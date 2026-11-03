"""Service tickets ("chamados") appended to a JSON Lines file.

The operational CSVs stay read-only; anything the agent hands off to the team is
recorded here with a protocol number. The default file lives under `.state/`, which is
gitignored because tickets may hold customer contact data.
"""

from __future__ import annotations

import json
import threading
from datetime import datetime
from pathlib import Path
from typing import Any, Literal

TicketKind = Literal[
    "devolucao",
    "troca",
    "garantia",
    "cancelamento",
    "reclamacao",
    "interesse",
    "lgpd",
    "atendimento_humano",
    "outro",
]
DEFAULT_TICKETS_PATH = Path(__file__).resolve().parents[2] / ".state" / "tickets.jsonl"


class TicketStore:
    def __init__(self, path: Path | str = DEFAULT_TICKETS_PATH) -> None:
        self.path = Path(path)
        self._lock = threading.Lock()  # ToolNode runs parallel tool calls in threads

    def _count(self) -> int:
        if not self.path.exists():
            return 0
        with self.path.open(encoding="utf-8") as f:
            return sum(1 for line in f if line.strip())

    def open(
        self,
        *,
        kind: str,
        summary: str,
        now: datetime,
        customer_id: int | None = None,
        order_id: int | None = None,
        contact: str | None = None,
    ) -> dict[str, Any]:
        with self._lock:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            protocol = f"EMP-{now.year}-{self._count() + 1:04d}"
            record = {
                "protocolo": protocol,
                "tipo": kind,
                "resumo": summary.strip(),
                "aberto_em": now.isoformat(timespec="seconds"),
                "cliente_verificado": customer_id,
                "pedido": order_id,
                "contato": contact,
            }
            with self.path.open("a", encoding="utf-8") as f:
                f.write(json.dumps(record, ensure_ascii=False) + "\n")
        return record

    def all(self) -> list[dict[str, Any]]:
        if not self.path.exists():
            return []
        with self.path.open(encoding="utf-8") as f:
            return [json.loads(line) for line in f if line.strip()]
