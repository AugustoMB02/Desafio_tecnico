"""The LangGraph agent wiring, driven by a scripted fake model (no API calls)."""

import json

import pytest
from langchain_core.messages import HumanMessage, SystemMessage, ToolMessage
from langchain_core.utils.function_calling import convert_to_openai_tool

from emporio_agent.cli import Session, collect_turn, transcript_markdown
from emporio_agent.clock import Clock, parse_now
from emporio_agent.data import load_store
from emporio_agent.graph import build_graph
from emporio_agent.llm import ModelConfigError, parse_spec
from emporio_agent.prompts import STATIC_PROMPT
from emporio_agent.tools import AgentContext, build_tools

from .fakes import ai, call, scripted


@pytest.fixture(scope="module")
def ctx():
    return AgentContext(store=load_store(), clock=Clock(parse_now("2026-11-04T10:00")))


def run(ctx, model, text, **kw):
    app = build_graph(model, ctx, **kw)
    config = {"configurable": {"thread_id": "t"}}
    return app.invoke({"messages": [HumanMessage(text)]}, config)


def tool_messages(state):
    return [m for m in state["messages"] if isinstance(m, ToolMessage)]


def test_tool_schemas_are_valid(ctx):
    names = []
    for t in build_tools(ctx):
        schema = convert_to_openai_tool(t)
        assert schema["function"]["description"]
        names.append(t.name)
    assert {"search_catalog", "get_product", "quote", "consult_policy", "check_store_hours"} <= set(
        names
    )


def test_catalog_lookup_round_trip(ctx):
    model = scripted(
        ai("", call("get_product", product="Takamine GD20")),
        ai("O Takamine GD20 sai por R$ 2.199,00."),
    )
    state = run(ctx, model, "Quanto custa o Takamine GD20?")
    [result] = tool_messages(state)
    payload = json.loads(result.content)
    assert payload["preco"] == "R$ 2.199,00"
    assert payload["pix"].startswith("R$ 2.089,05")
    assert payload["parcelamento"] == "até 12x de R$ 183,25 sem juros"
    assert state["messages"][-1].content == "O Takamine GD20 sai por R$ 2.199,00."


def test_parallel_tool_calls_in_one_step(ctx):
    model = scripted(
        ai(
            "",
            call("consult_policy", "c1", topics=["sobre_a_loja"]),
            call("check_store_hours", "c2", day="20/11/2026"),
        ),
        ai("Fica na Rua 14 de Maio, 3200. Dia 20/11 estaremos fechados."),
    )
    state = run(ctx, model, "Qual o endereço? Vocês abrem dia 20/11?")
    policy, hours = tool_messages(state)
    assert "Rua 14 de Maio, 3200" in policy.content
    assert "Consciência Negra" in json.loads(hours.content)["dia_consultado"]


def test_system_prompt_static_first_dynamic_last(ctx):
    model = scripted(ai("Olá!"))
    run(ctx, model, "oi")
    system = model.seen[0][0]
    assert isinstance(system, SystemMessage)
    assert isinstance(system.content, str)
    assert system.content.startswith(STATIC_PROMPT)
    assert "quarta-feira, 04/11/2026 às 10:00" in system.content
    assert "Data simulada" in system.content


def test_prompt_cache_blocks_for_anthropic(ctx):
    model = scripted(ai("Olá!"))
    run(ctx, model, "oi", cache_prompt=True)
    static, dynamic = model.seen[0][0].content
    assert static["text"] == STATIC_PROMPT and static["cache_control"] == {"type": "ephemeral"}
    assert "Contexto desta mensagem" in dynamic["text"]


def test_prompt_core_rules():
    for rule in ("somente instrumentos musicais", "loja parceira", "verify_customer",
                 "nunca invente", "24 horas úteis"):  # fmt: skip
        assert rule.lower() in STATIC_PROMPT.lower(), rule


def test_session_and_transcript(ctx):
    model = scripted(
        ai("", call("search_catalog", category="violoes", max_price_brl=1000)),
        ai("Temos 12 opções!"),
        ai("Por nada!"),
    )
    session = Session(build_graph(model, ctx))
    first = session.send("Quais violões até R$ 1000?")
    second = session.send("Valeu")
    assert first.reply == "Temos 12 opções!"
    assert [tc.name for tc in first.tool_calls] == ["search_catalog"]
    assert json.loads(first.tool_calls[0].result)["total_encontrado"] == 12
    assert second.tool_calls == [] and second.reply == "Por nada!"

    md = transcript_markdown(session.turns, title="Teste", model="fake:model", clock=ctx.clock)
    assert md.startswith("# Teste")
    assert "`fake:model`" in md and "simulado em" in md
    assert "**Cliente:** Quais violões até R$ 1000?" in md
    assert "<code>search_catalog</code>" in md


def test_collect_turn_ignores_empty_text():
    turn = collect_turn("oi", [ai("", call("get_product", product="81")), ai("Pronto")])
    assert turn.reply == "Pronto"


def test_model_spec_is_required(monkeypatch):
    monkeypatch.delenv("MODEL", raising=False)
    with pytest.raises(ModelConfigError):
        parse_spec(None)
    with pytest.raises(ModelConfigError):
        parse_spec("claude-sonnet-5-5")
    spec = parse_spec("anthropic:claude-sonnet-5-5")
    assert spec.provider == "anthropic" and spec.supports_prompt_cache


def test_cli_script_and_export(tmp_path, monkeypatch):
    from emporio_agent import cli
    from emporio_agent.llm import ModelSpec

    model = scripted(
        ai("", call("consult_policy", topics=["sobre_a_loja"])),
        ai("Ficamos na Rua 14 de Maio, 3200 — Centro."),
    )
    monkeypatch.setattr(cli, "load_model", lambda spec: (model, ModelSpec("fake:model", "fake")))
    monkeypatch.setattr(cli, "TicketStore", lambda: None)
    script = tmp_path / "s.yaml"
    script.write_text(
        'title: "Endereço"\nnow: "2026-02-20T10:00"\nturns:\n  - "Qual o endereço?"\n',
        encoding="utf-8",
    )
    out = tmp_path / "out.md"
    assert cli.main(["--script", str(script), "--export", str(out)]) == 0
    md = out.read_text(encoding="utf-8")
    assert md.startswith("# Endereço") and "2026-02-20T10:00:00-04:00" in md
    assert "Rua 14 de Maio, 3200" in md


def test_example_scripts_parse():
    from pathlib import Path

    from emporio_agent.cli import load_script

    scripts = sorted(Path(__file__).parents[1].glob("examples/scripts/*.yaml"))
    assert len(scripts) >= 5
    for path in scripts:
        data = load_script(path)
        assert data["title"] and all(isinstance(t, str) for t in data["turns"])


def test_cli_script_aborts_without_export_on_model_error(tmp_path, monkeypatch, capsys):
    from emporio_agent import cli
    from emporio_agent.llm import ModelSpec

    class Broken(type(scripted())):
        def invoke(self, input, config=None, **kwargs):
            raise RuntimeError("402 RESOURCE_EXHAUSTED. Your prepayment credits are depleted.")

    model = Broken(messages=iter([]))
    monkeypatch.setattr(cli, "load_model", lambda spec: (model, ModelSpec("fake:model", "fake")))
    monkeypatch.setattr(cli, "TicketStore", lambda: None)
    script = tmp_path / "s.yaml"
    script.write_text('title: "x"\nturns:\n  - "oi"\n', encoding="utf-8")
    out = tmp_path / "out.md"
    assert cli.main(["--script", str(script), "--export", str(out)]) == 1
    assert not out.exists()
    err = capsys.readouterr().err
    assert "RESOURCE_EXHAUSTED" in err and "nada foi exportado" in err
