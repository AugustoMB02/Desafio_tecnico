"""Business rules from the policy manual, as pure functions over the `Store`.

Every rule cites the manual section it implements. Interpretations of ambiguous
rules are marked ASSUMPTION and repeated in the README.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum

from .data import Product, ProductStatus, Store
from .money import apply_discount, round_money
from .text import compact, normalize, tokens

PIX_DISCOUNT_PERCENT = Decimal(5)  # §3
COMBINED_PAYMENT_MIN = Decimal("2000.00")  # §3.1
FREE_SHIPPING_MIN = Decimal("500.00")  # §5.1
LOCAL_SHIPPING_FEE = Decimal("35.00")  # §5.1
MAX_INSTALLMENTS = 12  # §3

# §3.1, ASSUMPTION: the tiered rules govern over the flat "parcela mínima de R$ 100,00"
# cell of the §3 table, and the first bullet means "each installment >= R$ 50,00".
INSTALLMENT_TIERS: tuple[tuple[int, int, Decimal], ...] = (
    (1, 3, Decimal("50.00")),
    (4, 6, Decimal("80.00")),
    (7, 12, Decimal("100.00")),
)

# ASSUMPTION: only Campo Grande itself is treated as the metropolitan region (§5.1);
# neighbouring municipalities get the "calculado pelo CEP" answer until confirmed.
METRO_CITIES = frozenset({"campo grande", "cg"})


# --- Availability --------------------------------------------------------------------


class Availability(StrEnum):
    AVAILABLE = "disponível"
    OUT_OF_STOCK = "sem estoque"
    DISCONTINUED = "descontinuado"
    COMING_SOON = "em breve"


def availability(product: Product) -> Availability:
    """Available means `active AND stock > 0`.

    `discontinued` wins over stock (ID 136 has 13 units but is out of the catalog), and
    `coming_soon` means "em breve, ainda sem pronta entrega" — never pre-sale (ASSUMPTION).
    """
    if product.status is ProductStatus.DISCONTINUED:
        return Availability.DISCONTINUED
    if product.status is ProductStatus.COMING_SOON:
        return Availability.COMING_SOON
    if product.stock <= 0:
        return Availability.OUT_OF_STOCK
    return Availability.AVAILABLE


def is_available(product: Product) -> bool:
    return availability(product) is Availability.AVAILABLE


# --- Prices --------------------------------------------------------------------------


@dataclass(frozen=True)
class Price:
    table: Decimal
    current: Decimal  # what the customer pays by card, debit or boleto
    promo_percent: Decimal | None
    promo_name: str | None
    pix: Decimal  # PIX price; equals `current` when a promotion applies (§6.2)

    @property
    def on_promotion(self) -> bool:
        return self.promo_percent is not None


def price_of(store: Store, product: Product, quantity: int = 1) -> Price:
    """Line price for `quantity` units.

    Only `is_active = 1` promotions change the price. PIX takes 5% off the table price
    (§3) but never stacks on a promotional price (§6.2). Rounding is half-up per line.
    """
    table = round_money(product.price * quantity)
    promo = store.active_promotion(product.product_id)
    if promo is not None:
        current = apply_discount(table, promo.discount_percent)
        return Price(table, current, promo.discount_percent, promo.description, current)
    pix = apply_discount(table, PIX_DISCOUNT_PERCENT)
    return Price(table, table, None, None, pix)


# --- Installments (§3, §3.1) -----------------------------------------------------------


def min_installment(n: int) -> Decimal:
    for low, high, minimum in INSTALLMENT_TIERS:
        if low <= n <= high:
            return minimum
    raise ValueError(f"installments must be 1..{MAX_INSTALLMENTS}, got {n}")


def installment_allowed(total: Decimal, n: int) -> bool:
    if not 1 <= n <= MAX_INSTALLMENTS:
        return False
    if n == 1:
        return True  # paying once on the card is always allowed
    return total / n >= min_installment(n)


def max_installments(total: Decimal) -> int:
    return max(n for n in range(1, MAX_INSTALLMENTS + 1) if installment_allowed(total, n))


def installment_value(total: Decimal, n: int) -> Decimal:
    """Displayed value of each installment (half-up; the card issuer adjusts the cents)."""
    return round_money(total / n)


# --- Shipping (§5) -----------------------------------------------------------------------


class ShippingKind(StrEnum):
    FREE_LOCAL = "grátis (motoboy, região metropolitana de Campo Grande)"
    PAID_LOCAL = "taxa fixa (motoboy, região metropolitana de Campo Grande)"
    BY_CEP = "calculado pelo CEP (Correios/Jadlog)"


@dataclass(frozen=True)
class Shipping:
    kind: ShippingKind
    fee: Decimal | None  # None when it depends on the CEP
    special_freight: bool  # §5.2 large instruments may need an individual quote


def is_metro(city: str | None) -> bool:
    """Campo Grande, also written "Campo Grande - MS", "Campo Grande/MS" or "CG"."""
    if not city:
        return False
    name = re.sub(r"\b(ms|mato grosso do sul)\b", " ", normalize(city))
    return " ".join(name.split()) in METRO_CITIES


def needs_special_freight(store: Store, product: Product) -> bool:
    """§5.2 "grande porte": acoustic drum kits, digital/stage pianos, acoustic double basses.

    ASSUMPTION: electric basses (category 2) ship normally; "contrabaixos" in §5.2 means
    the acoustic double bass (category 8, currently empty).
    """
    name = normalize(product.name)
    if product.category_id == 3 and "acustica" in name:
        return True
    if product.category_id == 4 and ("piano" in name or "piano" in normalize(product.description)):
        return True
    return product.category_id == 8


def shipping_for(amount_paid: Decimal, city: str | None, special: bool = False) -> Shipping:
    """§5.1 inside the Campo Grande metro region, §5.2 elsewhere.

    ASSUMPTION: the threshold is measured on the amount actually paid (after promotion and
    PIX), and exactly R$ 500,00 counts as free ("acima de" read as ">=").
    """
    if is_metro(city):
        if amount_paid >= FREE_SHIPPING_MIN:
            return Shipping(ShippingKind.FREE_LOCAL, Decimal("0.00"), False)
        return Shipping(ShippingKind.PAID_LOCAL, LOCAL_SHIPPING_FEE, False)
    return Shipping(ShippingKind.BY_CEP, None, special)


# --- Alternatives (§7.3) ---------------------------------------------------------------


def alternatives(store: Store, product: Product, limit: int = 3) -> list[Product]:
    """Available products in the same category with the same `strings` value, nearest price.

    Computed, not hand-picked: the plan's hand-picked alternative to the nylon 7-string
    #113 was a steel-string guitar.
    """
    candidates = [
        p
        for p in store.products.values()
        if p.product_id != product.product_id
        and p.category_id == product.category_id
        and p.strings == product.strings
        and is_available(p)
    ]
    seven = "7 cordas" in product.name.lower()
    candidates.sort(
        key=lambda p: (
            ("7 cordas" in p.name.lower()) != seven,  # keep 7-strings with 7-strings
            abs(price_of(store, p).current - product.price),
        )
    )
    return candidates[:limit]


# --- Data-quality flags --------------------------------------------------------------------

BRANDS = (
    "Fender", "Gibson", "Ibanez", "PRS", "Music Man", "Yamaha", "Pearl", "Tama", "Korg",
    "Roland", "Nord", "Tagima", "Giannini", "Takamine", "Martin", "Taylor", "Crafter",
    "Shelby", "Rozini", "Kala", "Ohana", "Kalani",
)  # fmt: skip
# Model names that identify a brand on their own.
MODEL_BRANDS = {
    "jazz bass": "Fender", "precision": "Fender", "stratocaster": "Fender",
    "telecaster": "Fender", "les paul": "Gibson", "stingray": "Music Man",
    "stage custom": "Yamaha", "export": "Pearl", "star mount": "Tama",
}  # fmt: skip


def _brands_in(text: str) -> set[str]:
    norm = f" {normalize(text)} "
    found = {b for b in BRANDS if f" {normalize(b)} " in norm}
    found |= {brand for model, brand in MODEL_BRANDS.items() if f" {model} " in norm}
    return found


def data_quality_issues(product: Product) -> list[str]:
    """Rule-based contradictions between name, description and specs (pt-BR notes)."""
    issues = []
    name_brands = _brands_in(product.name)
    other = sorted(_brands_in(product.description) - name_brands)
    if name_brands and other:
        issues.append(
            f"a descrição cita {', '.join(other)}, mas o produto é {', '.join(sorted(name_brands))}"
        )
    desc = normalize(product.description)
    for word, key in (("cordas", "strings"), ("teclas", "keys")):
        spec = str(product.specs.get(key, ""))
        m = re.search(rf"\b(\d+) {word}\b", desc)
        if m and spec.isdigit() and m.group(1) != spec:
            issues.append(f"a descrição fala em {m.group(1)} {word} e a ficha técnica em {spec}")
    return issues


# --- Product lookup by name ----------------------------------------------------------------

_LOOKUP_STOPWORDS = frozenset(
    {
        "o", "a", "os", "as", "um", "uma", "de", "do", "da", "dos", "das", "e", "quanto",
        "custa", "preco", "valor", "tem", "voces", "vcs", "qto", "ta", "esta", "modelo",
        "instrumento", "por", "favor",
    }
)  # fmt: skip


def find_products(store: Store, query: str, limit: int = 5) -> list[tuple[float, Product]]:
    """Fuzzy name lookup tolerant to accents, spacing and hyphens ("takamine gd 20")."""
    q_compact = compact(query)
    q_tokens = [t for t in tokens(query) if t not in _LOOKUP_STOPWORDS] or tokens(query)
    if not q_tokens:
        return []
    scored = []
    for p in store.products.values():
        name_c = compact(p.name)
        name_t = set(tokens(p.name))
        joined = compact(" ".join(q_tokens))
        if joined and joined in name_c:
            score = 1.0 + len(joined) / len(name_c)
        elif q_compact and q_compact in name_c:
            score = 1.0 + len(q_compact) / len(name_c)
        else:
            hits = sum(1 for t in q_tokens if t in name_t or (len(t) >= 3 and t in name_c))
            score = hits / len(q_tokens)
        if score > 0:
            scored.append((score, p))
    scored.sort(key=lambda sp: (-sp[0], sp[1].product_id))
    return scored[:limit]
