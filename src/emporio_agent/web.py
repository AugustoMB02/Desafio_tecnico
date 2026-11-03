"""Web chat for the agent, in pure Python (Gradio).

    uv run emporio-web                      # http://127.0.0.1:7860
    uv run emporio-web --now 2026-02-20     # frozen clock, as in the CLI
    uv run emporio-web --hide-tools         # customer view, without the tool steps

Each browser session gets its own agent conversation (same graph, tools and rules as the
CLI). Tool calls appear as collapsible steps under the reply, so an evaluator can see which
data or policy the agent consulted; `--hide-tools` shows only the customer-facing text.
"""

from __future__ import annotations

import argparse
import json
import sys
import threading
from collections.abc import Callable
from typing import Any

import gradio as gr
from dotenv import load_dotenv

from .cli import Session, Turn, build_session, describe_error
from .llm import ModelConfigError, parse_spec

TITLE = "🎸 Empório da Música"
DESCRIPTION = (
    "**Sua música começa aqui.** Assistente virtual da loja de instrumentos de Campo "
    "Grande/MS: preços, estoque, pedidos, trocas, frete e horários."
)
EXAMPLES = [
    "Quais opções de violões disponíveis custando até R$1000?",
    "Qual o endereço da loja?",
    "Quanto custa o Takamine GD20?",
    "Me arrependi da minha compra, posso devolver meu pedido?",
]
SessionFactory = Callable[[], Session]


def turn_messages(turn: Turn, show_tools: bool = True) -> list[gr.ChatMessage]:
    """The agent's reply, preceded by one collapsible step per tool call."""
    messages = []
    if show_tools:
        for tc in turn.tool_calls:
            args = json.dumps(tc.args, ensure_ascii=False)
            messages.append(
                gr.ChatMessage(
                    role="assistant",
                    content=f"```json\n{tc.result}\n```",
                    metadata={"title": f"⚙ {tc.name}({args})", "status": "done"},
                )
            )
    messages.append(gr.ChatMessage(role="assistant", content=turn.reply or "…"))
    return messages


class WebSessions:
    """One agent conversation per browser session; a cleared chat starts a new one."""

    def __init__(self, factory: SessionFactory) -> None:
        self._factory = factory
        self._sessions: dict[str, Session] = {}
        self._lock = threading.Lock()

    def get(self, key: str, *, fresh: bool) -> Session:
        with self._lock:
            if fresh or key not in self._sessions:
                self._sessions[key] = self._factory()
            return self._sessions[key]


def make_responder(
    factory: SessionFactory, show_tools: bool = True
) -> Callable[..., list[gr.ChatMessage]]:
    sessions = WebSessions(factory)

    def respond(
        message: str, history: list[Any], request: gr.Request | None = None
    ) -> list[gr.ChatMessage]:
        key = getattr(request, "session_hash", None) or "local"
        session = sessions.get(key, fresh=not history)
        try:
            turn = session.send(message)
        except Exception as exc:  # quota, billing, network: tell the customer, keep the app up
            print(f"[erro ao chamar o modelo] {describe_error(exc)}", file=sys.stderr)
            return [
                gr.ChatMessage(
                    role="assistant",
                    content="Desculpe, não consegui responder agora. Pode tentar de novo em "
                    "instantes?",
                )
            ]
        return turn_messages(turn, show_tools)

    return respond


def build_app(factory: SessionFactory, show_tools: bool = True) -> gr.ChatInterface:
    return gr.ChatInterface(
        make_responder(factory, show_tools),
        title=TITLE,
        description=DESCRIPTION,
        examples=EXAMPLES,
        cache_examples=False,
        chatbot=gr.Chatbot(
            show_label=False,
            height=560,
            placeholder="Olá! Em que posso ajudar hoje? 🎶",
            group_consecutive_messages=True,
        ),
        textbox=gr.Textbox(placeholder="Escreva sua mensagem…", submit_btn=True),
        autofocus=True,
    )


def main(argv: list[str] | None = None) -> int:
    load_dotenv()
    parser = argparse.ArgumentParser(prog="emporio-web", description=DESCRIPTION)
    parser.add_argument("--model", help="provider:modelo (padrão: variável MODEL)")
    parser.add_argument("--now", help="congela o relógio (ISO), ex.: 2026-02-20T10:00")
    parser.add_argument("--port", type=int, default=7860)
    parser.add_argument("--hide-tools", action="store_true", help="esconde as ferramentas")
    args = parser.parse_args(argv)
    try:
        parse_spec(args.model)
    except ModelConfigError as exc:
        print(f"Erro de configuração: {exc}", file=sys.stderr)
        return 2

    def factory() -> Session:
        return build_session(args.model, args.now)[0]

    app = build_app(factory, show_tools=not args.hide_tools)
    app.launch(
        server_port=args.port,
        theme=gr.themes.Soft(primary_hue="amber", secondary_hue="teal"),
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
