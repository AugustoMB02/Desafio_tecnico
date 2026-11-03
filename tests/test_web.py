"""The Gradio web chat, driven by the scripted fake model (no server, no API calls)."""

import gradio as gr

from emporio_agent.cli import Session
from emporio_agent.clock import Clock, parse_now
from emporio_agent.data import load_store
from emporio_agent.graph import build_graph
from emporio_agent.tools import AgentContext
from emporio_agent.web import build_app, make_responder

from .fakes import ai, call, scripted


class FakeRequest:
    def __init__(self, session_hash: str) -> None:
        self.session_hash = session_hash


def factory_for(*models):
    queue = list(models)

    def factory() -> Session:
        ctx = AgentContext(load_store(), Clock(parse_now("2026-11-04T10:00")))
        return Session(build_graph(queue.pop(0), ctx))

    return factory


def test_reply_shows_tool_steps_then_the_answer():
    model = scripted(
        ai("", call("get_product", product="Takamine GD20")),
        ai("Sai por R$ 2.199,00."),
    )
    respond = make_responder(factory_for(model))
    tool_step, answer = respond("Quanto custa o Takamine GD20?", [], FakeRequest("a"))
    assert tool_step.metadata["title"].startswith("⚙ get_product")
    assert "R$ 2.199,00" in tool_step.content
    assert answer.content == "Sai por R$ 2.199,00."


def test_hide_tools_shows_only_the_answer():
    model = scripted(ai("", call("get_product", product="81")), ai("Pronto."))
    [answer] = make_responder(factory_for(model), show_tools=False)("oi", [], FakeRequest("a"))
    assert answer.content == "Pronto."


def test_each_browser_session_has_its_own_conversation():
    respond = make_responder(factory_for(scripted(ai("Oi, A!")), scripted(ai("Oi, B!"))))
    assert respond("oi", [], FakeRequest("a"))[-1].content == "Oi, A!"
    assert respond("oi", [], FakeRequest("b"))[-1].content == "Oi, B!"


def test_model_errors_become_a_friendly_message():
    class Broken(type(scripted())):
        def invoke(self, input, config=None, **kwargs):
            raise RuntimeError("503 UNAVAILABLE")

    [answer] = make_responder(factory_for(Broken(messages=iter([]))))("oi", [], None)
    assert "não consegui responder agora" in answer.content


def test_app_builds_without_launching():
    app = build_app(factory_for(scripted(ai("oi"))))
    assert isinstance(app, gr.ChatInterface)
