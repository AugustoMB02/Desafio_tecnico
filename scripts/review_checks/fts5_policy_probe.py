"""Reproduce Plan_Review.md §3.2: SQLite FTS5/BM25 over the policy manual's sections.

Builds the index PLAN.md proposes (one row per top-level section §1-§10,
tokenizer `unicode61 remove_diacritics 2`, BM25 ranking) and runs the brief's
own scenario question against it.

Usage:
    python3 scripts/review_checks/fts5_policy_probe.py [PATH_TO_POLICY_PDF]

Needs `pdftotext` (poppler-utils) on PATH. Standard library otherwise.
"""

import re
import sqlite3
import subprocess
import sys
from pathlib import Path

DEFAULT_PDF = Path(__file__).resolve().parents[2] / "políticas_da_loja.pdf"
pdf = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_PDF

try:
    text = subprocess.run(["pdftotext", "-layout", str(pdf), "-"],
                          capture_output=True, text=True, check=True).stdout
except FileNotFoundError:
    sys.exit("pdftotext not found: install poppler-utils (e.g. `sudo apt-get install -y poppler-utils`).")

sections: dict[str, list[str]] = {}
current = None
for line in text.splitlines():
    heading = re.match(r"^(\d{1,2})\. (\S.*)$", line)  # unindented "N. Title" = top-level section
    if heading and int(heading.group(1)) <= 10:
        current = f"§{heading.group(1)} {heading.group(2).strip()}"
        sections[current] = []
    elif current:
        sections[current].append(line)
print(f"sections indexed: {len(sections)}")

db = sqlite3.connect(":memory:")
db.execute("CREATE VIRTUAL TABLE policy USING fts5(title, body, tokenize='unicode61 remove_diacritics 2')")
db.executemany("INSERT INTO policy VALUES (?, ?)", [(k, "\n".join(v)) for k, v in sections.items()])

body = " ".join(" ".join(v) for v in sections.values()).lower()
for word in ("devolver", "devolução", "arrependi ", "arrependimento", "pedido"):
    print(f"  occurrences of {word!r}: {body.count(word)}")

question = "Me arrependi da minha compra, posso devolver meu pedido?"
tokens = re.findall(r"\w+", question.lower())
queries = [
    ("brief's question, default FTS5 syntax (implicit AND)", " ".join(tokens)),
    ("same tokens joined with OR", " OR ".join(tokens)),
    ("keywords a model might write", "devolver pedido"),
    ("keywords a model might write", "arrependi devolver"),
    ("prefix queries", "devol* OR arrepend*"),
]
for label, expr in queries:
    rows = db.execute(
        "SELECT title, round(bm25(policy), 2) FROM policy WHERE policy MATCH ? ORDER BY bm25(policy) LIMIT 3",
        (expr,),
    ).fetchall()
    print(f"\n{label}\n  MATCH {expr!r}\n  -> {rows or 'NO RESULTS'}")
