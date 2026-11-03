"""Customer verification, order summaries and the order tools inside the graph."""

import json
from datetime import date

import pytest
from langchain_core.messages import HumanMessage, ToolMessage

from emporio_agent import orders
from emporio_agent.clock import Clock, parse_now
from emporio_agent.data import load_store
from emporio_agent.graph import build_graph
from emporio_agent.tools import AgentContext

from .fakes import ai, call, scripted

TODAY = date(2026, 11, 4)
BRUNO = "bruno.martins@jmail.com"


@pytest.fixture(scope="module")
def store():
    return load_store()


def cid(result):
    return result.customer.customer_id if result.customer else None


# --- pure verification ----------------------------------------------------------------------


def test_order_plus_email(store):
    assert cid(orders.verify(store, TODAY, order_id=7, email="Leticia.Rocha@jmail.com ")) == 14


def test_order_plus_phone(store):
    assert cid(orders.verify(store, TODAY, order_id=8, phone="(67) 99654-7821")) == 2


@pytest.mark.parametrize("phone", ["(67) 98543-2109", "+55 67 98543-2109", "985432109"])
def test_phone_formats(store, phone):
    assert cid(orders.verify(store, TODAY, email=BRUNO, phone=phone)) == 11


def test_shared_email_customer_43_gets_his_own_account(store):
    result = orders.verify(store, TODAY, email=BRUNO, phone="(67) 99456-3456")
    assert cid(result) == 43
    assert orders.customer_orders(store, 43, TODAY) == []


def test_shared_email_plus_order_resolves_to_owner(store):
    assert cid(orders.verify(store, TODAY, order_id=10, email=BRUNO)) == 11


def test_customer_43_phone_cannot_open_order_10(store):
    assert not orders.verify(store, TODAY, order_id=10, phone="(67) 99456-3456").ok


def test_wrong_pair_fails_without_error_detail(store):
    result = orders.verify(store, TODAY, order_id=7, email=BRUNO)
    assert not result.ok and result.error is None


def test_single_factor_is_an_input_error(store):
    result = orders.verify(store, TODAY, email=BRUNO)
    assert not result.ok and result.error


def test_frozen_clock_hides_future_orders(store):
    early = date(2026, 2, 20)
    assert 10 not in orders.visible_orders(store, early)  # placed 25/02/2026
    assert not orders.verify(store, early, order_id=10, email=BRUNO).ok
    assert cid(orders.verify(store, early, order_id=7, email="leticia.rocha@jmail.com")) == 14


# --- summaries --------------------------------------------------------------------------------


def test_summary_of_overdue_shipment(store):
    summary = orders.order_summary(store, store.orders[8], TODAY)
    assert summary["status"] == "enviado"
    assert summary["codigo_rastreio"] == "BRJL5544332BR"
    assert summary["previsao_entrega"] == "28/02/2026"
    assert "previsão de entrega passou" in summary["atencao"][0]


def test_summary_of_stale_pending_order(store):
    summary = orders.order_summary(store, store.orders[14], TODAY)
    assert summary["status"].startswith("pendente")
    assert summary["total_pago"] == "R$ 1.749,00"
    assert summary["pagamento"] == "cartão de débito"
    assert "sem envio há" in summary["atencao"][0]


def test_summary_reports_totals_verbatim(store):
    summary = orders.order_summary(store, store.orders[3], TODAY)
    assert summary["total_pago"] == "R$ 3.450,00"  # not recomputed from today's prices
    assert summary["itens"] == ["2x Kala KA-ABP-CTG Barítono Cedar"]
    assert summary["pagamento"] == "cartão de crédito em 12x"


def test_summary_shows_cancellation_note(store):
    assert "Endereço" in orders.order_summary(store, store.orders[20], TODAY)["observacao"]


# --- tools in the graph -------------------------------------------------------------------------


@pytest.fixture
def ctx(store):
    return AgentContext(store=store, clock=Clock(parse_now("2026-11-04T10:00")))


def invoke(app, text, thread="t"):
    return app.invoke({"messages": [HumanMessage(text)]}, {"configurable": {"thread_id": thread}})


def payloads(state, since=0):
    return [json.loads(m.content) for m in state["messages"][since:] if isinstance(m, ToolMessage)]


def test_verification_returns_orders_despite_parallel_call(ctx):
    model = scripted(
        ai(
            "",
            call("verify_customer", "v1", order_id=7, email="leticia.rocha@jmail.com"),
            call("get_my_orders", "o1"),
        ),
        ai("Achei seu pedido!"),
    )
    state = invoke(build_graph(model, ctx), "pedido 7, leticia.rocha@jmail.com")
    verified, parallel_orders = payloads(state)
    assert verified["verificado"] and verified["primeiro_nome"] == "Letícia"
    assert verified["pedidos"][0]["pedido"] == 7
    assert "não verificado" in parallel_orders["erro"]  # saw the pre-step state, as expected
    assert state["verified_customer_id"] == 14


def test_orders_tool_after_verification_is_scoped_to_the_customer(ctx):
    model = scripted(
        ai("", call("verify_customer", "v1", email=BRUNO, phone="(67) 98543-2109")),
        ai("Verificado."),
        ai("", call("get_my_orders", "o1", order_id=7)),
        ai("Esse pedido não é seu."),
        ai("", call("get_my_orders", "o2")),
        ai("Seu pedido 10 está confirmado."),
    )
    app = build_graph(model, ctx)
    invoke(app, "sou o Bruno")
    state = invoke(app, "e o pedido 7?")
    assert "não está entre os pedidos" in payloads(state)[-1]["erro"]
    state = invoke(app, "meus pedidos")
    assert [p["pedido"] for p in payloads(state)[-1]["pedidos"]] == [10]


def test_three_failures_lock_verification(ctx):
    wrong = [ai("", call("verify_customer", f"v{i}", order_id=i, email=BRUNO)) for i in (1, 2, 3)]
    script = []
    for msg in wrong:
        script += [msg, ai("Não consegui confirmar.")]
    script += [
        ai("", call("verify_customer", "v4", order_id=10, email=BRUNO)),
        ai("Bloqueado."),
    ]
    app = build_graph(scripted(*script), ctx)
    for _ in range(3):
        state = invoke(app, "tentativa")
        result = payloads(state)[-1]
        assert result["verificado"] is False
        assert "e-mail" not in result["mensagem"] and "pedido" not in result["mensagem"]
    assert state["verification_failures"] == 3
    state = invoke(app, "pedido 10")  # the correct pair, but too late
    assert "bloqueada" in payloads(state)[-1]["erro"]
    assert state.get("verified_customer_id") is None


def test_parallel_guesses_count_once_and_only_first_is_checked(ctx):
    model = scripted(
        ai("", *[call("verify_customer", f"v{i}", order_id=i, email=BRUNO) for i in (9, 10, 11)]),
        ai("..."),
    )
    state = invoke(build_graph(model, ctx), "chutes")
    first, second, third = payloads(state)
    assert first["verificado"] is False
    assert "uma verificação por vez" in second["erro"] and "uma verificação" in third["erro"]
    assert state["verification_failures"] == 1
    assert state.get("verified_customer_id") is None
