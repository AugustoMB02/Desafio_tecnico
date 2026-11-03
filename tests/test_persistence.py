"""Named conversations persisted in SQLite survive a restart of the process."""

from emporio_agent.cli import Session
from emporio_agent.clock import Clock, parse_now
from emporio_agent.data import load_store
from emporio_agent.graph import build_graph
from emporio_agent.persistence import sqlite_checkpointer
from emporio_agent.tickets import TicketStore
from emporio_agent.tools import AgentContext

from .fakes import ai, call, scripted


def make_session(tmp_path, model, thread):
    ctx = AgentContext(
        load_store(), Clock(parse_now("2026-11-04T10:00")), TicketStore(tmp_path / "t.jsonl")
    )
    app = build_graph(model, ctx, checkpointer=sqlite_checkpointer(tmp_path / "conversas.sqlite"))
    return Session(app, thread_id=thread)


def test_conversation_resumes_after_restart(tmp_path):
    first = make_session(tmp_path, scripted(ai("Oi! Como posso ajudar?")), "cliente-1")
    first.send("Oi, tudo bem?")
    assert first.history_size() == 2

    # A new process: new checkpointer object, new model, same file and thread name.
    model = scripted(ai("Claro, sobre o violão que você perguntou..."))
    second = make_session(tmp_path, model, "cliente-1")
    assert second.history_size() == 2
    second.send("E aí, lembra de mim?")
    seen = [m.content for m in model.seen[0][1:]]  # skip the system prompt
    assert seen == ["Oi, tudo bem?", "Oi! Como posso ajudar?", "E aí, lembra de mim?"]


def test_sessions_are_isolated(tmp_path):
    make_session(tmp_path, scripted(ai("Oi!")), "cliente-1").send("Oi")
    other = make_session(tmp_path, scripted(ai("Olá!")), "cliente-2")
    assert other.history_size() == 0


def test_verification_survives_with_the_thread(tmp_path):
    model = scripted(
        ai("", call("verify_customer", "v", order_id=7, email="leticia.rocha@jmail.com")),
        ai("Verificado, Letícia."),
    )
    make_session(tmp_path, model, "leticia").send("Pedido 7, leticia.rocha@jmail.com")
    resumed = make_session(tmp_path, scripted(ai("Oi de novo!")), "leticia")
    state = resumed.app.get_state(resumed.config).values
    assert state["verified_customer_id"] == 14


def test_cli_session_flag_resumes(tmp_path, monkeypatch, capsys):
    from emporio_agent import cli
    from emporio_agent.llm import ModelSpec

    replies = iter([scripted(ai("Primeira resposta.")), scripted(ai("Segunda resposta."))])
    monkeypatch.setattr(
        cli, "load_model", lambda spec: (next(replies), ModelSpec("fake:model", "fake"))
    )
    monkeypatch.setattr(cli, "DEFAULT_DB", tmp_path / "conversas.sqlite")
    monkeypatch.setattr(cli, "TicketStore", lambda: TicketStore(tmp_path / "t.jsonl"))
    script = tmp_path / "s.yaml"
    script.write_text('title: "x"\nturns:\n  - "oi"\n', encoding="utf-8")

    assert cli.main(["--session", "ana", "--script", str(script)]) == 0
    assert "Retomando" not in capsys.readouterr().out
    assert cli.main(["--session", "ana", "--script", str(script)]) == 0
    out = capsys.readouterr().out
    assert "Retomando a conversa 'ana': 2 mensagens anteriores" in out
    assert "Segunda resposta." in out
