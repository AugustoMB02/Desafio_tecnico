"""The scenario runner's checks, and a full run against the scripted fake model."""

from decimal import Decimal
from pathlib import Path

import yaml

from emporio_agent.cli import Session
from emporio_agent.clock import Clock
from emporio_agent.data import load_store
from emporio_agent.evals import (
    DEFAULT_SCENARIOS,
    TurnRecord,
    check_conversation,
    check_turn,
    money_values,
    plain_numbers,
    render_report,
    run_scenario,
)
from emporio_agent.graph import build_graph
from emporio_agent.tools import AgentContext

from .fakes import ai, call, scripted


def test_money_values():
    text = "De R$ 2.199,00 por R$2.089,05; parcela R$ 183,25 e frete R$ 35"
    assert money_values(text) == {Decimal("2199.00"), Decimal("2089.05"), Decimal("183.25"),
                                  Decimal("35")}  # fmt: skip


def test_plain_numbers():
    assert {Decimal(1000), Decimal(500)} <= plain_numbers("até 1.000 ou 500 reais")


def record(reply, tools=(), outputs=(), user="oi"):
    return TurnRecord(user, reply, list(tools), list(outputs))


def failures(checks):
    return [c.message for c in checks if not c.ok]


def test_grounded_reply_passes():
    turn = record("Sai por R$ 2.199,00.", ["get_product"], ['{"preco":"R$ 2.199,00"}'])
    assert failures(check_turn({"tools": ["get_product"], "reply_any": ["2.199"]}, turn, [])) == []


def test_invented_amount_fails():
    turn = record("Sai por R$ 1.999,00.", ["get_product"], ['{"preco":"R$ 2.199,00"}'])
    [msg] = failures(check_turn({}, turn, []))
    assert "1999" in msg


def test_amounts_from_earlier_turns_and_user_budget_are_grounded():
    earlier = record("ok", ["quote"], ['{"total":"R$ 569,91"}'], user="tenho até R$ 600")
    turn = record("Lembrando: R$ 569,91, dentro dos seus R$ 600.")
    assert failures(check_turn({}, turn, [earlier])) == []


def test_punctuation_counts_so_percent_does_not_match_installments():
    turn = record("Sai por R$ 2.199,00 ou 12x de R$ 183,25.", ["get_product"],
                  ['{"preco":"R$ 2.199,00","parcelamento":"12x de R$ 183,25"}'])  # fmt: skip
    assert failures(check_turn({"reply_none": ["12%"]}, turn, [])) == []
    assert failures(check_turn({"reply_none": ["12x"]}, turn, []))


def test_conversation_level_expectations_accept_any_turn():
    first = record("Verificado e fora do prazo (24/02/2026).", ["verify_customer", "check_return"],
                   ['{"verificado":true}', '{"elegivel":false}'])  # fmt: skip
    second = record("Entendo, posso ajudar em algo mais?")
    expect = {"tools": ["check_return"], "tool_output": ['"elegivel":false'],
              "reply_any": ["24/02/2026"], "reply_none": ["devolução aprovada"]}  # fmt: skip
    assert failures(check_conversation(expect, [first, second])) == []
    assert failures(check_conversation({"tools": ["open_ticket"]}, [first, second]))


def test_text_checks_ignore_accents_and_case():
    turn = record("A loja está FECHADA no feriado.")
    expect = {"reply_any": ["fechad"], "reply_none": ["aberta"], "no_tools": ["quote"]}
    assert failures(check_turn(expect, turn, [])) == []
    assert failures(check_turn({"reply_none": ["fechada"]}, turn, []))


def test_scenarios_file_is_well_formed():
    scenarios = yaml.safe_load(Path(DEFAULT_SCENARIOS).read_text(encoding="utf-8"))["scenarios"]
    ids = [s["id"] for s in scenarios]
    assert len(ids) == len(set(ids)) >= 20
    allowed = {"tools", "no_tools", "tool_output", "reply_any", "reply_none"}
    for s in scenarios:
        assert s["turns"], s["id"]
        assert set(s.get("expect", {})) <= allowed, s["id"]
        for turn in s["turns"]:
            assert turn["user"].strip()
            assert set(turn.get("expect", {})) <= allowed, s["id"]


def test_run_scenario_with_fake_model():
    scenario = {
        "id": "takamine",
        "now": "2026-11-04T10:00",
        "turns": [
            {"user": "Quanto custa o Takamine GD20?",
             "expect": {"tools": ["get_product"], "reply_any": ["2.199,00"]}},
        ],
    }  # fmt: skip
    model = scripted(
        ai("", call("get_product", product="Takamine GD20")),
        ai("O GD20 sai por R$ 2.199,00 ou R$ 2.089,05 no PIX."),
    )

    def make_session(now, tickets):
        ctx = AgentContext(load_store(), Clock.from_env(now), tickets)
        return Session(build_graph(model, ctx))

    result = run_scenario(scenario, make_session)
    assert result.passed, render_report([result])
    assert "1/1 passaram" in render_report([result])
