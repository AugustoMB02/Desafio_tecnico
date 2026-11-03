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

from langchain_core.tools import BaseTool, tool
from pydantic import BaseModel, Field

from . import catalog
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


def build_tools(ctx: AgentContext) -> list[BaseTool]:
    return [*catalog_tools(ctx), *store_info_tools(ctx)]
