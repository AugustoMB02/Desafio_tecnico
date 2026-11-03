"""Load the challenge CSVs into typed, read-only objects.

65 products and 20 orders fit comfortably in memory, so there is no database and no
build step: the CSVs are parsed once at startup and queried by pure functions. The
objects are frozen, so tools running in parallel threads can share them safely.
"""

from __future__ import annotations

import csv
import json
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from enum import StrEnum
from pathlib import Path
from types import MappingProxyType

from .money import to_money
from .text import digits, normalize

DEFAULT_DATA_DIR = Path(__file__).resolve().parents[2] / "data"
CSV_PREFIX = "desafio_tecnico_ai_eng - "


class ProductStatus(StrEnum):
    ACTIVE = "active"
    DISCONTINUED = "discontinued"
    COMING_SOON = "coming_soon"


class OrderStatus(StrEnum):
    PENDING = "pending"
    CONFIRMED = "confirmed"
    SHIPPED = "shipped"
    DELIVERED = "delivered"
    CANCELLED = "cancelled"


@dataclass(frozen=True)
class Category:
    category_id: int
    name: str
    description: str


@dataclass(frozen=True)
class Promotion:
    promotion_id: int
    product_id: int
    discount_percent: Decimal
    description: str
    is_active: bool


@dataclass(frozen=True)
class Product:
    product_id: int
    name: str
    price: Decimal
    category_id: int
    description: str
    stock: int
    status: ProductStatus
    specs: MappingProxyType
    created_at: date

    @property
    def strings(self) -> str | None:
        """ "nylon"/"steel" for violões and ukuleles, "4"/"6" for guitars and basses."""
        return self.specs.get("strings")

    @property
    def has_electronics(self) -> bool | None:
        value = self.specs.get("electronics")
        return None if value is None else value == "yes"


@dataclass(frozen=True)
class Customer:
    customer_id: int
    name: str
    phone: str
    email: str
    city: str

    @property
    def phone_digits(self) -> str:
        return digits(self.phone)

    @property
    def email_norm(self) -> str:
        return self.email.strip().lower()

    @property
    def first_name(self) -> str:
        return self.name.split()[0]


@dataclass(frozen=True)
class OrderItem:
    product_id: int
    quantity: int


@dataclass(frozen=True)
class Order:
    order_id: int
    customer_id: int
    order_date: date
    status: OrderStatus
    total: Decimal
    payment_method: str
    tracking_code: str | None
    estimated_delivery: date | None
    notes: str | None
    items: tuple[OrderItem, ...] = field(default=())


@dataclass(frozen=True)
class Store:
    categories: MappingProxyType  # int -> Category
    products: MappingProxyType  # int -> Product
    promotions: tuple[Promotion, ...]
    customers: MappingProxyType  # int -> Customer
    orders: MappingProxyType  # int -> Order

    def active_promotion(self, product_id: int) -> Promotion | None:
        """The active promotion for a product (`is_active = 1`), if any.

        The data has at most one active row per product; if there were several, the
        largest discount would win (promotions are not cumulative, §6.2).
        """
        active = [p for p in self.promotions if p.product_id == product_id and p.is_active]
        return max(active, key=lambda p: p.discount_percent, default=None)

    def expired_promotions(self, product_id: int) -> list[Promotion]:
        return [p for p in self.promotions if p.product_id == product_id and not p.is_active]

    def category_slug_of(self, product: Product) -> str:
        return normalize(self.categories[product.category_id].name)


def _read(data_dir: Path, name: str) -> list[dict[str, str]]:
    path = data_dir / f"{CSV_PREFIX}{name}.csv"
    with path.open(encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def _opt(value: str) -> str | None:
    value = value.strip()
    return value or None


def load_store(data_dir: Path | str = DEFAULT_DATA_DIR) -> Store:
    data_dir = Path(data_dir)

    categories = {
        int(r["category_id"]): Category(int(r["category_id"]), r["name"], r["description"])
        for r in _read(data_dir, "categories")
    }
    products = {}
    for r in _read(data_dir, "products"):
        pid = int(r["product_id"])
        products[pid] = Product(
            product_id=pid,
            name=r["name"].strip(),
            price=to_money(r["price_brl"]),
            category_id=int(r["category_id"]),
            description=r["description"].strip(),
            stock=int(r["stock_quantity"]),
            status=ProductStatus(r["status"]),
            specs=MappingProxyType(json.loads(r["specs"])),
            created_at=date.fromisoformat(r["created_at"]),
        )
    promotions = tuple(
        Promotion(
            promotion_id=int(r["promotion_id"]),
            product_id=int(r["product_id"]),
            discount_percent=Decimal(r["discount_percent"]),
            description=r["description"].strip(),
            is_active=r["is_active"].strip() == "1",
        )
        for r in _read(data_dir, "promotions")
    )
    customers = {
        int(r["customer_id"]): Customer(
            int(r["customer_id"]),
            r["name"].strip(),
            r["phone"].strip(),
            r["email"].strip(),
            r["city"].strip(),
        )
        for r in _read(data_dir, "customers")
    }
    items: dict[int, list[OrderItem]] = defaultdict(list)
    for r in _read(data_dir, "order_items"):
        items[int(r["order_id"])].append(OrderItem(int(r["product_id"]), int(r["quantity"])))
    orders = {}
    for r in _read(data_dir, "orders"):
        oid = int(r["order_id"])
        eta = _opt(r["estimated_delivery"])
        orders[oid] = Order(
            order_id=oid,
            customer_id=int(r["customer_id"]),
            order_date=date.fromisoformat(r["order_date"]),
            status=OrderStatus(r["status"]),
            total=to_money(r["total_brl"]),
            payment_method=r["payment_method"].strip(),
            tracking_code=_opt(r["tracking_code"]),
            estimated_delivery=date.fromisoformat(eta) if eta else None,
            notes=_opt(r["notes"]),
            items=tuple(items[oid]),
        )

    return Store(
        categories=MappingProxyType(categories),
        products=MappingProxyType(products),
        promotions=promotions,
        customers=MappingProxyType(customers),
        orders=MappingProxyType(orders),
    )
