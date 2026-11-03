"""LangChain tools exposed to the model.

Tools are built by a factory over an `AgentContext` (store, clock, ticket store), so tests
can inject a fixed clock and a temporary ticket file. Every tool returns compact JSON with
pre-formatted values.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date
from typing import Annotated, Any

from langchain_core.messages import AIMessage, ToolMessage
from langchain_core.tools import BaseTool, InjectedToolCallId, tool
from langgraph.prebuilt import InjectedState
from langgraph.types import Command
from pydantic import BaseModel, Field

from . import catalog, orders
from .catalog import CategorySlug, PaymentMethod, StringsType
from .clock import Clock, hours_on, store_status
from .data import Store
from .policy import PolicyTopic, consult_policy


@dataclass(frozen=True)
class AgentContext:
    store: Store
    clock: Clock


def to_json(payload: Any) -> str:
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))


class QuoteItem(BaseModel):
    product_id: int = Field(description="id do produto (de search_catalog ou get_product)")
    quantity: int = Field(default=1, ge=1, description="quantidade")


def _parse_day(text: str, today: date) -> date | None:
    text = text.strip()
    for parse in (
        date.fromisoformat,
        lambda t: date(*reversed([int(x) for x in t.split("/")])),  # dd/mm/aaaa
        lambda t: date(today.year, *reversed([int(x) for x in t.split("/")])),  # dd/mm
    ):
        try:
            return parse(text)
        except (ValueError, TypeError):
            continue
    return None


def catalog_tools(ctx: AgentContext) -> list[BaseTool]:
    store = ctx.store

    @tool
    def search_catalog(
        query: Annotated[
            str | None, "palavras do nome/modelo/estilo, ex.: 'dreadnought', 'folk', 'Yamaha'"
        ] = None,
        category: CategorySlug | None = None,
        min_price_brl: Annotated[float | None, "preço mínimo em reais"] = None,
        max_price_brl: Annotated[float | None, "preço máximo em reais (orçamento)"] = None,
        strings: Annotated[StringsType | None, "tipo de corda (violões e ukuleles)"] = None,
        electronics: Annotated[bool | None, "True = eletroacústico / com captação"] = None,
        limit: Annotated[int, "máximo de itens a devolver (1 a 10)"] = 5,
    ) -> str:
        """Busca instrumentos DISPONÍVEIS no catálogo (ativos e com estoque), do mais barato
        para o mais caro, com preço, promoção ativa, preço no PIX e parcelamento máximo.
        Use para perguntas como "quais violões até R$ 1.000?" ou "tem saxofone?". Informa
        quando uma categoria da loja está sem itens e quando um item só cabe no orçamento
        pagando no PIX."""
        return to_json(
            catalog.search_catalog(
                store,
                query=query,
                category=category,
                min_price_brl=min_price_brl,
                max_price_brl=max_price_brl,
                strings=strings,
                electronics=electronics,
                limit=limit,
            )
        )

    @tool
    def get_product(
        product: Annotated[str, "id do produto ou nome/modelo, ex.: 'Takamine GD20'"],
    ) -> str:
        """Detalhes de um produto específico, em qualquer situação (disponível, sem estoque,
        descontinuado ou em breve): preço atual, PIX, parcelamento, ficha técnica,
        alternativas quando indisponível e alertas de cadastro. Use para "quanto custa o X?"
        ou "tem o X?". Se o nome for ambíguo, devolve candidatos para o cliente escolher."""
        return to_json(catalog.get_product(store, product))

    @tool
    def quote(
        items: list[QuoteItem],
        payment: Annotated[PaymentMethod | None, "forma de pagamento, se o cliente disse"] = None,
        installments: Annotated[int | None, "número de parcelas pedido pelo cliente"] = None,
        city: Annotated[str | None, "cidade de entrega, se o cliente disse"] = None,
    ) -> str:
        """Orçamento calculado pelo sistema para um ou mais produtos (por id): valor de cada
        item (com promoção ativa), total, total no PIX (5% só nos itens sem promoção),
        parcelamento permitido e frete para a cidade. Use sempre que o cliente perguntar
        quanto fica, em quantas vezes, quanto no PIX ou quanto é o frete."""
        return to_json(
            catalog.quote(
                store,
                [i.model_dump() for i in items],
                payment=payment,
                installments=installments,
                city=city,
            )
        )

    return [search_catalog, get_product, quote]


def store_info_tools(ctx: AgentContext) -> list[BaseTool]:
    @tool("consult_policy")
    def consult_policy_tool(topics: list[PolicyTopic]) -> str:
        """Consulta o manual de políticas da loja e devolve as seções inteiras dos tópicos
        pedidos, com notas de interpretação. Use para endereço, contatos, horários, formas de
        pagamento e parcelamento, trocas e devoluções, frete, promoções, garantia e LGPD."""
        return to_json(consult_policy(list(topics)))

    @tool
    def check_store_hours(
        day: Annotated[str | None, "data perguntada (dd/mm/aaaa, dd/mm ou aaaa-mm-dd)"] = None,
    ) -> str:
        """Diz se a loja está aberta agora e o horário de um dia específico, já
        considerando domingos e feriados nacionais e de MS. Use para "vocês estão abertos?"
        ou "abrem dia 20/11?"."""
        now = ctx.clock.now()
        result: dict[str, Any] = {"agora": store_status(now).describe()}
        if day:
            parsed = _parse_day(day, now.date())
            result["dia_consultado"] = (
                hours_on(parsed).describe() if parsed else f"data não reconhecida: {day}"
            )
        else:
            result["proximos_dias"] = [
                hours_on(date.fromordinal(now.date().toordinal() + i)).describe() for i in range(7)
            ]
        return to_json(result)

    return [consult_policy_tool, check_store_hours]


NOT_VERIFIED = {
    "erro": "cliente não verificado: use verify_customer com dois dados (pedido, e-mail, "
    "telefone) antes de consultar pedidos"
}


def _reply(tool_call_id: str, payload: Any, **update: Any) -> Command:
    message = ToolMessage(to_json(payload), tool_call_id=tool_call_id)
    return Command(update={**update, "messages": [message]})


def _is_first_call(state: dict[str, Any], tool_name: str, tool_call_id: str) -> bool:
    """Whether this is the first call to `tool_name` in the model's latest message."""
    last_ai = next((m for m in reversed(state["messages"]) if isinstance(m, AIMessage)), None)
    if last_ai is None:
        return True
    ids = [c["id"] for c in last_ai.tool_calls if c["name"] == tool_name]
    return not ids or ids[0] == tool_call_id


def order_tools(ctx: AgentContext) -> list[BaseTool]:
    store = ctx.store

    @tool
    def verify_customer(
        state: Annotated[dict, InjectedState],
        tool_call_id: Annotated[str, InjectedToolCallId],
        order_id: Annotated[int | None, "número do pedido"] = None,
        email: Annotated[str | None, "e-mail do cliente"] = None,
        phone: Annotated[str | None, "telefone do cliente, com DDD"] = None,
    ) -> Command:
        """Verifica a identidade do cliente com DOIS destes dados: número do pedido, e-mail,
        telefone. Obrigatório antes de mostrar qualquer pedido. Se der certo, já devolve os
        pedidos do cliente. Nunca diga qual dado estava errado. Bloqueia após 3 falhas."""
        today = ctx.clock.today()
        failures = state.get("verification_failures", 0)
        if failures >= orders.MAX_VERIFICATION_ATTEMPTS:
            return _reply(tool_call_id, {"erro": "verificação bloqueada nesta conversa após 3 "
                          "tentativas; ofereça atendimento humano (open_ticket)"})  # fmt: skip
        if not _is_first_call(state, "verify_customer", tool_call_id):
            return _reply(tool_call_id, {"erro": "uma verificação por vez; aguarde o resultado"})
        result = orders.verify(store, today, order_id=order_id, email=email, phone=phone)
        if result.error:
            return _reply(tool_call_id, {"erro": result.error})
        if not result.ok:
            left = orders.MAX_VERIFICATION_ATTEMPTS - failures - 1
            payload = {"verificado": False, "mensagem": orders.GENERIC_FAILURE,
                       "tentativas_restantes": left}  # fmt: skip
            return _reply(tool_call_id, payload, verification_failures=1)
        customer = result.customer
        assert customer is not None
        found = orders.customer_orders(store, customer.customer_id, today)
        payload = {
            "verificado": True,
            "primeiro_nome": customer.first_name,
            "pedidos": [orders.order_summary(store, o, today) for o in found]
            or "nenhum pedido encontrado para este cliente",
        }
        return _reply(tool_call_id, payload, verified_customer_id=customer.customer_id)

    @tool
    def get_my_orders(
        state: Annotated[dict, InjectedState],
        order_id: Annotated[int | None, "um pedido específico; vazio = todos"] = None,
    ) -> str:
        """Pedidos do cliente JÁ VERIFICADO nesta conversa: status, itens, valor pago,
        rastreio, previsão de entrega e alertas (atraso, pedido parado)."""
        cid = state.get("verified_customer_id")
        if not cid:
            return to_json(NOT_VERIFIED)
        today = ctx.clock.today()
        found = orders.customer_orders(store, cid, today)
        if order_id is not None:
            found = [o for o in found if o.order_id == int(order_id)]
            if not found:
                return to_json({"erro": "esse pedido não está entre os pedidos deste cliente"})
        return to_json({"pedidos": [orders.order_summary(store, o, today) for o in found]})

    return [verify_customer, get_my_orders]


def build_tools(ctx: AgentContext) -> list[BaseTool]:
    return [*catalog_tools(ctx), *store_info_tools(ctx), *order_tools(ctx)]
