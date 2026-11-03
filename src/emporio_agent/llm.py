"""Chat model selection through LangChain's `init_chat_model`.

`MODEL` uses the "provider:model" format (e.g. `anthropic:claude-sonnet-5-5`). There is no
default model: running without one fails with a clear message. No `temperature` is sent,
because current Claude models reject non-default sampling parameters.
"""

from __future__ import annotations

import os
from dataclasses import dataclass

from langchain.chat_models import init_chat_model
from langchain_core.language_models import BaseChatModel


class ModelConfigError(RuntimeError):
    pass


@dataclass(frozen=True)
class ModelSpec:
    spec: str
    provider: str

    @property
    def supports_prompt_cache(self) -> bool:
        return self.provider == "anthropic"


def parse_spec(spec: str | None) -> ModelSpec:
    spec = (spec or os.environ.get("MODEL", "")).strip()
    if not spec:
        raise ModelConfigError(
            "Nenhum modelo configurado. Defina MODEL no formato provider:modelo "
            "(ex.: MODEL=anthropic:claude-sonnet-5-5) e a chave do provedor "
            "(ex.: ANTHROPIC_API_KEY) no ambiente ou no arquivo .env."
        )
    if ":" not in spec:
        raise ModelConfigError(f"MODEL deve ter o formato provider:modelo, recebido: {spec!r}")
    return ModelSpec(spec, spec.split(":", 1)[0])


def load_model(spec: str | None = None) -> tuple[BaseChatModel, ModelSpec]:
    parsed = parse_spec(spec)
    kwargs: dict[str, object] = {}
    effort = os.environ.get("MODEL_EFFORT", "").strip()
    if effort and parsed.provider == "anthropic":
        kwargs["effort"] = effort  # Claude 5.x thinks by default; "low" suits chat latency
    return init_chat_model(parsed.spec, **kwargs), parsed
