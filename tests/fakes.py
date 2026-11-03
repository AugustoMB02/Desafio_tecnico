"""A scripted chat model for running the real graph without an LLM."""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

from langchain_core.language_models.fake_chat_models import GenericFakeChatModel
from langchain_core.messages import AIMessage
from pydantic import Field


class ScriptedChatModel(GenericFakeChatModel):
    """Replays AIMessages in order and records every prompt it was given."""

    seen: list[list[Any]] = Field(default_factory=list)

    def bind_tools(self, tools: Any, **kwargs: Any) -> ScriptedChatModel:
        return self

    def invoke(self, input: Any, config: Any = None, **kwargs: Any) -> Any:
        self.seen.append(list(input))
        return super().invoke(input, config, **kwargs)


def scripted(*messages: AIMessage) -> ScriptedChatModel:
    iterator: Iterator[AIMessage] = iter(messages)
    return ScriptedChatModel(messages=iterator, seen=[])


def call(name: str, call_id: str = "c1", **args: Any) -> dict[str, Any]:
    return {"name": name, "args": args, "id": call_id, "type": "tool_call"}


def ai(text: str = "", *calls: dict[str, Any]) -> AIMessage:
    return AIMessage(content=text, tool_calls=list(calls))
