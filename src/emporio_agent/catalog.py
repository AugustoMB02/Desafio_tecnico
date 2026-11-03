"""Catalog search, product details and quotes, as plain dicts ready for the model.

Tools take IDs, never prices typed by the model, and every amount comes back already
formatted (`R$ 1.967,18`) so the model never does arithmetic or formatting itself.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any, Literal

from . import rules
from .data import Product, Store
from .money import fmt_brl, round_money
from .rules import Availability
from .text import normalize, tokens

CategorySlug = Literal[
    "guitarras",
    "baixos",
    "baterias_percussao",
    "teclados_pianos",
    "violoes",
    "sopro_madeiras",
    "sopro_metais",
    "cordas_orquestrais",
    "ukuleles",
]
CATEGORY_IDS: dict[str, int] = {
    "guitarras": 1,
    "baixos": 2,
    "baterias_percussao": 3,
    "teclados_pianos": 4,
    "violoes": 5,
    "sopro_madeiras": 6,
    "sopro_metais": 7,
    "cordas_orquestrais": 8,
    "ukuleles": 9,
}
StringsType = Literal["nylon", "aço"]
PaymentMethod = Literal["pix", "credito", "debito", "boleto"]

_STRINGS_PT = {"nylon": "nylon", "steel": "aço"}
_SEARCH_STOPWORDS = frozenset(
    {"de", "do", "da", "com", "para", "um", "uma", "o", "a", "e", "em", "modelo"}
)


# --- presentation helpers -----------------------------------------------------------------


def _strings_label(product: Product) -> str | None:
    value = product.strings
    if value is None:
        return None
    return _STRINGS_PT.get(value, f"{value} cordas")


def price_info(store: Store, product: Product) -> dict[str, Any]:
    price = rules.price_of(store, product)
    n = rules.max_installments(price.current)
    info: dict[str, Any] = {"preco": fmt_brl(price.current)}
    if price.on_promotion:
        info["preco_original"] = fmt_brl(price.table)
        info["promocao"] = f"{price.promo_percent}% de desconto ({price.promo_name})"
        info["pix"] = "sem desconto adicional no PIX (item já em promoção)"
    else:
        info["pix"] = f"{fmt_brl(price.pix)} (5% de desconto à vista)"
    info["parcelamento"] = (
        f"até {n}x de {fmt_brl(rules.installment_value(price.current, n))} sem juros"
        if n > 1
        else "somente à vista no crédito"
    )
    return info


def product_summary(store: Store, product: Product) -> dict[str, Any]:
    summary: dict[str, Any] = {
        "id": product.product_id,
        "nome": product.name,
        "categoria": store.categories[product.category_id].name,
    }
    if (strings := _strings_label(product)) is not None:
        summary["cordas"] = strings
    if product.has_electronics is not None:
        summary["eletroacustico"] = product.has_electronics
    if rules.data_quality_issues(product):
        summary["alerta_dados"] = "cadastro inconsistente: não descreva marca, modelo ou specs"
    else:
        summary["descricao"] = product.description
    summary.update(price_info(store, product))
    return summary


# --- search ------------------------------------------------------------------------------


def _haystack(store: Store, product: Product) -> str:
    parts = [product.name, product.description, store.categories[product.category_id].name]
    parts += [str(v) for v in product.specs.values()]
    if product.strings == "steel":
        parts.append("aco")
    return normalize(" ".join(parts))


def _matches_query(store: Store, product: Product, query: str) -> bool:
    """Every meaningful query word must start some word of the product text (accent-free)."""
    words = _haystack(store, product).split()
    for tok in tokens(query):
        if tok in _SEARCH_STOPWORDS:
            continue
        stem = tok[:-1] if len(tok) > 4 and tok.endswith("s") else tok
        if not any(w.startswith(stem) for w in words):
            return False
    return True


def search_catalog(
    store: Store,
    *,
    query: str | None = None,
    category: str | None = None,
    min_price_brl: float | None = None,
    max_price_brl: float | None = None,
    strings: str | None = None,
    electronics: bool | None = None,
    limit: int = 5,
) -> dict[str, Any]:
    if category is not None and category not in CATEGORY_IDS:
        return {"erro": f"categoria desconhecida; use uma de: {', '.join(CATEGORY_IDS)}"}
    limit = max(1, min(int(limit), 10))
    cat_id = CATEGORY_IDS.get(category) if category else None
    min_p = Decimal(str(min_price_brl)) if min_price_brl is not None else None
    max_p = Decimal(str(max_price_brl)) if max_price_brl is not None else None
    want_strings = {"aco": "steel", "nylon": "nylon"}.get(normalize(strings or ""))

    def base_filter(p: Product) -> bool:
        return (
            rules.is_available(p)
            and (cat_id is None or p.category_id == cat_id)
            and (want_strings is None or p.strings == want_strings)
            and (electronics is None or p.has_electronics is electronics)
            and (not query or _matches_query(store, p, query))
        )

    pool = [p for p in store.products.values() if base_filter(p)]
    matches, pix_only = [], []
    for p in pool:
        price = rules.price_of(store, p)
        if min_p is not None and price.current < min_p:
            continue
        if max_p is None or price.current <= max_p:
            matches.append(p)
        elif price.pix <= max_p:
            pix_only.append(p)
    matches.sort(key=lambda p: (rules.price_of(store, p).current, p.product_id))

    result: dict[str, Any] = {
        "total_encontrado": len(matches),
        "itens": [product_summary(store, p) for p in matches[:limit]],
    }
    if len(matches) > limit:
        result["observacao"] = (
            f"Mostrando {limit} de {len(matches)} (ordem: menor preço). Não liste tudo: "
            "pergunte o que o cliente prefere para refinar."
        )
    if pix_only:
        result["cabem_no_orcamento_so_no_pix"] = [product_summary(store, p) for p in pix_only]
    if cat_id is not None and not any(p.category_id == cat_id for p in store.products.values()):
        result["categoria_sem_itens"] = (
            f"A categoria '{store.categories[cat_id].name}' existe na loja, mas não há nenhum "
            "item cadastrado no momento. Não é fora do escopo: ofereça registrar interesse."
        )
    elif not matches and not pix_only:
        result["observacao"] = "Nenhum item disponível com esses filtros."
    return result


# --- product details -------------------------------------------------------------------------

_SPEC_LABELS = {
    "top": "tampo", "back_sides": "fundo e laterais", "neck": "braço", "strings": "cordas",
    "scale": "escala", "electronics": "eletrônica", "color": "cor", "body": "corpo",
    "shells": "cascos", "pieces": "peças", "hardware": "ferragens", "keys": "teclas",
    "type": "tipo", "polyphony": "polifonia",
}  # fmt: skip
_SPEC_VALUES = {"steel": "aço", "yes": "sim", "no": "não", "included": "inclusas"}


def product_details(store: Store, product: Product) -> dict[str, Any]:
    avail = rules.availability(product)
    details: dict[str, Any] = {
        "id": product.product_id,
        "nome": product.name,
        "categoria": store.categories[product.category_id].name,
        "disponibilidade": avail.value,
        "descricao": product.description,
        "ficha_tecnica": {
            _SPEC_LABELS.get(k, k): _SPEC_VALUES.get(str(v), v) for k, v in product.specs.items()
        },
    }
    if avail is Availability.AVAILABLE:
        details["estoque"] = f"{product.stock} unidade(s)"
        details.update(price_info(store, product))
    else:
        details["situacao"] = {
            Availability.OUT_OF_STOCK: "temporariamente sem estoque",
            Availability.DISCONTINUED: "não faz mais parte do catálogo",
            Availability.COMING_SOON: (
                "em breve: ainda sem pronta entrega e sem pré-venda; ofereça registrar interesse"
            ),
        }[avail]
        details["preco"] = "não informar: o preço só vale para item disponível"
        details["alternativas_disponiveis"] = [
            product_summary(store, p) for p in rules.alternatives(store, product)
        ]
    if rules.needs_special_freight(store, product):
        details["frete"] = "fora de Campo Grande pode exigir frete especial com cotação individual"
    if issues := rules.data_quality_issues(product):
        details["alerta_dados"] = (
            "Cadastro inconsistente (" + "; ".join(issues) + "). Confie no nome e no preço; "
            "não afirme marca, modelo ou especificações da descrição. Se o cliente perguntar, "
            "explique que vai confirmar com um especialista da loja."
        )
    if expired := store.expired_promotions(product.product_id):
        details["promocoes_encerradas"] = {
            "uso": "só mencione se o cliente perguntar sobre promoção ou desconto",
            "lista": [f"{p.discount_percent}% ({p.description}) — encerrada" for p in expired],
        }
    return details


def get_product(store: Store, product: str | int) -> dict[str, Any]:
    text = str(product).strip()
    if text.isdigit():
        p = store.products.get(int(text))
        if p is None:
            return {"erro": f"não existe produto com id {text}"}
        return product_details(store, p)
    found = rules.find_products(store, text)
    if not found:
        return {"erro": "nenhum produto com esse nome no catálogo"}
    top_score = found[0][0]
    best = [p for s, p in found if s == top_score]
    if top_score >= 1 and len(best) == 1:
        return product_details(store, best[0])
    candidates = [
        {
            "id": p.product_id,
            "nome": p.name,
            "disponibilidade": rules.availability(p).value,
        }
        for _, p in found
    ]
    note = (
        "Mais de um produto corresponde; pergunte qual o cliente quer."
        if top_score >= 1
        else "Nenhum nome bate exatamente; estes são os mais parecidos. Confirme com o cliente."
    )
    return {"candidatos": candidates, "observacao": note}


# --- quote -------------------------------------------------------------------------------------


def quote(
    store: Store,
    items: list[dict[str, int]],
    *,
    payment: str | None = None,
    installments: int | None = None,
    city: str | None = None,
) -> dict[str, Any]:
    if not items:
        return {"erro": "informe ao menos um item (product_id e quantity)"}
    lines, errors = [], []
    total = total_pix = Decimal("0.00")
    special = False
    for item in items:
        pid, qty = int(item.get("product_id", 0)), int(item.get("quantity", 1) or 1)
        product = store.products.get(pid)
        if product is None:
            errors.append(f"produto {pid} não existe")
            continue
        avail = rules.availability(product)
        if avail is not Availability.AVAILABLE:
            errors.append(f"{product.name} está {avail.value}; não entra no orçamento")
            continue
        if qty < 1:
            errors.append(f"quantidade inválida para {product.name}")
            continue
        if qty > product.stock:
            errors.append(f"{product.name}: só há {product.stock} unidade(s) em estoque")
            continue
        price = rules.price_of(store, product, qty)
        line: dict[str, Any] = {
            "id": pid,
            "nome": product.name,
            "quantidade": qty,
            "valor": fmt_brl(price.current),
        }
        if price.on_promotion:
            line["valor_original"] = fmt_brl(price.table)
            line["promocao"] = f"{price.promo_percent}% de desconto ({price.promo_name})"
            line["valor_no_pix"] = f"{fmt_brl(price.pix)} (promoção não acumula com PIX)"
        else:
            line["valor_no_pix"] = f"{fmt_brl(price.pix)} (5% de desconto)"
        lines.append(line)
        total += price.current
        total_pix += price.pix
        special = special or rules.needs_special_freight(store, product)

    result: dict[str, Any] = {"itens": lines}
    if errors:
        result["problemas"] = errors
    if not lines:
        return result

    total, total_pix = round_money(total), round_money(total_pix)
    n_max = rules.max_installments(total)
    result["total"] = fmt_brl(total)
    result["total_no_pix"] = fmt_brl(total_pix)
    if total_pix < total:
        result["economia_no_pix"] = fmt_brl(total - total_pix)
    result["parcelamento_maximo"] = (
        f"{n_max}x de {fmt_brl(rules.installment_value(total, n_max))} sem juros"
    )
    if installments is not None:
        n = int(installments)
        if rules.installment_allowed(total, n):
            result["parcelamento_pedido"] = (
                f"{n}x de {fmt_brl(rules.installment_value(total, n))} sem juros: permitido"
            )
        else:
            result["parcelamento_pedido"] = (
                f"{n}x não é permitido para {fmt_brl(total)} (regras da seção 3.1); "
                f"o máximo é {n_max}x"
            )
    if payment == "boleto":
        result["boleto"] = "compensação em até 3 dias úteis"
    if total > rules.COMBINED_PAYMENT_MIN:
        result["pagamento_combinado"] = (
            "permitido (ex.: PIX + cartão) por ser acima de R$ 2.000,00; o desconto do PIX "
            "na parte combinada não está definido na política: a equipe confirma"
        )

    def ship(amount: Decimal) -> str:
        if city is None:
            return "depende da cidade: pergunte a cidade (Campo Grande tem regra própria)"
        s = rules.shipping_for(amount, city, special)
        if s.fee is None:
            text = "calculado pelo CEP de destino (Correios PAC/SEDEX ou Jadlog); peça o CEP"
            if s.special_freight:
                text += "; instrumento de grande porte pode exigir frete especial com cotação"
            return text
        fee = "grátis" if s.fee == 0 else fmt_brl(s.fee)
        return f"{fee} (motoboy próprio, 1 a 3 dias úteis)"

    paid_by_payment = {"pix": total_pix}.get(payment or "", total)
    if payment is None and rules.is_metro(city) and ship(total) != ship(total_pix):
        result["frete"] = {"pagando no PIX": ship(total_pix), "outras formas": ship(total)}
    else:
        result["frete"] = ship(paid_by_payment)
    return result
