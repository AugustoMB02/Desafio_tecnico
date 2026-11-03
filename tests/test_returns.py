"""Return/exchange/warranty eligibility and ticket creation."""

import json
from datetime import date

import pytest
from langchain_core.messages import HumanMessage, ToolMessage

from emporio_agent.clock import Clock, parse_now
from emporio_agent.data import load_store
from emporio_agent.graph import build_graph
from emporio_agent.returns import check_return
from emporio_agent.tickets import TicketStore
from emporio_agent.tools import AgentContext

from .fakes import ai, call, scripted

LETICIA = {"order_id": 7, "email": "leticia.rocha@jmail.com"}  # order 7: received 17/02/2026


@pytest.fixture(scope="module")
def store():
    return load_store()


def check(store, order_id, today, reason, received_on=None):
    return check_return(store, store.orders[order_id], today, reason, received_on)


# --- regret (§4.1) ----------


def test_regret_within_seven_days(store):
    r = check(store, 7, date(2026, 2, 20), "arrependimento")
    assert r["elegivel"] is True
    assert "24/02/2026" in r["regra"]
    assert r["datas"]["dias_desde_o_recebimento"] == 3
    assert any("10 dias úteis" in c for c in r["condicoes"])
    assert "previsão de entrega registrada" in r["datas"]["recebimento"]


@pytest.mark.parametrize(
    ("today", "eligible"), [(date(2026, 2, 24), True), (date(2026, 2, 25), False)]
)
def test_regret_boundary(store, today, eligible):
    assert check(store, 7, today, "arrependimento")["elegivel"] is eligible


def test_regret_expired_with_real_clock_points_to_warranty(store):
    r = check(store, 7, date(2026, 11, 4), "arrependimento")
    assert r["elegivel"] is False
    assert "24/02/2026" in r["regra"]
    assert "defeito" in r["alternativa"]


def test_customer_supplied_receipt_date_wins(store):
    r = check(store, 7, date(2026, 2, 25), "arrependimento", received_on=date(2026, 2, 19))
    assert r["elegivel"] is True
    assert r["datas"]["recebimento"] == "19/02/2026"


def test_receipt_date_cannot_be_in_the_future(store):
    r = check(store, 7, date(2026, 2, 20), "arrependimento", received_on=date(2026, 3, 1))
    assert r["elegivel"] is None


# --- defects and warranty (§4.2, §8) ------------------------------------------------------------


def test_defect_within_30_days_of_purchase_is_direct_exchange(store):
    r = check(store, 7, date(2026, 3, 5), "defeito")  # 30 days after the 03/02 purchase
    assert r["elegivel"] is True and r["caminho"] == "troca direta na loja"


def test_defect_after_30_days_uses_legal_warranty(store):
    r = check(store, 7, date(2026, 4, 1), "defeito")
    assert r["elegivel"] is True
    assert "garantia legal" in r["caminho"]
    assert "18/05/2026" in r["regra"]  # 17/02 + 90 days


def test_defect_after_90_days_goes_to_manufacturer(store):
    r = check(store, 7, date(2026, 11, 4), "defeito")
    assert r["elegivel"] is None
    assert "fabricante" in r["caminho"]
    assert r["nao_coberto"]


# --- preference (§4.3) ----------


def test_preference_exchange(store):
    assert check(store, 7, date(2026, 2, 20), "preferencia")["elegivel"] is True
    assert check(store, 7, date(2026, 3, 1), "preferencia")["elegivel"] is False


# --- status branches ----------


@pytest.mark.parametrize("order_id", [9, 14])  # confirmed, pending
def test_not_shipped_is_a_cancellation_request(store, order_id):
    r = check(store, order_id, date(2026, 11, 4), "arrependimento")
    assert r["caminho"] == "cancelamento" and r["elegivel"] is None
    assert "sem prometer" in r["regra"]


def test_shipped_not_received_is_a_cancellation_request(store):
    r = check(store, 8, date(2026, 3, 1), "arrependimento")
    assert r["caminho"] == "cancelamento"
    assert "recebido" in r["situacao"]


def test_shipped_and_received_uses_the_customer_date(store):
    r = check(store, 8, date(2026, 3, 5), "arrependimento", received_on=date(2026, 3, 1))
    assert r["elegivel"] is True


def test_cancelled_order(store):
    assert check(store, 20, date(2026, 11, 4), "arrependimento")["elegivel"] is False


# --- tickets ----------


def test_ticket_store_numbers_sequentially(tmp_path):
    tickets = TicketStore(tmp_path / "t.jsonl")
    now = parse_now("2026-11-04T10:00")
    first = tickets.open(kind="interesse", summary="Quer saxofone", now=now, contact="x@y.com")
    second = tickets.open(kind="reclamacao", summary="Atraso", now=now, customer_id=2)
    assert (first["protocolo"], second["protocolo"]) == ("EMP-2026-0001", "EMP-2026-0002")
    assert [t["tipo"] for t in tickets.all()] == ["interesse", "reclamacao"]


# --- tools in the graph ----------


def make_ctx(store, tmp_path, now):
    return AgentContext(store, Clock(parse_now(now)), TicketStore(tmp_path / "tickets.jsonl"))


def results(state):
    return [json.loads(m.content) for m in state["messages"] if isinstance(m, ToolMessage)]


def invoke(app, text):
    return app.invoke({"messages": [HumanMessage(text)]}, {"configurable": {"thread_id": "t"}})


def test_return_flow_with_frozen_clock(store, tmp_path):
    ctx = make_ctx(store, tmp_path, "2026-02-20T10:00")
    model = scripted(
        ai("", call("verify_customer", "v", **LETICIA)),
        ai("", call("check_return", "r", order_id=7, reason="arrependimento")),
        ai("Pode devolver até 24/02/2026. Confirma que abro o chamado?"),
        ai("", call("open_ticket", "t", kind="devolucao", summary="Arrependimento", order_id=7)),
        ai("Protocolo EMP-2026-0001."),
    )
    app = build_graph(model, ctx)
    state = invoke(app, "Me arrependi da minha compra. Pedido 7, leticia.rocha@jmail.com")
    _, eligibility = results(state)
    assert eligibility["elegivel"] is True
    state = invoke(app, "Sim, pode abrir")
    ticket = results(state)[-1]
    assert ticket["protocolo"] == "EMP-2026-0001"
    [saved] = ctx.tickets.all()
    assert saved["cliente_verificado"] == 14 and saved["pedido"] == 7


def test_check_return_requires_verification(store, tmp_path):
    ctx = make_ctx(store, tmp_path, "2026-11-04T10:00")
    model = scripted(ai("", call("check_return", "r", order_id=7, reason="defeito")), ai("..."))
    assert "não verificado" in results(invoke(build_graph(model, ctx), "devolver"))[0]["erro"]


def test_unverified_ticket_needs_contact_and_no_order(store, tmp_path):
    ctx = make_ctx(store, tmp_path, "2026-11-04T10:00")
    model = scripted(
        ai(
            "",
            call("open_ticket", "a", kind="interesse", summary="Saxofone alto"),
            call("open_ticket", "b", kind="devolucao", summary="x", order_id=7, contact="a@b.c"),
            call("open_ticket", "c", kind="interesse", summary="Sax", contact="(67) 99999-0000"),
        ),
        ai("Registrado."),
    )
    no_contact, foreign_order, ok = results(invoke(build_graph(model, ctx), "quero um sax"))
    assert "telefone ou e-mail" in no_contact["erro"]
    assert "verificado" in foreign_order["erro"]
    assert ok["protocolo"] == "EMP-2026-0001"
    assert "não prometa prazo" in ok["retorno"]
    assert len(ctx.tickets.all()) == 1
