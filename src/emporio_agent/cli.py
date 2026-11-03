"""Command-line chat with the agent.

uv run emporio-agent                       # interactive chat
uv run emporio-agent --trace               # also print tool calls and results
uv run emporio-agent --now 2026-02-20      # frozen clock for a scripted demo
uv run emporio-agent --script examples/scripts/01.yaml --export examples/01.md
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

import yaml
from dotenv import load_dotenv
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, ToolMessage

from .clock import TZ, Clock
from .data import load_store
from .graph import build_graph
from .llm import ModelConfigError, load_model
from .tools import AgentContext

BANNER = "Empório da Música — Sua música começa aqui. (digite 'sair' para encerrar)"


@dataclass
class ToolCall:
    name: str
    args: dict[str, Any]
    result: str = ""


@dataclass
class Turn:
    user: str
    reply: str = ""
    tool_calls: list[ToolCall] = field(default_factory=list)


def message_text(message: BaseMessage) -> str:
    """Plain text of a message, skipping thinking/tool-use blocks."""
    return message.text.strip()


def collect_turn(user: str, new_messages: list[BaseMessage]) -> Turn:
    turn = Turn(user)
    by_id: dict[str, ToolCall] = {}
    replies = []
    for msg in new_messages:
        if isinstance(msg, AIMessage):
            for call in msg.tool_calls:
                tc = ToolCall(call["name"], call["args"])
                by_id[call["id"]] = tc
                turn.tool_calls.append(tc)
            if text := message_text(msg):
                replies.append(text)
        elif isinstance(msg, ToolMessage) and msg.tool_call_id in by_id:
            by_id[msg.tool_call_id].result = str(msg.content)
    turn.reply = replies[-1] if replies else ""
    return turn


class Session:
    def __init__(self, app: Any, thread_id: str | None = None) -> None:
        self.app = app
        self.config = {"configurable": {"thread_id": thread_id or uuid.uuid4().hex}}
        self.turns: list[Turn] = []

    def send(self, text: str) -> Turn:
        before = len(self.app.get_state(self.config).values.get("messages", []))
        state = self.app.invoke({"messages": [HumanMessage(text)]}, self.config)
        turn = collect_turn(text, state["messages"][before + 1 :])
        self.turns.append(turn)
        return turn


def _short(text: str, limit: int = 600) -> str:
    return text if len(text) <= limit else text[:limit] + " …"


def print_turn(turn: Turn, trace: bool) -> None:
    if trace:
        for tc in turn.tool_calls:
            args = json.dumps(tc.args, ensure_ascii=False)
            print(f"  ⚙ {tc.name}({args})\n    → {_short(tc.result)}")
    print(f"\nEmpório: {turn.reply}\n")


def git_commit() -> str:
    try:
        out = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True, check=True
        )
        return out.stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return "desconhecido"


def transcript_markdown(
    turns: list[Turn], *, title: str, model: str, clock: Clock, notes: str = ""
) -> str:
    generated = datetime.now(TZ).strftime("%d/%m/%Y %H:%M")
    header = [
        f"# {title}",
        "",
        f"- **Modelo:** `{model}`",
        f"- **Gerado em:** {generated} (horário de Campo Grande/MS)",
        f"- **Commit:** `{git_commit()}`",
        "- **Relógio:** "
        + (
            f"simulado em `{clock.now().isoformat()}` (`--now`); "
            "registros posteriores ficam ocultos"
            if clock.is_override
            else "tempo real"
        ),
    ]
    if notes:
        header += ["", notes]
    body = []
    for turn in turns:
        body += ["", f"**Cliente:** {turn.user}", ""]
        if turn.tool_calls:
            body.append("<details><summary>Ferramentas consultadas: "
                        + ", ".join(f"<code>{tc.name}</code>" for tc in turn.tool_calls)
                        + "</summary>")  # fmt: skip
            body.append("")
            for tc in turn.tool_calls:
                body.append(f"- `{tc.name}({json.dumps(tc.args, ensure_ascii=False)})`")
                body.append("")
                body.append("  ```json")
                body.append(f"  {tc.result}")
                body.append("  ```")
            body += ["", "</details>", ""]
        body.append("**Empório da Música:** " + turn.reply.replace("\n", "  \n"))
    return "\n".join(header + body) + "\n"


def load_script(path: Path) -> dict[str, Any]:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict) or not data.get("turns"):
        raise SystemExit(f"{path}: o roteiro precisa de uma lista 'turns'")
    return data


def build_session(model_spec: str | None, now: str | None) -> tuple[Session, str, Clock]:
    model, spec = load_model(model_spec)
    clock = Clock.from_env(now)
    ctx = AgentContext(store=load_store(), clock=clock)
    app = build_graph(model, ctx, cache_prompt=spec.supports_prompt_cache)
    return Session(app), spec.spec, clock


def main(argv: list[str] | None = None) -> int:
    load_dotenv()
    parser = argparse.ArgumentParser(prog="emporio-agent", description=BANNER)
    parser.add_argument("--model", help="provider:modelo (padrão: variável MODEL)")
    parser.add_argument("--now", help="congela o relógio (ISO), ex.: 2026-02-20T10:00")
    parser.add_argument("--trace", action="store_true", help="mostra chamadas de ferramentas")
    parser.add_argument("--script", type=Path, help="roteiro YAML com as falas do cliente")
    parser.add_argument("--export", type=Path, help="salva a conversa em Markdown")
    args = parser.parse_args(argv)

    script = load_script(args.script) if args.script else None
    now = args.now or (script or {}).get("now")
    try:
        session, model_name, clock = build_session(args.model, now)
    except ModelConfigError as exc:
        print(f"Erro de configuração: {exc}", file=sys.stderr)
        return 2

    print(BANNER + "\n")
    if script:
        for text in script["turns"]:
            print(f"Você: {text}")
            print_turn(session.send(text), args.trace)
    else:
        while True:
            try:
                text = input("Você: ").strip()
            except (EOFError, KeyboardInterrupt):
                print()
                break
            if text.lower() in {"sair", "exit", "quit"}:
                break
            if text:
                print_turn(session.send(text), args.trace)

    if args.export and session.turns:
        title = (script or {}).get("title", "Conversa com o agente da Empório da Música")
        md = transcript_markdown(
            session.turns,
            title=title,
            model=model_name,
            clock=clock,
            notes=(script or {}).get("notes", ""),
        )
        args.export.parent.mkdir(parents=True, exist_ok=True)
        args.export.write_text(md, encoding="utf-8")
        print(f"Conversa salva em {args.export}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
