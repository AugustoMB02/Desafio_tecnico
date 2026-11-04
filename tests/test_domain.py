"""Domain rules, pinned to the values re-derived in docs/Plan_Review.md §2–§3."""

from decimal import Decimal

import pytest

from emporio_agent import rules
from emporio_agent.data import load_store
from emporio_agent.money import fmt_brl, fmt_date
from emporio_agent.rules import Availability

D = Decimal


@pytest.fixture(scope="module")
def store():
    return load_store()


# --- loading ---------------------------------------------------------------------------


def test_row_counts(store):
    assert len(store.categories) == 9
    assert len(store.products) == 65
    assert len(store.promotions) == 25
    assert len(store.customers) == 50
    assert len(store.orders) == 20
    assert sum(len(o.items) for o in store.orders.values()) == 22


def test_prices_parse_without_float_noise(store):
    assert store.products[81].price == D("599.90")
    assert store.products[81].specs["strings"] == "nylon"


# --- formatting ------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("1967.18", "R$ 1.967,18"),
        ("0", "R$ 0,00"),
        ("35", "R$ 35,00"),
        ("19567", "R$ 19.567,00"),
        ("1234567.891", "R$ 1.234.567,89"),
        ("569.905", "R$ 569,91"),
    ],
)
def test_fmt_brl(value, expected):
    assert fmt_brl(D(value)) == expected


def test_fmt_date(store):
    assert fmt_date(store.orders[7].estimated_delivery) == "17/02/2026"


# --- availability ------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("pid", "expected"),
    [
        (95, Availability.AVAILABLE),
        (96, Availability.OUT_OF_STOCK),  # active, stock 0
        (113, Availability.DISCONTINUED),  # discontinued, stock 0
        (136, Availability.DISCONTINUED),  # discontinued despite 13 units
        (130, Availability.COMING_SOON),  # coming_soon with 2 units
    ],
)
def test_availability_traps(store, pid, expected):
    assert rules.availability(store.products[pid]) is expected


def test_sixty_one_sellable_skus(store):
    assert sum(rules.is_available(p) for p in store.products.values()) == 61


def test_violoes_up_to_1000(store):
    matches = [
        p.product_id
        for p in store.products.values()
        if p.category_id == 5
        and rules.is_available(p)
        and rules.price_of(store, p).current <= D(1000)
    ]
    assert sorted(matches) == sorted([83, 85, 89, 88, 81, 84, 87, 86, 107, 82, 91, 112])


# --- prices and promotions -----------------------------------------------------------------


def test_takamine_gd20_ignores_expired_promo(store):
    price = rules.price_of(store, store.products[95])
    assert price.table == price.current == D("2199.00")
    assert not price.on_promotion
    assert price.pix == D("2089.05")
    assert [p.promotion_id for p in store.expired_promotions(95)] == [4]


@pytest.mark.parametrize(
    ("pid", "percent", "promo_price"),
    [(90, 18, "1967.18"), (94, 8, "5519.08"), (121, 20, "439.20"), (127, 10, "323.10")],
)
def test_active_promotions(store, pid, percent, promo_price):
    price = rules.price_of(store, store.products[pid])
    assert price.promo_percent == percent
    assert price.current == D(promo_price)
    assert price.pix == price.current  # PIX never stacks on a promotion (§6.2)


def test_only_four_active_promotions(store):
    assert sorted(p.product_id for p in store.promotions if p.is_active) == [90, 94, 121, 127]


@pytest.mark.parametrize(
    ("pid", "pix"),
    [(81, "569.91"), (83, "408.41"), (85, "436.91"), (87, "664.91"), (88, "550.91"),
     (96, "759.91"), (120, "332.41"), (124, "427.41")],
)  # fmt: skip
def test_pix_half_cent_rounds_half_up(store, pid, pix):
    assert rules.price_of(store, store.products[pid]).pix == D(pix)


def test_gd20_pix_crosses_1000_for_101(store):
    assert rules.price_of(store, store.products[101]).pix == D("996.55")


def test_line_price_scales_with_quantity(store):
    price = rules.price_of(store, store.products[81], quantity=2)
    assert price.table == D("1199.80")
    assert price.pix == D("1139.81")


# --- installments --------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("total", "expected"),
    [
        ("2199.00", 12),
        ("159.90", 3),
        ("599.90", 6),
        ("429.90", 5),
        ("349.90", 4),
        ("700.00", 7),
        ("699.99", 6),
        ("1200.00", 12),
        ("40.00", 1),
    ],
)
def test_max_installments(total, expected):
    assert rules.max_installments(D(total)) == expected


def test_gd20_twelve_installments():
    assert rules.installment_value(D("2199.00"), 12) == D("183.25")


def test_installment_bounds():
    assert not rules.installment_allowed(D("5000"), 13)
    assert not rules.installment_allowed(D("5000"), 0)
    assert rules.installment_allowed(D("150.00"), 3)
    assert not rules.installment_allowed(D("149.99"), 3)


# --- shipping --------------------------------------------------------------------------------


def test_shipping_campo_grande():
    assert rules.shipping_for(D("500.00"), "Campo Grande").fee == D("0.00")
    assert rules.shipping_for(D("499.99"), "campo grande").fee == D("35.00")
    assert rules.shipping_for(D("439.20"), "Campo Grande").fee == D("35.00")  # CK-20 promo


def test_shipping_other_city_is_by_cep():
    ship = rules.shipping_for(D("5000"), "Dourados", special=True)
    assert ship.kind is rules.ShippingKind.BY_CEP
    assert ship.fee is None
    assert ship.special_freight


def test_shipping_unknown_city_is_by_cep():
    assert rules.shipping_for(D("100"), None).fee is None


def test_special_freight(store):
    special = {
        p.product_id for p in store.products.values() if rules.needs_special_freight(store, p)
    }
    assert special == {139, 140, 141, 143}


# --- alternatives and data quality ------------------------------------------------------------


def test_alternatives_keep_strings_type(store):
    alts = rules.alternatives(store, store.products[113])  # nylon 7-string, discontinued
    assert alts
    assert all(a.strings == "nylon" for a in alts)
    assert alts[0].product_id == 110  # Giannini GWNE-7, nearest nylon 7-string
    assert 112 not in [a.product_id for a in alts]  # steel 7-string


def test_alternatives_for_out_of_stock_dreadnought(store):
    alts = rules.alternatives(store, store.products[96])
    assert all(rules.is_available(a) and a.strings == "steel" for a in alts)
    assert alts[0].product_id in {107, 91}


def test_data_quality_flags_exactly_the_seven_skus(store):
    flagged = {p.product_id for p in store.products.values() if rules.data_quality_issues(p)}
    assert flagged == {135, 136, 137, 139, 140, 142, 144}


def test_data_quality_mentions_specs(store):
    issues = " ".join(rules.data_quality_issues(store.products[142]))
    assert "Roland" in issues and "88 teclas" in issues


# --- name lookup -------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "query", ["Takamine GD20", "takamine gd 20", "TAKAMINE GD-20", "qto custa o takamine gd20"]
)
def test_find_takamine(store, query):
    assert rules.find_products(store, query)[0][1].product_id == 95


def test_find_ambiguous_brand_returns_several(store):
    ids = {p.product_id for _, p in rules.find_products(store, "Takamine")}
    assert {95, 100, 105, 115} <= ids


def test_find_yamaha_c40(store):
    assert rules.find_products(store, "yamaha c40")[0][1].product_id == 81


# --- quote: total with shipping ------------------------------------------------------------


def test_quote_total_with_shipping_for_pix_in_campo_grande(store):
    from emporio_agent.catalog import quote

    q = quote(store, [{"product_id": 119, "quantity": 1}], payment="pix", city="Campo Grande")
    assert q["total_no_pix"] == "R$ 151,91"
    assert q["total_com_frete"] == "R$ 186,91"  # 151,91 + 35,00 (below R$ 500)


def test_quote_total_with_shipping_without_payment_shows_both(store):
    from emporio_agent.catalog import quote

    q = quote(store, [{"product_id": 119, "quantity": 1}], city="Campo Grande")
    assert q["total_com_frete"] == {"pagando no PIX": "R$ 186,91", "outras formas": "R$ 194,90"}


def test_quote_total_with_free_shipping_and_unknown_fee(store):
    from emporio_agent.catalog import quote

    mixed = [{"product_id": 81, "quantity": 1}, {"product_id": 121, "quantity": 1}]
    assert quote(store, mixed, payment="pix", city="Campo Grande")["total_com_frete"] == (
        "R$ 1.009,11"
    )
    assert "total_com_frete" not in quote(store, [{"product_id": 95}], city="Dourados")
    assert "total_com_frete" not in quote(store, [{"product_id": 95}])
