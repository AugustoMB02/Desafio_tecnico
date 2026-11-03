"""Fidelity of data/policies.md to the PDF, and the consult_policy lookup."""

import re
from functools import cache

import pytest
from pypdf import PdfReader

from emporio_agent.data import DEFAULT_DATA_DIR
from emporio_agent.policy import TOPICS, consult_policy, load_policies


def _norm(text: str) -> str:
    text = re.sub(r"[​•]", " ", text)
    return re.sub(r"\s+", " ", text).strip()


@cache
def pdf_text() -> str:
    reader = PdfReader(DEFAULT_DATA_DIR / "políticas_da_loja.pdf")
    return _norm(" ".join(page.extract_text() for page in reader.pages))


def _manual_lines():
    for topic, section in load_policies().items():
        for line in section["manual"].splitlines():
            line = line.strip()
            if line and not line.startswith("#"):
                yield topic, _norm(line.removeprefix("- "))


def test_every_topic_has_manual_text_and_notes():
    policies = load_policies()
    assert set(policies) == set(TOPICS)
    for topic in TOPICS:
        assert policies[topic]["manual"], topic
        assert policies[topic]["notas"], topic


def test_manual_text_is_verbatim_from_the_pdf():
    """Prose and bullets are literal; table rows (flattened with ':' and '—') match cell by cell."""
    pdf = pdf_text()
    for topic, line in _manual_lines():
        if line in pdf:
            continue
        cells = [c.strip() for c in re.split(r" — |: ", line) if c.strip()]
        assert len(cells) > 1, f"[{topic}] not in the PDF: {line}"
        for cell in cells:
            assert cell in pdf, f"[{topic}] table cell not in the PDF: {cell!r}"


@pytest.mark.parametrize(
    ("topic", "fact"),
    [
        ("sobre_a_loja", "Rua 14 de Maio, 3200"),
        ("sobre_a_loja", "79202-333"),
        ("sobre_a_loja", "(67) 3341-4444"),
        ("sobre_a_loja", "(67) 3321-4500"),
        ("horarios", "09:00 às 18:00"),
        ("horarios", "09:00 às 13:00"),
        ("horarios", "Domingo e Feriados"),
        ("pagamento", "5% de desconto"),
        ("pagamento", "R$ 2.000,00"),
        ("trocas_devolucoes", "7 (sete) dias corridos após o recebimento"),
        ("trocas_devolucoes", "30 (trinta) dias corridos após a compra"),
        ("garantia", "90 (noventa) dias"),
        ("frete_entregas", "R$ 500,00"),
        ("frete_entregas", "R$ 35,00"),
        ("frete_entregas", "1 a 3 dias úteis"),
    ],
)
def test_key_facts_match_pdf_and_markdown(topic, fact):
    assert fact in pdf_text()
    assert fact in _norm(load_policies()[topic]["manual"])


def test_ascii_email_is_the_one_recommended():
    assert "contato@emporiodamusica.com.br" in pdf_text()
    assert "contato@emporiodamusica.com.br" in load_policies()["sobre_a_loja"]["notas"]


def test_agent_only_sections_stay_out_of_the_tool():
    everything = " ".join(s["manual"] for s in load_policies().values())
    assert "Tom de voz" not in everything  # §7.1 lives in the system prompt
    assert "consultar a gerência" not in everything  # §10 lives in the system prompt


def test_consult_policy_returns_whole_sections():
    result = consult_policy(["trocas_devolucoes", "garantia", "trocas_devolucoes"])
    assert list(result) == ["trocas_devolucoes", "garantia"]
    manual = result["trocas_devolucoes"]["manual"]
    for heading in ("4.1", "4.2", "4.3", "4.4"):
        assert heading in manual


def test_consult_policy_reports_unknown_topics():
    assert "erro" in consult_policy(["cancelamento"])["cancelamento"]
