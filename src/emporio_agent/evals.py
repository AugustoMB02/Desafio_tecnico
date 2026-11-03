"""Scripted scenario runner: real agent, scripted user turns, code-graded assertions.

    uv run emporio-evals                       # all scenarios in evals/scenarios.yaml
    uv run emporio-evals --only takamine_preco --report evals/report.md

Each scenario runs in a fresh conversation with its own clock (`now`) and a temporary
ticket file. Per turn it can assert:
- `tools`: tools that must be called in that turn; `no_tools`: tools that must not be;
- `tool_output`: strings that must appear in that turn's tool outputs;
- `reply_any` / `reply_none`: strings the reply must (any of) / must not contain
  (accent- and case-insensitive);
- always: every R$ amount in the reply must appear in a tool output (or in the user's
  own messages) so far in the conversation — the numeric-faithfulness check.

No LLM judge: every check is deterministic. The runs cost API calls, so run it sparingly.
"""

from __future__ import annotations

import argparse
import re
import sys
import tempfile
from collections.abc import Callable
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

import yaml
from dotenv import load_dotenv

from .cli import Session, build_session
from .llm import ModelConfigError, parse_spec
from .text import normalize
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
    """Bare numbers a customer might type as a budget ("até 1000", "1.000")."""
    found = set()
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


@dataclass
class Check:
    ok: bool
    message: str


@dataclass
class ScenarioResult:
    scenario_id: str
    checks: list[tuple[int, Check]] = field(default_factory=list)
    turns: list[TurnRecord] = field(default_factory=list)
    error: str | None = None

    @property
    def passed(self) -> bool:
        return self.error is None and all(c.ok for _, c in self.checks)


def check_turn(expect: dict[str, Any], turn: TurnRecord, history: list[TurnRecord]) -> list[Check]:
    checks: list[Check] = []
    reply = normalize(turn.reply)
    outputs = "\n".join(turn.tool_outputs)

    for name in expect.get("tools", []):
        checks.append(Check(name in turn.tools, f"chamou {name}"))
    for name in expect.get("no_tools", []):
        checks.append(Check(name not in turn.tools, f"não chamou {name}"))
    for text in expect.get("tool_output", []):
        checks.append(Check(text in outputs, f"saída de ferramenta contém {text!r}"))
    if any_of := expect.get("reply_any"):
        hit = any(normalize(t) in reply for t in any_of)
        checks.append(Check(hit, f"resposta contém um de {any_of}"))
    for text in expect.get("reply_none", []):
        checks.append(Check(normalize(text) not in reply, f"resposta não contém {text!r}"))

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


SessionFactory = Callable[[str | None, TicketStore], Session]


def run_scenario(scenario: dict[str, Any], make_session: SessionFactory) -> ScenarioResult:
    """Run one scenario in a fresh conversation with a throwaway ticket file."""
    result = ScenarioResult(scenario["id"])
    try:
        with tempfile.TemporaryDirectory() as tmp:
            session = make_session(scenario.get("now"), TicketStore(Path(tmp) / "t.jsonl"))
            for index, step in enumerate(scenario["turns"], start=1):
                turn = session.send(step["user"])
                record = TurnRecord(
                    step["user"],
                    turn.reply,
                    [tc.name for tc in turn.tool_calls],
                    [tc.result for tc in turn.tool_calls],
                )
                for check in check_turn(step.get("expect", {}), record, result.turns):
                    result.checks.append((index, check))
                result.turns.append(record)
    except Exception as exc:  # report and keep going with the other scenarios
        result.error = f"{type(exc).__name__}: {exc}"
    return result


def render_report(results: list[ScenarioResult]) -> str:
    passed = sum(r.passed for r in results)
    lines = [f"# Cenários: {passed}/{len(results)} passaram", ""]
    for r in results:
        lines.append(f"## {'✅' if r.passed else '❌'} {r.scenario_id}")
        if r.error:
            lines.append(f"- erro: `{r.error}`")
        for index, check in r.checks:
            if not check.ok:
                lines.append(f"- turno {index}: falhou — {check.message}")
        for index, turn in enumerate(r.turns, start=1):
            lines.append(f"\n> **{index}. Cliente:** {turn.user}  \n> ferramentas: "
                         f"{', '.join(turn.tools) or '—'}  \n> **Agente:** "
                         + turn.reply.replace("\n", " "))  # fmt: skip
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
    report = render_report(results)
    if args.report:
        args.report.write_text(report, encoding="utf-8")
    passed = sum(r.passed for r in results)
    print(f"\n{passed}/{len(results)} cenários passaram")
    return 0 if passed == len(results) else 1


if __name__ == "__main__":
    sys.exit(main())
