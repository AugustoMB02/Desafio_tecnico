"""Recompute the numbers cited in docs/Plan_Review.md from the raw CSVs.

Usage:
    python3 scripts/review_checks/check_numbers.py [DATA_DIR]

DATA_DIR defaults to the repository root, where the CSVs currently live.
If they move to data/, pass that directory (or update DEFAULT_DATA_DIR).
Standard library only.
"""

import csv
import datetime as dt
import statistics
import sys
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path

DEFAULT_DATA_DIR = Path(__file__).resolve().parents[2] / "data"
DATA_DIR = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_DATA_DIR
PREFIX = "desafio_tecnico_ai_eng - "


def load(name: str) -> list[dict[str, str]]:
    with open(DATA_DIR / f"{PREFIX}{name}.csv", encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


products, promotions = load("products"), load("promotions")
orders, customers = load("orders"), load("customers")
customer_by_id = {c["customer_id"]: c for c in customers}
active_promo = {p["product_id"]: Decimal(p["discount_percent"]) for p in promotions if p["is_active"] == "1"}


def is_available(p: dict[str, str]) -> bool:
    return p["status"] == "active" and int(p["stock_quantity"]) > 0


def effective_price(p: dict[str, str]) -> Decimal:
    return Decimal(p["price_brl"]) * (1 - active_promo.get(p["product_id"], Decimal(0)) / 100)


def min_installment_31(n: int) -> int:  # §3.1 tiers
    return 50 if n <= 3 else 80 if n <= 6 else 100


def min_installment_3(n: int) -> int:  # §3 table: "Parcela mínima de R$ 100,00"
    return 100


def max_installments(total: Decimal, rule) -> int:
    return max([n for n in range(1, 13) if total / n >= rule(n)] or [1])


available = [p for p in products if is_available(p)]

print("== Category stats: count, available, min/median/max price, stock, available stock")
for cid in sorted({p["category_id"] for p in products}, key=int):
    rows = [p for p in products if p["category_id"] == cid]
    prices = sorted(float(p["price_brl"]) for p in rows)
    print(
        f"  cat {cid}: {len(rows)} SKUs, {sum(is_available(p) for p in rows)} available, "
        f"{min(prices)} / {statistics.median(prices)} / {max(prices)}, "
        f"stock {sum(int(p['stock_quantity']) for p in rows)}, "
        f"available stock {sum(int(p['stock_quantity']) for p in rows if is_available(p))}"
    )

print("\n== Available violões (cat 5) with table price <= R$ 1.000, and PIX-only matches")
cheap = sorted((p for p in available if p["category_id"] == "5" and Decimal(p["price_brl"]) <= 1000),
               key=lambda p: Decimal(p["price_brl"]))
print(f"  {len(cheap)} matches: {[p['product_id'] for p in cheap]}")
pix_only = [p["product_id"] for p in available if p["category_id"] == "5" and p["product_id"] not in active_promo
            and Decimal(p["price_brl"]) > 1000 and Decimal(p["price_brl"]) * Decimal("0.95") <= 1000]
print(f"  PIX-only matches: {pix_only}")

print("\n== Active promotions")
for pid, pct in active_promo.items():
    p = next(x for x in products if x["product_id"] == pid)
    print(f"  {pid} {p['name']}: R$ {p['price_brl']} -{pct}% -> R$ {effective_price(p):.2f}")

print("\n== Takamine GD20 (95)")
gd20 = next(p for p in products if p["product_id"] == "95")
price = Decimal(gd20["price_brl"])
print(f"  table R$ {price}, PIX R$ {price * Decimal('0.95'):.2f}, "
      f"max {max_installments(price, min_installment_31)}x of R$ {price / 12:.2f}, "
      f"promos: {[(p['promotion_id'], p['discount_percent'], p['is_active']) for p in promotions if p['product_id'] == '95']}")

print("\n== PIX price: float round() vs Decimal ROUND_HALF_UP (non-promotional products)")
for p in products:
    if p["product_id"] in active_promo:
        continue
    as_float = round(float(p["price_brl"]) * 0.95, 2)
    as_decimal = (Decimal(p["price_brl"]) * Decimal("0.95")).quantize(Decimal("0.01"), ROUND_HALF_UP)
    if Decimal(str(as_float)) != as_decimal:
        print(f"  {p['product_id']:>3} {p['name'][:36]:36s} float {as_float:.2f}  half-up {as_decimal}")

print("\n== Max installments: §3.1 tiers vs §3 flat R$ 100 (available SKUs where they differ)")
differ = [(p["product_id"], effective_price(p), max_installments(effective_price(p), min_installment_31),
           max_installments(effective_price(p), min_installment_3)) for p in available]
differ = [d for d in differ if d[2] != d[3]]
print(f"  {len(differ)} of {len(available)} available SKUs differ; highest price among them R$ {max(d[1] for d in differ):.2f}")
for pid, eff, a, b in differ:
    print(f"    {pid:>3} R$ {eff:>8.2f}: §3.1 {a}x vs §3 {b}x")

print("\n== Shipping threshold flips (table price > R$ 500 but price after promotion < R$ 500)")
for p in available:
    if Decimal(p["price_brl"]) > 500 > effective_price(p):
        print(f"  {p['product_id']} {p['name']}: table R$ {p['price_brl']}, promo R$ {effective_price(p):.2f}")

print("\n== Days from order to estimated delivery, with the customer's city")
for o in orders:
    if o["estimated_delivery"]:
        days = (dt.date.fromisoformat(o["estimated_delivery"]) - dt.date.fromisoformat(o["order_date"])).days
        print(f"  order {o['order_id']:>2} {customer_by_id[o['customer_id']]['city']:12s} {o['status']:9s} {days} days")

print("\n== Orders dated after the reference dates docs/PLAN.md suggests")
print(f"  latest order_date: {max(o['order_date'] for o in orders)}")
for ref in ("2026-02-22", "2026-03-23"):
    print(f"  {ref}: {[o['order_id'] for o in orders if o['order_date'] > ref]}")

print("\n== SKUs 135-144: brand/model named in the description vs the product name")
brand_models = {
    "Fender": ["Fender", "Jazz Bass", "Precision"], "Music Man": ["Music Man", "StingRay"],
    "Ibanez": ["Ibanez"], "Yamaha": ["Yamaha", "Stage Custom"], "Pearl": ["Pearl", "Export"],
    "Tama": ["Tama"], "Korg": ["Korg"], "Roland": ["Roland", "SuperNATURAL"], "Nord": ["Nord"],
}
for p in products:
    if 135 <= int(p["product_id"]) <= 144:
        name_brand = next(b for b in brand_models if b.lower() in p["name"].lower())
        desc_brands = [b for b, terms in brand_models.items()
                       if any(t.lower() in p["description"].lower() for t in terms)]
        flag = "MISMATCH" if desc_brands and name_brand not in desc_brands else "ok"
        print(f"  {p['product_id']} name={name_brand:9s} description={desc_brands} {flag}")
