"""The LangGraph agent: one model node in a loop with a ToolNode.

    START → agent ──(tool calls?)──> tools ──> agent ... → END

The verified customer lives in graph state, written only by the verification tool through
`Command(update=...)` and read by the order tools through `InjectedState`; the model never
supplies a customer id.
"""

from __future__ import annotations

import operator
from typing import Annotated, Any, NotRequired, TypedDict

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AnyMessage, SystemMessage
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import START, StateGraph
from langgraph.graph.message import add_messages
from langgraph.prebuilt import ToolNode, tools_condition

from .orders import MAX_VERIFICATION_ATTEMPTS
from .prompts import STATIC_PROMPT, dynamic_context
from .tools import AgentContext, build_tools


class AgentState(TypedDict):
    messages: Annotated[list[AnyMessage], add_messages]
    verified_customer_id: NotRequired[int | None]
    # Summed across tool calls, so parallel failures in one step all count.
    verification_failures: NotRequired[Annotated[int, operator.add]]


def system_message(ctx: AgentContext, state: AgentState, cache: bool) -> SystemMessage:
    cid = state.get("verified_customer_id")
    name = ctx.store.customers[cid].first_name if cid else None
    locked = state.get("verification_failures", 0) >= MAX_VERIFICATION_ATTEMPTS
    dynamic = dynamic_context(ctx.clock, name, locked)
    if cache:  # Anthropic prompt caching: the static block is identical on every call
        return SystemMessage(
            content=[
                {"type": "text", "text": STATIC_PROMPT, "cache_control": {"type": "ephemeral"}},
                {"type": "text", "text": dynamic},
            ]
        )
    return SystemMessage(content=f"{STATIC_PROMPT}\n{dynamic}")


def build_graph(
    model: BaseChatModel,
    ctx: AgentContext,
    *,
    cache_prompt: bool = False,
    checkpointer: BaseCheckpointSaver | None = None,
) -> Any:
    tools = build_tools(ctx)
    bound = model.bind_tools(tools)

    def agent(state: AgentState) -> dict[str, Any]:
        system = system_message(ctx, state, cache_prompt)
        return {"messages": [bound.invoke([system, *state["messages"]])]}

    graph = StateGraph(AgentState)
    graph.add_node("agent", agent)
    graph.add_node("tools", ToolNode(tools))
    graph.add_edge(START, "agent")
    graph.add_conditional_edges("agent", tools_condition)
    graph.add_edge("tools", "agent")
    return graph.compile(checkpointer=checkpointer or InMemorySaver())
