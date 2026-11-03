"""Customer verification and order summaries.

Verification needs two of: order id, e-mail, phone. The whole tuple must match one
customer, so the e-mail shared by customers 11 and 43 never binds the wrong person.
Failures are generic (they never say which factor was wrong) and capped per conversation.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any

from .data import Customer, Order, OrderStatus, Store
from .money import fmt_brl, fmt_date
from .text import digits

STATUS_PT = {
    OrderStatus.PENDING: "pendente (aguardando processamento)",
    OrderStatus.CONFIRMED: "confirmado (em separação, ainda não enviado)",
    OrderStatus.SHIPPED: "enviado",
    OrderStatus.DELIVERED: "entregue",
    OrderStatus.CANCELLED: "cancelado",
}
GENERIC_FAILURE = (
    "Não foi possível confirmar a identidade com os dados informados. Peça ao cliente para "
    "conferir os dados (sem dizer qual estava errado)."
)
STALE_DAYS = 7
MAX_VERIFICATION_ATTEMPTS = 3


def visible_orders(store: Store, today: date) -> dict[int, Order]:
    """Orders that exist at `today` (a frozen clock hides orders placed after it)."""
    return {oid: o for oid, o in store.orders.items() if o.order_date <= today}


def normalize_phone(phone: str) -> str:
    """Digits with DDD; accepts +55 and a bare 9-digit number (DDD 67 assumed)."""
    d = digits(phone)
    if len(d) == 13 and d.startswith("55"):
        d = d[2:]
    if len(d) == 9:
        d = "67" + d
    return d


@dataclass(frozen=True)
class VerificationResult:
    customer: Customer | None
    error: str | None = None  # input problem: not counted as a failed attempt

    @property
    def ok(self) -> bool:
        return self.customer is not None


def verify(
    store: Store,
    today: date,
    *,
    order_id: int | None = None,
    email: str | None = None,
    phone: str | None = None,
) -> VerificationResult:
    email = (email or "").strip().lower() or None
    phone = normalize_phone(phone) if phone and digits(phone) else None
    factors = sum(x is not None for x in (order_id, email, phone))
    if factors < 2:
        return VerificationResult(
            None, "São necessários dois dados entre: número do pedido, e-mail e telefone."
        )
    candidates = list(store.customers.values())
    if order_id is not None:
        order = visible_orders(store, today).get(int(order_id))
        candidates = [c for c in candidates if order and c.customer_id == order.customer_id]
    if email is not None:
        candidates = [c for c in candidates if c.email_norm == email]
    if phone is not None:
        candidates = [c for c in candidates if c.phone_digits == phone]
    return VerificationResult(candidates[0] if len(candidates) == 1 else None)


def order_summary(store: Store, order: Order, today: date) -> dict[str, Any]:
    items = [
        f"{i.quantity}x {store.products[i.product_id].name}"
        for i in order.items
        if i.product_id in store.products
    ]
    payment = order.payment_method
    if payment.startswith("credit_"):
        payment_pt = f"cartão de crédito em {payment.removeprefix('credit_')}"
    else:
        payment_pt = {"pix": "PIX", "debit": "cartão de débito", "boleto": "boleto"}.get(
            payment, payment
        )
    summary: dict[str, Any] = {
        "pedido": order.order_id,
        "data_do_pedido": fmt_date(order.order_date),
        "status": STATUS_PT[order.status],
        "itens": items,
        "total_pago": fmt_brl(order.total),
        "pagamento": payment_pt,
    }
    if order.tracking_code:
        summary["codigo_rastreio"] = order.tracking_code
    if order.estimated_delivery:
        summary["previsao_entrega"] = fmt_date(order.estimated_delivery)
    if order.notes:
        summary["observacao"] = order.notes

    alerts = []
    age = (today - order.order_date).days
    if order.status is OrderStatus.SHIPPED and order.estimated_delivery:
        late = (today - order.estimated_delivery).days
        if late > 0:
            alerts.append(
                f"a previsão de entrega passou há {late} dias: peça desculpas, passe o código "
                "de rastreio (site dos Correios/Jadlog) e ofereça abrir um chamado"
            )
    if order.status in (OrderStatus.PENDING, OrderStatus.CONFIRMED) and age > STALE_DAYS:
        alerts.append(
            f"pedido sem envio há {age} dias: peça desculpas e ofereça abrir um chamado para a "
            "equipe verificar (não prometa prazo)"
        )
    if alerts:
        summary["atencao"] = alerts
    return summary


def customer_orders(store: Store, customer_id: int, today: date) -> list[Order]:
    orders = [o for o in visible_orders(store, today).values() if o.customer_id == customer_id]
    return sorted(orders, key=lambda o: o.order_date, reverse=True)
