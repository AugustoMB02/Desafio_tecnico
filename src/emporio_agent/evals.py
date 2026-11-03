"""Scripted scenario runner: real agent, scripted user turns, code-graded assertions.

    uv run emporio-evals                       # all scenarios in evals/scenarios.yaml
    uv run emporio-evals --only takamine_preco --report evals/report.md

Each scenario runs in a fresh conversation with its own clock (`now`) and a temporary
ticket file. Expectations can be set per turn (`turns[i].expect`) or for the whole
conversation (`expect` at scenario level, for things the agent may do in any turn):
- `tools`: tools that must be called; `no_tools`: tools that must not be;
- `tool_output`: strings that must appear in the tool outputs;
- `reply_any` / `reply_none`: strings the reply must (any of) / must not contain
  (ignoring accents, case and spacing; punctuation counts, so "12%" never matches "12x");
- `reply_all`: every item must appear; an item that is a list is satisfied by any of its
  strings (for messages with several questions, where each needs its own answer);
- always, per turn: every R$ amount in the reply must appear in a tool output (or in the
  user's own messages) so far in the conversation — the numeric-faithfulness check.

No LLM judge: every check is deterministic. The runs cost API calls, so run it sparingly.
"""

from __future__ import annotations

import argparse
import os
import re
import statistics
import sys
import tempfile
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

import yaml
from dotenv import load_dotenv

from .cli import Session, build_session
from .llm import ModelConfigError, parse_spec
from .text import strip_accents
from .tickets import TicketStore

DEFAULT_SCENARIOS = Path(__file__).resolve().parents[2] / "evals" / "scenarios.yaml"
_MONEY = re.compile(r"R\$\s?(\d{1,3}(?:\.\d{3})*(?:,\d{2})?|\d+(?:,\d{2})?)")


def money_values(text: str) -> set[Decimal]:
    """All R$ amounts in a text, as Decimals ("R$ 1.967,18" -> 1967.18)."""
    values = set()
    for raw in _MONEY.findall(text):
        try:
            values.add(Decimal(raw.replace(".", "").replace(",", ".")))
        except InvalidOperation:
            continue
    return values


def plain_numbers(text: str) -> set[Decimal]:
    """Bare numbers a customer might type as a budget ("até 1000", "1.000", "2 mil", "2k")."""
    found = set()
    for number, _unit in re.findall(r"(\d+(?:[.,]\d+)?)\s*(mil|k)\b", text, flags=re.I):
        found.add(Decimal(number.replace(",", ".")) * 1000)
    for raw in re.findall(r"\d[\d.,]*", text):
        cleaned = raw.rstrip(".,")
        if "," in cleaned:
            cleaned = cleaned.replace(".", "").replace(",", ".")
        elif re.fullmatch(r"\d{1,3}(\.\d{3})+", cleaned):
            cleaned = cleaned.replace(".", "")
        try:
            found.add(Decimal(cleaned))
        except InvalidOperation:
            continue
    return found


@dataclass
class TurnRecord:
    user: str
    reply: str
    tools: list[str]
    tool_outputs: list[str]
    seconds: float = 0.0


def fold(text: str) -> str:
    """Accent-, case- and spacing-insensitive form that keeps punctuation."""
    return " ".join(strip_accents(text).lower().split())


@dataclass
class Check:
    ok: bool
    message: str


@dataclass
class ScenarioResult:
    scenario_id: str
    note: str = ""
    checks: list[tuple[int, Check]] = field(default_factory=list)
    turns: list[TurnRecord] = field(default_factory=list)
    error: str | None = None

    @property
    def passed(self) -> bool:
        return self.error is None and all(c.ok for _, c in self.checks)


def check_expectations(
    expect: dict[str, Any], tools: list[str], outputs: str, reply: str
) -> list[Check]:
    checks: list[Check] = []
    folded = fold(reply)
    for name in expect.get("tools", []):
        checks.append(Check(name in tools, f"chamou {name}"))
    for name in expect.get("no_tools", []):
        checks.append(Check(name not in tools, f"não chamou {name}"))
    for text in expect.get("tool_output", []):
        checks.append(Check(text in outputs, f"saída de ferramenta contém {text!r}"))
    if any_of := expect.get("reply_any"):
        hit = any(fold(t) in folded for t in any_of)
        checks.append(Check(hit, f"resposta contém um de {any_of}"))
    for text in expect.get("reply_none", []):
        checks.append(Check(fold(text) not in folded, f"resposta não contém {text!r}"))
    for item in expect.get("reply_all", []):
        options = item if isinstance(item, list) else [item]
        hit = any(fold(o) in folded for o in options)
        label = repr(options[0]) if len(options) == 1 else f"um de {options}"
        checks.append(Check(hit, f"resposta contém {label}"))
    return checks


def check_turn(expect: dict[str, Any], turn: TurnRecord, history: list[TurnRecord]) -> list[Check]:
    checks = check_expectations(expect, turn.tools, "\n".join(turn.tool_outputs), turn.reply)
    grounded = set()
    for past in [*history, turn]:
        for out in past.tool_outputs:
            grounded |= money_values(out)
        grounded |= money_values(past.user) | plain_numbers(past.user)
    ungrounded = sorted(money_values(turn.reply) - grounded)
    checks.append(
        Check(not ungrounded, "todo R$ da resposta veio de uma ferramenta"
              + (f" (sem origem: {', '.join(map(str, ungrounded))})" if ungrounded else ""))
    )  # fmt: skip
    return checks


def check_conversation(expect: dict[str, Any], turns: list[TurnRecord]) -> list[Check]:
    """Expectations over the whole conversation (any turn may satisfy them)."""
    tools = [name for t in turns for name in t.tools]
    outputs = "\n".join(out for t in turns for out in t.tool_outputs)
    replies = "\n".join(t.reply for t in turns)
    return check_expectations(expect, tools, outputs, replies)


SessionFactory = Callable[[str | None, TicketStore], Session]


def run_scenario(scenario: dict[str, Any], make_session: SessionFactory) -> ScenarioResult:
    """Run one scenario in a fresh conversation with a throwaway ticket file."""
    result = ScenarioResult(scenario["id"], scenario.get("nota", ""))
    try:
        with tempfile.TemporaryDirectory() as tmp:
            session = make_session(scenario.get("now"), TicketStore(Path(tmp) / "t.jsonl"))
            for index, step in enumerate(scenario["turns"], start=1):
                started = time.perf_counter()
                turn = session.send(step["user"])
                record = TurnRecord(
                    step["user"],
                    turn.reply,
                    [tc.name for tc in turn.tool_calls],
                    [tc.result for tc in turn.tool_calls],
                    time.perf_counter() - started,
                )
                for check in check_turn(step.get("expect", {}), record, result.turns):
                    result.checks.append((index, check))
                result.turns.append(record)
            for check in check_conversation(scenario.get("expect", {}), result.turns):
                result.checks.append((0, check))  # 0 = the whole conversation
    except Exception as exc:  # report and keep going with the other scenarios
        result.error = f"{type(exc).__name__}: {exc}"
    return result


def latency_summary(results: list[ScenarioResult]) -> str:
    seconds = sorted(t.seconds for r in results for t in r.turns if t.seconds)
    if not seconds:
        return ""
    p90 = seconds[min(len(seconds) - 1, round(0.9 * (len(seconds) - 1)))]
    return (
        f"Tempo de resposta por mensagem ({len(seconds)} mensagens): mediana "
        f"{statistics.median(seconds):.1f} s, p90 {p90:.1f} s, máximo {seconds[-1]:.1f} s."
    )


def render_report(results: list[ScenarioResult], model: str = "") -> str:
    passed = sum(r.passed for r in results)
    lines = [f"# Cenários: {passed}/{len(results)} passaram", ""]
    if model:
        lines.append(f"Modelo: `{model}`. Gerado por `uv run emporio-evals --report`.  ")
    if summary := latency_summary(results):
        lines.append(summary)
    lines.append("")
    for r in results:
        lines.append(f"## {'✅' if r.passed else '❌'} {r.scenario_id}")
        if r.note:
            lines.append(f"*{r.note}*\n")
        if r.error:
            lines.append(f"- erro: `{r.error}`")
        for index, check in r.checks:
            if not check.ok:
                where = f"turno {index}" if index else "conversa"
                lines.append(f"- {where}: falhou — {check.message}")
        for index, turn in enumerate(r.turns, start=1):
            lines.append(f"\n> **{index}. Cliente:** {turn.user}  \n> ferramentas: "
                         f"{', '.join(turn.tools) or '—'} ({turn.seconds:.1f} s)  \n"
                         "> **Agente:** " + turn.reply.replace("\n", " "))  # fmt: skip
        lines.append("")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    load_dotenv()
    parser = argparse.ArgumentParser(prog="emporio-evals")
    parser.add_argument("scenarios", nargs="?", type=Path, default=DEFAULT_SCENARIOS)
    parser.add_argument("--only", action="append", help="id do cenário (pode repetir)")
    parser.add_argument("--model", help="provider:modelo (padrão: variável MODEL)")
    parser.add_argument("--report", type=Path, help="salva o relatório em Markdown")
    args = parser.parse_args(argv)

    def real_session(now: str | None, tickets: TicketStore) -> Session:
        return build_session(args.model, now, tickets)[0]

    try:
        parse_spec(args.model)
    except ModelConfigError as exc:
        print(f"Erro de configuração: {exc}", file=sys.stderr)
        return 2
    scenarios = yaml.safe_load(args.scenarios.read_text(encoding="utf-8"))["scenarios"]
    if args.only:
        scenarios = [s for s in scenarios if s["id"] in args.only]
    results = []
    for scenario in scenarios:
        result = run_scenario(scenario, real_session)
        results.append(result)
        failed = [c.message for _, c in result.checks if not c.ok]
        status = "ok " if result.passed else "FALHOU"
        print(f"[{status}] {scenario['id']}: {result.error or '; '.join(failed) or 'tudo certo'}")
    report = render_report(results, model=args.model or os.environ.get("MODEL", ""))
    if args.report:
        args.report.write_text(report, encoding="utf-8")
    passed = sum(r.passed for r in results)
    print(f"\n{passed}/{len(results)} cenários passaram")
    return 0 if passed == len(results) else 1


if __name__ == "__main__":
    sys.exit(main())
