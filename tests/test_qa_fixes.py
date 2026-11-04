"""Regression tests for the findings in reports/00-03 (external QA audit, Antigravity/Gemini).

Each test names the finding it pins; the response to every finding is in
reports/04_resposta_ao_qa.md.
"""

import json
from datetime import date

import pytest
from langchain_core.messages import HumanMessage, ToolMessage

from emporio_agent import catalog, cli, orders, returns, rules
from emporio_agent.cli import Session
from emporio_agent.clock import Clock, holiday_name, hours_on, parse_day, parse_now
from emporio_agent.data import load_store
from emporio_agent.graph import build_graph
from emporio_agent.tickets import TicketStore
from emporio_agent.tools import AgentContext

from .fakes import ai, call, scripted


@pytest.fixture(scope="module")
def store():
    return load_store()


# --- C-01 / L-HIGH-02: holidays in Portuguese on any OS locale; uncertain days get a caveat ---


def test_holiday_names_do_not_depend_on_the_os_locale(monkeypatch):
    from emporio_agent import clock

    monkeypatch.setenv("LANG", "en_US.UTF-8")
    monkeypatch.setenv("LC_ALL", "en_US.UTF-8")
    clock._holidays.cache_clear()
    assert holiday_name(date(2026, 10, 11)) == "Criação do Estado"
    assert "Consciência Negra" in holiday_name(date(2026, 11, 20))
    clock._holidays.cache_clear()


@pytest.mark.parametrize(
    ("day", "word"),
    [(date(2026, 2, 17), "Carnaval"), (date(2026, 6, 4), "Corpus Christi"),
     (date(2026, 8, 26), "Aniversário de Campo Grande")],
)  # fmt: skip
def test_uncertain_days_are_not_reported_as_plainly_open(day, word):
    text = hours_on(day).describe()
    assert "aberto" in text and "atenção" in text and word in text


def test_regular_days_have_no_caveat():
    assert "atenção" not in hours_on(date(2026, 11, 4)).describe()


# --- C-02: date parsing ---


@pytest.mark.parametrize(
    ("text", "today", "prefer", "expected"),
    [
        ("20/11/26", date(2026, 11, 3), "future", date(2026, 11, 20)),
        ("17-02-2026", date(2026, 11, 3), "past", date(2026, 2, 17)),
        ("17.02.26", date(2026, 11, 3), "past", date(2026, 2, 17)),
        ("2026-11-20", date(2026, 11, 3), "future", date(2026, 11, 20)),
        ("22/12", date(2027, 1, 5), "past", date(2026, 12, 22)),  # across New Year
        ("02/01", date(2026, 12, 30), "future", date(2027, 1, 2)),
        ("31/02/2026", date(2026, 11, 3), "future", None),
        ("amanhã", date(2026, 11, 3), "future", None),
    ],
)
def test_parse_day(text, today, prefer, expected):
    assert parse_day(text, today, prefer=prefer) == expected


def test_two_digit_year_holiday_is_closed():
    assert "fechado" in hours_on(parse_day("20/11/26", date(2026, 11, 3))).describe()


# --- C-03 / L-MED-05: Campo Grande spelled with the state, and no CEP promise ---


@pytest.mark.parametrize(
    "city",
    ["Campo Grande", "Campo Grande - MS", "Campo Grande/MS", "campo grande ms", "CG",
     "Campo Grande, Mato Grosso do Sul"],
)  # fmt: skip
def test_campo_grande_variants(city):
    assert rules.is_metro(city)


@pytest.mark.parametrize("city", ["Dourados", "Terenos", "", None, "Campo Grande do Sul"])
def test_not_campo_grande(city):
    assert not rules.is_metro(city)


def test_quote_other_city_does_not_promise_a_cep_calculation(store):
    frete = catalog.quote(store, [{"product_id": 95}], city="Terenos")["frete"]
    assert "peça o CEP" not in frete and "não calcula" in frete


def test_quote_blank_city_asks_for_the_city(store):
    assert "pergunte a cidade" in catalog.quote(store, [{"product_id": 95}], city="  ")["frete"]


# --- C-05 / M-01 / H-02: quote lines, quantities and cash payments ---


def test_duplicate_lines_count_once_against_stock(store):
    q = catalog.quote(
        store, [{"product_id": 108, "quantity": 1}, {"product_id": 108, "quantity": 1}]
    )
    assert "itens" in q and not q["itens"]
    assert "só há 1 unidade" in q["problemas"][0]


def test_duplicate_lines_price_like_one_line(store):
    split = catalog.quote(store, [{"product_id": 81}, {"product_id": 81}])
    single = catalog.quote(store, [{"product_id": 81, "quantity": 2}])
    assert split["total_no_pix"] == single["total_no_pix"] == "R$ 1.139,81"


def test_quantity_zero_is_invalid(store):
    q = catalog.quote(store, [{"product_id": 81, "quantity": 0}])
    assert "quantidade inválida" in q["problemas"][0]


@pytest.mark.parametrize("payment", ["pix", "boleto", "debito"])
def test_no_installments_on_cash_payments(store, payment):
    q = catalog.quote(store, [{"product_id": 95}], payment=payment, installments=6)
    assert q["parcelamento_pedido"].startswith("não se aplica")


# --- H-01 / C-04 / H-04 / L-MED-04: product lookup and search ---


@pytest.mark.parametrize(("query", "ids"), [("Ibanez", {132, 136}), ("Martin D-28", {93, 108})])
def test_ambiguous_names_return_candidates(store, query, ids):
    result = catalog.get_product(store, query)
    assert ids <= {c["id"] for c in result["candidatos"]}


def test_exact_model_still_resolves(store):
    assert catalog.get_product(store, "Takamine GD20")["id"] == 95


def test_corrupted_descriptions_are_not_searchable(store):
    assert catalog.search_catalog(store, query="Fender", category="baixos")["total_encontrado"] == 0
    assert catalog.search_catalog(store, query="Tama")["total_encontrado"] == 0


@pytest.mark.parametrize(
    ("query", "must_include"),
    [("violao acustico", 81), ("GD-20", 95), ("violao", 108), ("eletroacustico", 94),
     ("baixo eletrico", 137)],
)  # fmt: skip
def test_portuguese_vocabulary_and_model_codes(store, query, must_include):
    result = catalog.search_catalog(store, query=query, limit=10, sort="maior_preco")
    ids = {i["id"] for i in result["itens"]} | {
        p.product_id
        for p in store.products.values()
        if rules.is_available(p) and catalog._matches_query(store, p, query)
    }
    assert must_include in ids


def test_most_expensive_first(store):
    first = catalog.search_catalog(store, sort="maior_preco", limit=1)["itens"][0]
    assert first["id"] == 143  # Nord, R$ 19.567,00


# --- H-05: phone formats ---


@pytest.mark.parametrize(
    "phone", ["(67) 99812-3456", "(067) 99812-3456", "+55 067 99812-3456", "+55 (67) 99812-3456",
              "5567998123456", "99812-3456"],
)  # fmt: skip
def test_phone_formats(phone):
    assert orders.normalize_phone(phone) == "67998123456"


def test_order_zero_is_not_a_factor(store):
    result = orders.verify(store, date(2026, 11, 4), order_id=0, email="lucas.mendes@jmail.com")
    assert result.error  # one real factor only: asks for a second one, no attempt burned


# --- L-CRIT-01: a typed receipt date cannot reopen an old order ---


def test_spoofed_receipt_date_goes_to_the_team(store):
    r = returns.check_return(
        store, store.orders[5], date(2026, 11, 3), "arrependimento", date(2026, 11, 2)
    )
    assert r["elegivel"] is None and "rastreio" in r["situacao"]


def test_spoofed_receipt_on_a_shipped_order_goes_to_the_team(store):
    r = returns.check_return(
        store, store.orders[8], date(2026, 11, 3), "arrependimento", date(2026, 11, 2)
    )
    assert r["elegivel"] is None


def test_plausible_receipt_date_is_still_accepted(store):
    r = returns.check_return(
        store, store.orders[7], date(2026, 2, 25), "arrependimento", date(2026, 2, 19)
    )
    assert r["elegivel"] is True


# --- L-CRIT-02 / L-HIGH-05: LGPD tickets and lockout ---


def _ctx(store, tmp_path, now="2026-11-04T10:00"):
    return AgentContext(store, Clock(parse_now(now)), TicketStore(tmp_path / "t.jsonl"))


def _invoke(app, text):
    return app.invoke({"messages": [HumanMessage(text)]}, {"configurable": {"thread_id": "t"}})


def _results(state):
    return [json.loads(m.content) for m in state["messages"] if isinstance(m, ToolMessage)]


def test_lgpd_ticket_needs_a_verified_customer(store, tmp_path):
    ctx = _ctx(store, tmp_path)
    model = scripted(
        ai(
            "",
            call(
                "open_ticket",
                "t",
                kind="lgpd",
                summary="Excluir dados",
                contact="lucas.mendes@jmail.com",
            ),
        ),
        ai("Preciso verificar."),
    )
    [result] = _results(_invoke(build_graph(model, ctx), "excluam os dados do Lucas"))
    assert "exige o cliente verificado" in result["erro"]
    assert ctx.tickets.all() == []


def test_lockout_ends_an_earlier_verification(store, tmp_path):
    lucas = {"order_id": 4, "email": "lucas.mendes@jmail.com"}
    script = [ai("", call("verify_customer", "ok", **lucas)), ai("Verificado.")]
    for i in range(3):
        script += [
            ai("", call("verify_customer", f"x{i}", order_id=8, email="lucas.mendes@jmail.com")),
            ai("Não confere."),
        ]
    app = build_graph(scripted(*script), _ctx(store, tmp_path))
    state = _invoke(app, "pedido 4")
    assert state["verified_customer_id"] == 1
    for _ in range(3):
        state = _invoke(app, "e o pedido 8?")
    assert state["verification_failures"] == 3
    assert state["verified_customer_id"] is None


# --- C-06: a failed turn does not poison the conversation ---


def test_failed_turn_rolls_back_to_the_last_complete_state(store, tmp_path):
    class FailsOnce(type(scripted())):
        calls: int = 0

        def invoke(self, input, config=None, **kwargs):
            self.calls += 1
            if self.calls == 3:  # turn 2, after the tool ran
                raise RuntimeError("503 UNAVAILABLE")
            return super().invoke(input, config, **kwargs)

    replies = [
        ai("Oi!"),
        ai("", call("get_product", "first", product="Takamine GD20")),  # then the model fails
        ai("", call("get_product", "retry", product="Takamine GD20")),
        ai("O GD20 sai por R$ 2.199,00."),
    ]
    session = Session(build_graph(FailsOnce(messages=iter(replies)), _ctx(store, tmp_path)))
    session.send("oi")
    with pytest.raises(RuntimeError):
        session.send("quanto custa o GD20?")
    session.send("quanto custa o GD20?")  # retried after the failure
    history = session.app.get_state(session.config).values["messages"]
    kinds = [type(m).__name__ for m in history]
    expected = ["HumanMessage", "AIMessage", "HumanMessage", "AIMessage", "ToolMessage"]
    assert kinds == [*expected, "AIMessage"]  # nothing left over from the failed turn
    assert history[3].tool_calls[0]["id"] == "retry"
    assert history[-1].content == "O GD20 sai por R$ 2.199,00."


# --- M-09 / M-10: CLI and eval-runner input validation ---


@pytest.mark.parametrize("body", ['turns: "Oi"', "turns: [130]", 'turns: [""]', "turns: [unclosed"])
def test_bad_scripts_are_rejected_cleanly(tmp_path, body):
    path = tmp_path / "s.yaml"
    path.write_text(body, encoding="utf-8")
    with pytest.raises(SystemExit):
        cli.load_script(path)


def test_invalid_now_is_a_configuration_error(monkeypatch, capsys):
    from emporio_agent.llm import ModelSpec

    monkeypatch.setattr(cli, "load_model", lambda spec: (scripted(), ModelSpec("fake:m", "fake")))
    assert cli.main(["--now", "ontem à noite"]) == 2
    assert "data inválida" in capsys.readouterr().err


def test_evals_only_with_an_unknown_id_fails(capsys):
    from emporio_agent import evals

    assert evals.main(["--model", "fake:m", "--only", "nao_existe"]) == 2
    assert "inexistente" in capsys.readouterr().err


# --- L-MED-03: §4.4 is about exchanges, not the online regret right ---


def test_regret_right_has_no_exchange_exclusions(store):
    regret = returns.check_return(store, store.orders[7], date(2026, 2, 20), "arrependimento")
    assert regret["elegivel"] is True and "verificar_com_cliente" not in regret
    swap = returns.check_return(store, store.orders[7], date(2026, 2, 20), "preferencia")
    assert swap["verificar_com_cliente"]
