"""Conversation persistence: named threads stored in SQLite under `.state/`.

Without a session name the CLI keeps the conversation in memory, as before. With
`--session <nome>` every step is checkpointed to `.state/conversas.sqlite`, so the customer
can close the chat and continue later — like a WhatsApp thread that lives on the same
phone number. The file is gitignored: after verification it holds personal data.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

from langgraph.checkpoint.sqlite import SqliteSaver

DEFAULT_DB = Path(__file__).resolve().parents[2] / ".state" / "conversas.sqlite"


def sqlite_checkpointer(path: Path | str = DEFAULT_DB) -> SqliteSaver:
    """A SQLite checkpointer; one connection shared by the graph (SqliteSaver locks it)."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path, check_same_thread=False)
    return SqliteSaver(conn)
