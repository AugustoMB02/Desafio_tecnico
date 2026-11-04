"""Policy lookup by topic over the hand-curated `data/policies.md`.

Why a topic enum and not BM25/embeddings: the manual is ~2.5k tokens in 10 sections, and
SQLite FTS5 returned nothing for the brief's own question ("Me arrependi da minha compra,
posso devolver meu pedido?") because the manual only says "devolução"/"arrependimento" and
FTS5 has no Portuguese stemmer (scripts/review_checks/fts5_policy_probe.py). The model
picks topics from a fixed list, whole sections come back intact, and the decision to
consult policies stays visible in the trace.
"""

from __future__ import annotations

import re
from functools import cache
from pathlib import Path
from typing import Literal, get_args

from .data import DEFAULT_DATA_DIR

PolicyTopic = Literal[
    "sobre_a_loja",
    "horarios",
    "pagamento",
    "trocas_devolucoes",
    "frete_entregas",
    "promocoes",
    "garantia",
    "privacidade",
]
TOPICS: tuple[str, ...] = get_args(PolicyTopic)

TOPIC_SUMMARIES = {
    "sobre_a_loja": (
        "quem somos, endereço, CNPJ, telefone, WhatsApp e tempo de resposta, e-mail, o que vendemos"
    ),
    "horarios": "horário de funcionamento da loja e do WhatsApp, feriados",
    "pagamento": "PIX, débito, crédito, boleto, regras de parcelamento, pagamento combinado",
    "trocas_devolucoes": "arrependimento, troca por defeito, troca por preferência, exceções",
    "frete_entregas": "frete em Campo Grande e outras cidades, prazos, rastreamento",
    "promocoes": "campanhas do ano e regras de promoção (cumulatividade, PIX)",
    "garantia": "garantia legal de 90 dias, garantia do fabricante, o que não cobre",
    "privacidade": "LGPD, uso dos dados pessoais, exclusão de dados",
}

_MARKER = re.compile(r"<!-- (topic|notes): (\w+) -->")


@cache
def load_policies(path: Path = DEFAULT_DATA_DIR / "policies.md") -> dict[str, dict[str, str]]:
    """Parse policies.md into {topic: {"manual": ..., "notas": ...}}."""
    text = path.read_text(encoding="utf-8")
    parts = _MARKER.split(text)
    sections: dict[str, dict[str, str]] = {t: {"manual": "", "notas": ""} for t in TOPICS}
    # parts = [preamble, kind, topic, body, kind, topic, body, ...]
    for kind, topic, body in zip(parts[1::3], parts[2::3], parts[3::3], strict=True):
        if topic not in sections:
            raise ValueError(f"unknown policy topic in policies.md: {topic}")
        body = body.split("\n---\n")[0].split("\n# Notas de interpretação")[0].strip()
        sections[topic]["manual" if kind == "topic" else "notas"] = body
    missing = [t for t, s in sections.items() if not s["manual"]]
    if missing:
        raise ValueError(f"policies.md has no manual text for: {missing}")
    return sections


def consult_policy(topics: list[str]) -> dict[str, dict[str, str]]:
    """Whole sections for the requested topics (unknown topics are reported, not guessed)."""
    policies = load_policies()
    result: dict[str, dict[str, str]] = {}
    for topic in dict.fromkeys(topics):
        if topic in policies:
            result[topic] = policies[topic]
        else:
            result[topic] = {"erro": f"tópico desconhecido; use um de: {', '.join(TOPICS)}"}
    return result
