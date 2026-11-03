"""Return / exchange / warranty eligibility for one order (§4, §8).

Branches on order status first: an order that has not arrived cannot be "returned" — that
is a cancellation request, and the manual has no cancellation policy, so it is escalated.

ASSUMPTIONS (also in the README):
- orders in the system are remote purchases, so §4.1 (online) applies;
- the receipt date is the recorded `estimated_delivery` unless the customer says otherwise;
- the §4.3 7-day preference window counts from receipt, like §4.1;
- day 0 is the day of receipt/purchase ("até 7 dias corridos" = today - receipt <= 7).
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any, Literal

from .data import Order, OrderStatus, Store
from .money import fmt_date

ReturnReason = Literal["arrependimento", "defeito", "preferencia"]

REGRET_DAYS = 7  # §4.1
PREFERENCE_DAYS = 7  # §4.3
DEFECT_EXCHANGE_DAYS = 30  # §4.2, from purchase
LEGAL_WARRANTY_DAYS = 90  # §8.1, from receipt

NOT_ELIGIBLE_ITEMS = [  # §4.4: confirm with the customer, the data cannot tell
    "instrumento com personalização ou ajuste sob encomenda (setup, regulagem especial)",
    'compra em liquidação com aviso explícito de "venda final"',
]
DEFECT_EXCLUSIONS = [  # §4.2 and §8.3
    "danos por mau uso, quedas, umidade excessiva ou condições climáticas extremas",
    "modificações ou reparos feitos por terceiros não autorizados",
    "desgaste natural de peças (trastes, cordas, feltros) e danos só estéticos",
]


def check_return(
    store: Store,
    order: Order,
    today: date,
    reason: ReturnReason,
    received_on: date | None = None,
) -> dict[str, Any]:
    result: dict[str, Any] = {"pedido": order.order_id, "motivo": reason}

    if order.status is OrderStatus.CANCELLED:
        result.update(
            elegivel=False,
            situacao="o pedido foi cancelado; não há produto para devolver",
            proximo_passo="se o cliente relatar cobrança indevida, abrir chamado de reclamação",
        )
        return result

    if order.status in (OrderStatus.PENDING, OrderStatus.CONFIRMED) or (
        order.status is OrderStatus.SHIPPED and received_on is None
    ):
        situacao = (
            "o pedido está a caminho e ainda não foi recebido"
            if order.status is OrderStatus.SHIPPED
            else "o pedido ainda não foi enviado"
        )
        result.update(
            elegivel=None,
            situacao=situacao,
            caminho="cancelamento",
            regra=(
                "o manual não tem política de cancelamento; o prazo de arrependimento só começa "
                "no recebimento. Registre um chamado de cancelamento para a equipe analisar, "
                "sem prometer resultado nem prazo de estorno."
            ),
            proximo_passo="confirmar com o cliente e abrir chamado do tipo 'cancelamento'",
        )
        if order.status is OrderStatus.SHIPPED:
            result["observacao"] = (
                "se o cliente já recebeu, peça a data de recebimento e consulte de novo"
            )
        return result

    receipt = received_on or order.estimated_delivery
    if receipt is None:
        result.update(elegivel=None, situacao="sem data de recebimento: pergunte ao cliente")
        return result
    if receipt > today or receipt < order.order_date:
        result.update(elegivel=None, situacao="data de recebimento inválida para este pedido")
        return result

    since_receipt = (today - receipt).days
    since_purchase = (today - order.order_date).days
    result["datas"] = {
        "compra": fmt_date(order.order_date),
        "recebimento": fmt_date(receipt)
        + ("" if received_on else " (previsão de entrega registrada; confirme com o cliente)"),
        "hoje": fmt_date(today),
        "dias_desde_o_recebimento": since_receipt,
        "dias_desde_a_compra": since_purchase,
    }

    if reason == "arrependimento":
        deadline = receipt + timedelta(days=REGRET_DAYS)
        if since_receipt <= REGRET_DAYS:
            result.update(
                elegivel=True,
                regra=f"direito de arrependimento (seção 4.1): até {fmt_date(deadline)}",
                condicoes=[
                    "produto na embalagem original, sem sinais de uso, com acessórios e manuais",
                    "reembolso na mesma forma de pagamento em até 10 dias úteis",
                    "frete de devolução por conta da loja",
                ],
                verificar_com_cliente=NOT_ELIGIBLE_ITEMS,
                proximo_passo="confirmar com o cliente e abrir chamado do tipo 'devolucao'",
            )
        else:
            result.update(
                elegivel=False,
                regra=(
                    f"o prazo de arrependimento (7 dias após o recebimento) terminou em "
                    f"{fmt_date(deadline)}"
                ),
                alternativa=(
                    "se o instrumento tiver defeito de fabricação, consulte de novo com "
                    "motivo 'defeito' (garantia)"
                ),
            )
        return result

    if reason == "preferencia":
        deadline = receipt + timedelta(days=PREFERENCE_DAYS)
        if since_receipt <= PREFERENCE_DAYS:
            result.update(
                elegivel=True,
                regra=f"troca por preferência (seção 4.3): até {fmt_date(deadline)}",
                condicoes=[
                    "sujeita à disponibilidade do produto desejado (consulte o catálogo)",
                    "produto em perfeito estado e na embalagem original",
                    "diferenças de valor são cobradas ou reembolsadas",
                ],
                verificar_com_cliente=NOT_ELIGIBLE_ITEMS,
                proximo_passo="confirmar o produto desejado e abrir chamado do tipo 'troca'",
            )
        else:
            result.update(
                elegivel=False,
                regra=f"a troca por preferência (7 dias) terminou em {fmt_date(deadline)}",
            )
        return result

    # defeito
    exchange_until = order.order_date + timedelta(days=DEFECT_EXCHANGE_DAYS)
    legal_until = receipt + timedelta(days=LEGAL_WARRANTY_DAYS)
    if since_purchase <= DEFECT_EXCHANGE_DAYS:
        result.update(
            elegivel=True,
            caminho="troca direta na loja",
            regra=f"troca por defeito de fabricação (seção 4.2): até {fmt_date(exchange_until)}",
        )
    elif since_receipt <= LEGAL_WARRANTY_DAYS:
        result.update(
            elegivel=True,
            caminho="garantia legal (seção 8.1), acionada com o fabricante",
            regra=(
                f"passou dos 30 dias da troca direta, mas a garantia legal de 90 dias vale até "
                f"{fmt_date(legal_until)}; a loja pode intermediar"
            ),
        )
    else:
        result.update(
            elegivel=None,
            caminho="garantia do fabricante (seção 8.2)",
            regra=(
                f"a troca direta (30 dias) e a garantia legal (90 dias, até "
                f"{fmt_date(legal_until)}) terminaram; a garantia do fabricante costuma ir de "
                "6 meses a 2 anos e depende do certificado do produto. A loja pode intermediar."
            ),
        )
    result["nao_coberto"] = DEFECT_EXCLUSIONS
    result["proximo_passo"] = (
        "pedir uma descrição do defeito, confirmar e abrir chamado do tipo 'garantia'"
    )
    return result
