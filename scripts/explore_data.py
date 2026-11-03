import csv
import json
import re
from collections import Counter, defaultdict
from pathlib import Path

# Raw inputs currently live at the repository root. If they move to data/, append / "data".
DATA_DIR = Path(__file__).resolve().parents[1]

def load_csv(name):
    path = DATA_DIR / f"desafio_tecnico_ai_eng - {name}.csv"
    with open(path, encoding="utf-8") as f:
        raw = f.read()
    has_crlf = "\r\n" in raw
    ends_with_newline = raw.endswith("\n")
    with open(path, encoding="utf-8", newline="") as f:
        rows = list(csv.DictReader(f))
    return rows, {"bytes": path.stat().st_size, "crlf": has_crlf, "trailing_nl": ends_with_newline, "rows": len(rows)}

tables = {}
meta = {}
for t in ["categories", "customers", "products", "promotions", "orders", "order_items"]:
    tables[t], meta[t] = load_csv(t)

print("=== FILE METADATA ===")
for t, m in meta.items():
    print(f"{t:15s}: {m}")

# 1. Categories analysis
cats = {r["category_id"]: r for r in tables["categories"]}
prod_by_cat = Counter(r["category_id"] for r in tables["products"])
print("\n=== CATEGORIES COVERAGE ===")
for cid, c in cats.items():
    print(f"Cat {cid} ({c['name']}): {prod_by_cat.get(cid, 0)} products")
extra_cats = set(prod_by_cat.keys()) - set(cats.keys())
print("Orphan category_ids in products:", extra_cats)

# 2. Products analysis
prods = {r["product_id"]: r for r in tables["products"]}
print("\n=== PRODUCTS ANALYSIS ===")
print("Total rows:", len(tables["products"]), "Unique product_ids:", len(prods))
pids = [int(r["product_id"]) for r in tables["products"]]
print("ID range:", min(pids), "to", max(pids), "Is sorted?", pids == sorted(pids))
print("Status counts:", Counter(r["status"] for r in tables["products"]))

print("\nZero-stock or non-active products:")
for r in tables["products"]:
    if int(r["stock_quantity"]) <= 0 or r["status"] != "active":
        print(f"  ID={r['product_id']} | status={r['status']} | stock={r['stock_quantity']} | price={r['price_brl']} | name={r['name']}")

print("\nJSON specs validation & schema per category:")
specs_keys_by_cat = defaultdict(Counter)
for r in tables["products"]:
    try:
        sp = json.loads(r["specs"])
        specs_keys_by_cat[r["category_id"]][tuple(sorted(sp.keys()))] += 1
    except Exception as e:
        print(f"  INVALID JSON in product {r['product_id']}: {e}")

for cid, kcounts in sorted(specs_keys_by_cat.items()):
    print(f"  Cat {cid} ({cats[cid]['name']}): {dict(kcounts)}")

print("\nBrand/spec contradictions between name, description, and specs:")
brands = ["Yamaha", "Tagima", "Giannini", "Rozini", "Shelby", "Crafter", "Martin", "Taylor", "Takamine",
          "Kala", "Ohana", "Kalani", "Fender", "Gibson", "Ibanez", "PRS", "Music Man", "Pearl", "Tama",
          "Korg", "Roland", "Nord"]
for r in tables["products"]:
    sp = json.loads(r["specs"])
    name_brands = [b for b in brands if b.lower() in r["name"].lower()]
    desc_brands = [b for b in brands if b.lower() in r["description"].lower()]
    issues = []
    if name_brands and desc_brands and set(name_brands) != set(desc_brands):
        issues.append(f"brand mismatch name={name_brands} vs desc={desc_brands}")
    # Check strings / keys mismatch
    if "5 cordas" in r["description"].lower() and sp.get("strings") != "5":
        issues.append(f"desc says 5 cordas vs specs strings={sp.get('strings')}")
    if "88 teclas" in r["description"].lower() and sp.get("keys") != "88":
        issues.append(f"desc says 88 teclas vs specs keys={sp.get('keys')}")
    if "alder" in r["description"].lower() and sp.get("body", "").lower() != "alder":
        issues.append(f"desc says Alder vs specs body={sp.get('body')}")
    if "birch" in r["description"].lower() and sp.get("shells", "").lower() != "birch":
        issues.append(f"desc says Birch vs specs shells={sp.get('shells')}")
    if "poplar" in r["description"].lower() and "poplar" not in sp.get("shells", "").lower():
        issues.append(f"desc says Poplar vs specs shells={sp.get('shells')}")
    if issues:
        print(f"  ID={r['product_id']} ({r['name']}, R${r['price_brl']}): {'; '.join(issues)}")

# Violoes <= 1000 check (including promotions and PIX!)
active_promos = {r["product_id"]: r for r in tables["promotions"] if r["is_active"] == "1"}
print("\n=== VIOLÕES (cat 5) <= R$1100 OR WITH PROMO ===")
for r in tables["products"]:
    if r["category_id"] == "5":
        p = float(r["price_brl"])
        pr = active_promos.get(r["product_id"])
        eff = p * (1 - float(pr["discount_percent"]) / 100) if pr else p
        pix = eff if pr else p * 0.95
        if p <= 1100 or eff <= 1100 or pix <= 1000:
            print(f"  ID={r['product_id']} | {r['name']} | base={p:.2f} | promo={eff:.2f} ({pr['discount_percent']+'%' if pr else 'none'}) | pix={pix:.2f} | stock={r['stock_quantity']} | status={r['status']}")

# 3. Promotions analysis
print("\n=== PROMOTIONS ANALYSIS ===")
print("Total promotions:", len(tables["promotions"]))
print("is_active counts:", Counter(r["is_active"] for r in tables["promotions"]))
prod_promo_counts = Counter(r["product_id"] for r in tables["promotions"])
print("Products with multiple promotion rows:", {k: v for k, v in prod_promo_counts.items() if v > 1})
print("Active promotions details:")
for r in tables["promotions"]:
    p = prods.get(r["product_id"])
    if r["is_active"] == "1":
        base = float(p["price_brl"])
        disc = float(r["discount_percent"])
        final = base * (1 - disc / 100)
        print(f"  promo_id={r['promotion_id']} | prod={r['product_id']} ({p['name']}) | base=R${base:.2f} | -{disc:.0f}% -> R${final:.2f} | desc={r['description']} | prod_status={p['status']} | stock={p['stock_quantity']}")
    if not p:
        print(f"  ORPHAN promo: {r}")

# Check promo descriptions vs PDF §6.1 campaigns
print("Promotion descriptions distribution:", Counter(r["description"] for r in tables["promotions"]))

# 4. Customers analysis
print("\n=== CUSTOMERS ANALYSIS ===")
custs = {r["customer_id"]: r for r in tables["customers"]}
print("Total customers:", len(tables["customers"]), "Unique IDs:", len(custs))
print("Cities:", Counter(r["city"] for r in tables["customers"]))
email_counts = Counter(r["email"].lower() for r in tables["customers"])
phone_counts = Counter(r["phone"] for r in tables["customers"])
name_counts = Counter(r["name"].lower() for r in tables["customers"])
print("Duplicate emails:", {k: v for k, v in email_counts.items() if v > 1})
for r in tables["customers"]:
    if email_counts[r["email"].lower()] > 1:
        print("  Dup email row:", r)
print("Duplicate phones:", {k: v for k, v in phone_counts.items() if v > 1})
print("Duplicate full names:", {k: v for k, v in name_counts.items() if v > 1})
first_last = Counter((r["name"].split()[0].lower(), r["name"].split()[-1].lower()) for r in tables["customers"])
print("Duplicate (first, last) name pairs:", {k: v for k, v in first_last.items() if v > 1})
for r in tables["customers"]:
    fl = (r["name"].split()[0].lower(), r["name"].split()[-1].lower())
    if first_last[fl] > 1:
        print("  Near-homonym row:", r)
# Check accents in names (e.g. Joao vs João, Leticia vs Letícia)
for r in tables["customers"]:
    if any(w in r["name"] for w in ["Joao", "Leticia", "Julia"]):
        print("  Unaccented name:", r)
print("Email domains:", Counter(r["email"].split("@")[1] for r in tables["customers"]))

# 5. Orders & Order Items analysis
print("\n=== ORDERS & ORDER ITEMS ANALYSIS ===")
items_by_order = defaultdict(list)
for it in tables["order_items"]:
    items_by_order[it["order_id"]].append(it)
    if it["product_id"] not in prods:
        print("ORPHAN product_id in order_items:", it)

tracking_re = re.compile(r"^BR[A-Z0-9]{9}BR$")  # PDF §5.3 says BR + 9 alphanumeric + BR = 13 chars

for o in tables["orders"]:
    oid = o["order_id"]
    cid = o["customer_id"]
    c = custs.get(cid)
    its = items_by_order.get(oid, [])
    sum_base = sum(int(i["quantity"]) * float(prods[i["product_id"]]["price_brl"]) for i in its)
    total = float(o["total_brl"])
    diff = total - sum_base
    ratio = total / sum_base if sum_base else 0
    tc = o["tracking_code"]
    tc_ok = bool(tracking_re.match(tc)) if tc else None
    prod_statuses = [(i["product_id"], prods[i["product_id"]]["name"], prods[i["product_id"]]["status"], prods[i["product_id"]]["stock_quantity"]) for i in its]
    print(f"Order {oid:2s} | cust={cid:2s} ({c['city']}) | date={o['order_date']} | status={o['status']:9s} | pay={o['payment_method']:10s} | sum_base={sum_base:8.2f} | total={total:8.2f} (diff={diff:+.2f}, ratio={ratio:.4f}) | tc={tc or '-':13s} (valid_fmt={tc_ok}) | est={o['estimated_delivery'] or '-':10s} | items={prod_statuses}")
    # Check installment rules vs §3.1!
    pm = o["payment_method"]
    if pm.startswith("credit_"):
        n_inst = int(pm.split("_")[1].replace("x", ""))
        inst_val = total / n_inst
        min_req = 50 if n_inst <= 3 else (80 if n_inst <= 6 else 100)
        if inst_val < min_req:
            print(f"  [POLICY VIOLATION in historical order {oid}!] {pm} on R${total:.2f} -> installment R${inst_val:.2f} < min R${min_req:.2f} (§3.1)")
    if pm == "pix":
        # Check if 5% PIX discount was applied or not!
        if abs(diff) < 0.01:
            print(f"  [NOTE] Order {oid} paid via PIX has total == base price (no 5% PIX discount applied in CSV total_brl)")
