# Report 01 — Static Code, Domain Logic, LangGraph State & Evaluation Audit

- **Target Commit Audited:** `9d5b635` (`main`)
- **Scope:** All 16 Python modules in [`src/emporio_agent/`](../src/emporio_agent/), all 8 test modules in [`tests/`](../tests/), [`data/policies.md`](../data/policies.md) vs. [`data/políticas_da_loja.pdf`](../data/políticas_da_loja.pdf) (all 8 pages), the 6 operational CSVs in [`data/`](../data/), and [`evals/`](../evals/).
- **Runtime Verified Against:** Python `3.12.14`, `langgraph 1.2.19`, `langchain 1.4.8`, `langchain-google-genai 4.4.2`, `langchain-anthropic 1.7.9`, `holidays 0.108`.

---

## Severity Overview

| Severity | Count | Key Themes |
|---|---:|---|
| **Critical** | **6** | Out-of-the-box `pytest` failure on `en_US` locales (`clock.py`); silent `0026 AD` 2-digit year bug (`tools.py`); Campo Grande shipping rejected on `"Campo Grande - MS"` / `"CG"` (`rules.py`); corrupted catalog descriptions indexed in search (`catalog.py`); duplicate-line stock-limit bypass in `quote` (`catalog.py`); mid-turn API failure bricking conversation checkpoints (`cli.py` / `graph.py`). |
| **High** | **10** | Ambiguous brand `get_product` picking shortest SKU including discontinued (`catalog.py`); installments approved on `pix`/`boleto`/`debito` (`catalog.py`); missing §7.1 5-minute WhatsApp SLA (`policies.md` / `prompts.py`); Portuguese plural/hyphen/vocabulary search blind spots (`catalog.py`); `0`-prefixed DDD phone rejection burning lockout attempts (`orders.py`); `check_return` self-contradicting under `--now` (`returns.py`); `MODEL_EFFORT` breaking `claude-haiku-5-5` (`llm.py`); mid-session customer account overwrite & lockout desync (`tools.py`); `evals.py` numeric-faithfulness false negatives & false positives (`evals.py`). |
| **Medium** | **12** | `quantity=0` coerced to `1`; PIX costing more than card after shipping flip; ascending `limit<=10` hiding high-end violões; `alternatives()` ignoring ukulele size/tuning; `TicketStore` cross-process race & `0644` PII permissions; unverified `open_ticket` order spoofing via `summary`; `invalid_tool_calls` / empty reply handling; unbounded `O(T^2)` history growth; uncaught CLI `--now` / YAML `--script` crashes; `evals.py --only` typo exiting `0` (`0/0`) and overwriting reports. |
| **Low** | **6** | Minor CDC/policy edge clauses (§4.1 presencial, §4.4 boquilhas, §5.2 transit damage); internal manual section numbers in tool outputs; optional Brazilian holidays (`Carnaval`, `Corpus Christi`); multi-line tool errors breaking Markdown `--export` fences; `AIMessage.text` block concatenation; dead fields/helpers in `data.py`. |

---

## 1. Critical Findings

### [C-01] `holidays.Brazil` omits `language="pt_BR"`, breaking 4 unit tests out-of-the-box and leaking English holiday names on `en_US` locales
- **Location:** [`src/emporio_agent/clock.py`](../src/emporio_agent/clock.py#L70-L71) (breaks [`tests/test_clock.py`](../tests/test_clock.py#L31-L49) and [`tests/test_agent.py`](../tests/test_agent.py#L72-L194))
- **Mechanism:** `clock.py:71` calls `holidays.Brazil(subdiv="MS", years=year)` with `language=None`. In `holidays>=0.108`, `HolidayBase.__init__` inspects OS environment variables (`LANGUAGE`, `LC_ALL`, `LC_MESSAGES`, `LANG`). Inside a cloud container with `LANG=C.UTF-8` (`"C"` is not a translation locale), `holidays` falls back to `Brazil.default_language = "pt_BR"`. On standard developer and CI machines running `LANG=en_US.UTF-8`, `holidays` translates Brazilian holidays into **English** (`"National Day of Zumbi and Black Awareness"`, `"State Creation Day"`). Ironically, [`src/emporio_agent/money.py`](../src/emporio_agent/money.py#L4-L5) explicitly avoided Python's `locale` module for currency formatting, while `clock.py` implicitly depended on system locale.
- **Reproduction:**
  ```bash
  $ LANG=en_US.UTF-8 uv run pytest
  FAILED tests/test_agent.py::test_parallel_tool_calls_in_one_step - AssertionError: assert 'Consciência Negra' in 'sexta-feira, 20/11/2026: fechado (feriado: National Day of Zumbi and Black Awareness)'
  FAILED tests/test_agent.py::test_closed_day_reports_next_opening - AssertionError: assert 'Consciência Negra' in 'sexta-feira, 20/11/2026: fechado (feriado: National Day of Zumbi and Black Awareness)'
  FAILED tests/test_clock.py::test_consciencia_negra_is_closed - AssertionError: assert 'Consciência Negra' in 'National Day of Zumbi and Black Awareness'
  FAILED tests/test_clock.py::test_ms_state_holiday - AssertionError: assert 'State Creation Day' == 'Criação do Estado'
  4 failed, 154 passed
  ```
- **Impact:** Immediate `uv run pytest` failure for evaluators on English OS locales, contradicting [`README.md`](../README.md#L55) (`158 testes`), plus English holiday strings injected into [`src/emporio_agent/prompts.py`](../src/emporio_agent/prompts.py#L131) and `check_store_hours`.

---

### [C-02] `_parse_day` parses 2-digit years (`dd/mm/aa`) as 1st-century AD (`0026-11-20`), falsely reporting the store OPEN on holidays and rejecting valid return dates
- **Location:** [`src/emporio_agent/tools.py`](../src/emporio_agent/tools.py#L46-L57) (called by `check_store_hours` at [`L145`](../src/emporio_agent/tools.py#L145) and `check_return` at [`L276`](../src/emporio_agent/tools.py#L276))
- **Mechanism:** Line 50 parses slash-separated dates via `lambda t: date(*reversed([int(x) for x in t.split("/")]))`. Python's `datetime.date(year, month, day)` accepts any `1 <= year <= 9999`. When a customer or LLM supplies a Brazilian 2-digit year like `"20/11/26"` or `"17/02/26"`, `date(26, 11, 20)` succeeds without raising `ValueError`, returning **November 20, 0026 AD**! Worse: on Linux/glibc, `strftime("%d/%m/%Y")` formats year `26` as `"20/11/26"` without zero-padding, masking the century error in tool output.
- **Concrete Failing Inputs:**
  1. **`check_store_hours(day="20/11/26")`** (Consciência Negra national holiday): `holidays.Brazil(years=26)` has no modern holidays in 26 AD, and 20/11/0026 was a Thursday (`hours_on` returns open `09:00–18:00`), so the tool **falsely tells the customer the store is OPEN (`09:00 às 18:00`) on a closed holiday**!
  2. **`check_return(order_id=7, reason="arrependimento", received_on="17/02/26")`**: parses `receipt = date(26, 2, 17) < order.order_date`, failing with `"data de recebimento inválida para este pedido"`.
  3. **Year-boundary bug (`tools.py:51`)**: `dd/mm` hardcodes `today.year`. Calling `check_return(..., received_on="22/12")` on `2026-01-05` for Order #4 (`2025-12-10`) constructs `2026-12-22` (11 months in the future) and rejects it; calling `check_store_hours(day="02/01")` on `2026-12-30` checks `2026-01-02` (past year, wrong weekday). Hyphenated `"17-02-2026"` also returns `None`.

---

### [C-03] `is_metro` exact-string check rejects `"Campo Grande - MS"`, `"Campo Grande/MS"`, `"CG"`, and `city=""` misroutes quotes to Correios/Jadlog
- **Location:** [`src/emporio_agent/rules.py`](../src/emporio_agent/rules.py#L34) & [`L140-L141`](../src/emporio_agent/rules.py#L140-L141), and [`src/emporio_agent/catalog.py`](../src/emporio_agent/catalog.py#L348-L366)
- **Mechanism:**
  1. `METRO_CITIES = frozenset({"campo grande"})` and `is_metro` checks `normalize(city) in METRO_CITIES`. Any state suffix or common local shorthand — including `"Campo Grande - MS"` (used verbatim in [`data/policies.md`](../data/policies.md#L31)) and `"Campo Grande/MS"` (used verbatim in [`src/emporio_agent/prompts.py`](../src/emporio_agent/prompts.py#L17)) — normalizes to `"campo grande ms"` or `"cg"`, returning `False`.
  2. In `catalog.py:348` and `366`, `quote` checks `if city is None:` rather than `if not (city and city.strip()):`. Passing `city=""` treats the empty string as a non-Campo-Grande destination instead of asking for the customer's city.
  3. Moreover, `catalog.py:352` instructs the LLM `"peça o CEP"`, causing the agent to invite customers to send their CEP even though **no tool in the system accepts a CEP or computes Correios/Jadlog freight**.
- **Concrete Failing Input:**
  - `quote(store, [{"product_id": 95, "quantity": 1}], city="Campo Grande - MS")` returns `"frete": "calculado pelo CEP de destino (Correios PAC/SEDEX ou Jadlog); peça o CEP"` and omits `total_com_frete`, denying local Campo Grande customers their free motoboy delivery (`grátis`, 1–3 business days).

---

### [C-04] `_haystack` indexes corrupted `product.description` on inconsistent SKUs while `product_summary` hides it
- **Location:** [`src/emporio_agent/catalog.py`](../src/emporio_agent/catalog.py#L87-L103) and [`L197-L224`](../src/emporio_agent/catalog.py#L197-L224)
- **Mechanism:** `rules.data_quality_issues` flags 7 SKUs (`135, 136, 137, 139, 140, 142, 144`) whose `description` names a **wrong brand or wrong specification** (`#135 Music Man Bass 1X` says `"Fender Jazz Bass"`; `#137 Yamaha Bass 3X` says `"5 cordas Ibanez"`; `#140 Pearl Kit 2` says `"Tama"`; `#142 Korg Synth 1 Pro` says `"Roland com 88 teclas"`). `product_summary` (`L87-90`) omits `descricao` and sets `alerta_dados`, **but `_haystack` (`L99`) still indexes `product.description` unconditionally**!
- **Concrete Failing Inputs:**
  - `search_catalog(store, query="Fender", category="baixos")` -> returns `[#135 Music Man Bass 1X Electric Bass]`!
  - `search_catalog(store, query="5 cordas", category="baixos")` -> returns `[#137 Yamaha Bass 3X Electric Bass]` (4-string)!
  - `search_catalog(store, query="Tama", category="baterias_percussao")` -> returns `[#140 Bateria Acústica Pearl Kit 2 Studio]`!
  - `search_catalog(store, query="88 teclas", category="teclados_pianos")` -> returns `[#142 Teclado Sintetizador Korg Synth 1 Pro]` (61-key)!
  - Additionally, `product_details` (`L198-200`) still returns `ficha_tecnica` (`Ash/Maple/4` on all basses, `Maple/5` on all drums, `Synthesizer/61/Black` on all synths) as clean truth even on SKUs `135–144`, and SKU `#143` (`Teclado Sintetizador Nord Synth 2 Pro` vs. `"Piano de palco Nord Stage"` vs. `type: Synthesizer, keys: 61`) is not flagged by `data_quality_issues` at all.

---

### [C-05] `quote` validates `qty > product.stock` per line item instead of per `product_id`, allowing stock-limit bypass and 1-cent PIX drift
- **Location:** [`src/emporio_agent/catalog.py`](../src/emporio_agent/catalog.py#L279-L311)
- **Mechanism:** `quote` iterates over `items` without merging duplicate `product_id` entries. Each dict is checked independently against `product.stock` (`L292`) and rounded independently (`rules.price_of(store, product, qty)`).
- **Concrete Failing Inputs:**
  1. **Inventory bypass:** `#108 Martin D-28E` has `stock = 1`. Calling `quote(store, [{"product_id": 108, "quantity": 1}, {"product_id": 108, "quantity": 1}])` checks `1 > 1` (`False`) twice and quotes **2 units (`R$ 24.000,00`) with zero `problemas`**.
  2. **PIX rounding drift:** `#81 Yamaha C40` (`R$ 599,90`) passed as two `quantity=1` lines yields `total_no_pix = "R$ 1.139,82"` (`569,91 * 2`), whereas one `quantity=2` line yields `"R$ 1.139,81"`.

---

### [C-06] Mid-turn LLM failure in `safe_send` leaves partial messages in checkpoint state, corrupting subsequent turns
- **Location:** [`src/emporio_agent/cli.py`](../src/emporio_agent/cli.py#L78-L99) and [`src/emporio_agent/graph.py`](../src/emporio_agent/graph.py#L60-L70)
- **Mechanism:** LangGraph checkpoints `HumanMessage` before `agent`, `AIMessage(tool_calls)` after step 1, and `ToolMessage`s after `ToolNode`. If the LLM raises an API error (`503`, `429`, network timeout) during step 1 or during the post-tool synthesis call, `safe_send` (`cli.py:92-97`) catches the exception and keeps the REPL alive without rolling back the checkpoint. On the next user input:
  - `[HumanMessage, AIMessage(tool_call), ToolMessage, HumanMessage]` violates turn-ordering invariants in `ChatGoogleGenerativeAI` (two consecutive `role='user'` `Content` blocks: `FunctionResponse` followed immediately by text without a `role='model'` response) and `ChatAnthropic` (`400 Bad Request` on dangling `tool_use`/`tool_result` or consecutive user messages).
  - Side effects executed in step 2 (`TicketStore.open` writing to `.state/tickets.jsonl`, `verify_customer` incrementing `verification_failures`) remain committed while `session.turns` (`cli.py:82`) drops the turn.

---

## 2. High Findings

### [H-01] `get_product` breaks brand/prefix ambiguity ties by shortest product name instead of returning `candidatos`
- **Location:** [`src/emporio_agent/catalog.py`](../src/emporio_agent/catalog.py#L243-L246) and [`src/emporio_agent/rules.py`](../src/emporio_agent/rules.py#L259-L263)
- **Mechanism:** [`tools.py`](../src/emporio_agent/tools.py#L100) promises: *"Se o nome for ambíguo, devolve candidatos para o cliente escolher."* However, `find_products` scores substring matches as `1.0 + len(joined) / len(name_c)`, and `get_product` only returns `candidatos` when `len([p for s, p in found if s == top_score]) > 1`. Because SKUs of the same brand have different name lengths (`len(name_c)`), **12 of 14 multi-SKU brands** produce a unique `top_score` winner — whichever SKU happens to have the shortest name!
- **Concrete Failing Inputs:**
  - `get_product(store, "Ibanez")` -> **silently returns ONLY discontinued `#136 Ibanez Bass 2X Electric Bass`** (`24` compact chars) and hides available `#132 Ibanez RG550 Genesis Collection` (`28` chars)!
  - `get_product(store, "Takamine")` -> silently returns `#95 GD20`, hiding `#100`, `#105`, `#115`.
  - `get_product(store, "Yamaha")` -> silently returns `#87 F310`, hiding 8 other Yamaha instruments across 4 categories.
  - `get_product(store, "Martin D-28")` -> silently returns `#93 Martin D-28`, hiding `#108 Martin D-28E`.
  - [`tests/test_domain.py`](../tests/test_domain.py#L232) missed this because it tested `rules.find_products(store, "Takamine")` rather than `catalog.get_product(store, "Takamine")`.

---

### [H-02] `quote` approves credit-card installments when `payment` is `"pix"`, `"boleto"`, or `"debito"`
- **Location:** [`src/emporio_agent/catalog.py`](../src/emporio_agent/catalog.py#L325-L338)
- **Mechanism:** `quote` evaluates `rules.installment_allowed(total, n)` without checking `payment`. Per Policy §3, PIX, Cartão de Débito, and Boleto Bancário are strictly *pagamento à vista*.
- **Concrete Failing Input:** `quote(store, [{"product_id": 95}], payment="boleto", installments=6)` returns `"parcelamento_pedido": "6x de R$ 366,50 sem juros: permitido"` alongside `"boleto": "compensação em até 3 dias úteis"`.

---

### [H-03] Policy §7.1 5-minute WhatsApp response-time SLA is omitted from both `policies.md` and `prompts.py`
- **Location:** [`data/policies.md`](../data/policies.md#L5-L7) & [`L36-L39`](../data/policies.md#L36-L39) and [`src/emporio_agent/prompts.py`](../src/emporio_agent/prompts.py#L15-L118) vs. [`data/políticas_da_loja.pdf`](../data/políticas_da_loja.pdf) p. 6 (§7.1)
- **Mechanism:** `policies.md:5-7` omitted §7 assuming all §7 rules were placed in `STATIC_PROMPT`. However, §7.1's explicit SLA — *"Tempo de resposta: máximo de 5 minutos durante o horário de funcionamento"* — was dropped from **both** files. Neither `consult_policy` nor `STATIC_PROMPT` can answer *"Qual o tempo máximo de resposta no WhatsApp durante o expediente?"*.

---

### [H-04] `search_catalog` vocabulary, irregular-plural, and hyphenation blind spots miss valid in-stock instruments
- **Location:** [`src/emporio_agent/catalog.py`](../src/emporio_agent/catalog.py#L98-L115)
- **Mechanism & Failing Queries:**
  1. **Irregular Portuguese plurals (`-ão`/`-ões`, `-ais`, `-ores`):** `_matches_query` (`L112`) only strips a trailing `"s"` when `len(tok) > 4`. Query `"violao"` (`stem="violao"`) does not prefix-match category `"Violões"` (`"violoes"`), making `#108 Martin D-28E Elétrico Aço Natural` (whose name/description omit the word `"violão"`) invisible to `query="violao"` and `query="violao eletrico"`. Likewise `"profissionais"` -> `"profissionai"` misses `"profissional"`.
  2. **`query="violao acustico"` returns `0` of 20 acoustic guitars:** None of the 20 non-electric guitars contain `"acústico"` in their CSV fields (`"clássico"`, `"folk"`, `"dreadnought"`), and `_haystack` injects no `"acustico"` keyword when `has_electronics is False`.
  3. **`query="baixo eletrico"` misses `#137` and `query="eletroacustico"` misses `#94`:** `#137 Yamaha Bass 3X Electric Bass` uses English `"Electric"` without `"elétrico"`; `#94 Taylor 110e` (`electronics="yes"`) has `"eletrônica ES2"` without `"elétrico"` or `"eletroacústico"`.
  4. **Hyphenated / spaced model codes return `0`:** Unlike `get_product` (which uses `compact()`), `_matches_query` splits on punctuation, so `search_catalog(query="GD-20")`, `"GD 20"`, `"AC39"`, `"C-40"`, and `"KA15S"` all return `total_encontrado: 0`.

---

### [H-05] `normalize_phone` rejects `0`-prefixed DDDs (`067...`), `+55 067...`, and 10-digit `+55` landlines — burning verification attempts
- **Location:** [`src/emporio_agent/orders.py`](../src/emporio_agent/orders.py#L38-L45) & [`L67-L81`](../src/emporio_agent/orders.py#L67-L81), and [`src/emporio_agent/tools.py`](../src/emporio_agent/tools.py#L210-L214)
- **Mechanism:** `normalize_phone` only normalizes `len(d) == 13 and d.startswith("55")` and `len(d) == 9`.
  - Trunk-prefixed `"(067) 98543-2109"` (`12` digits `"067985432109"`), `"+55 (067) 98543-2109"` (`14` digits), and `"+55 67 3341-4444"` (`12` digits) are returned unnormalized, failing equality against 11-digit CSV phones and **incrementing `verification_failures` toward the 3-strike lockout**. Passing `order_id=0` also counts as a factor (`0 is not None`) and burns an attempt.

---

### [H-06] `check_return` rejects its own `estimated_delivery` fallback when `--now` falls between `order_date` and `estimated_delivery`
- **Location:** [`src/emporio_agent/returns.py`](../src/emporio_agent/returns.py#L81-L87) and [`src/emporio_agent/orders.py`](../src/emporio_agent/orders.py#L33-L35)
- **Mechanism:** `visible_orders` filters only by `o.order_date <= today`. When `--now` is set between `order_date` and `estimated_delivery - 1` on any of the 7 static `DELIVERED` orders (e.g., `--now 2026-02-10` for Order #7, ordered `03/02`, `estimated_delivery = 17/02`), `order.status` is still `DELIVERED`, so `check_return` sets `receipt = order.estimated_delivery` (`17/02`), hits `if receipt > today:` (`17/02 > 10/02`), and returns `{"elegivel": None, "situacao": "data de recebimento inválida para este pedido"}` against its own database fallback!

---

### [H-07] `MODEL_EFFORT` is passed unconditionally for all `anthropic:*` models, breaking `anthropic:claude-haiku-5-5` with HTTP 400
- **Location:** [`src/emporio_agent/llm.py`](../src/emporio_agent/llm.py#L47-L50)
- **Mechanism:** Setting `MODEL_EFFORT=low` in `.env` (as suggested in [`README.md`](../README.md#L33)) passes `effort="low"` to `ChatAnthropic` for every `anthropic:*` model, including `claude-haiku-5-5` and `claude-sonnet-4-5`, which reject `output_config.effort` with HTTP `400`. Additionally, `supports_prompt_cache` (`L28`) checks `provider == "anthropic"` only (missing `bedrock` / `bedrock_converse`), and `parse_spec` does not lowercase `provider`.

---

### [H-08] Session state allows mid-conversation customer account overwrite and desynchronizes `verified_customer_id` from lockout
- **Location:** [`src/emporio_agent/tools.py`](../src/emporio_agent/tools.py#L190-L225) and [`src/emporio_agent/prompts.py`](../src/emporio_agent/prompts.py#L136-L140)
- **Mechanism:**
  1. **Account switching with PII retention:** `verify_customer` does not block re-verification when `verified_customer_id` is already set. Verifying Customer B overwrites `verified_customer_id` while Customer A's order details remain in `state["messages"]` visible to the model.
  2. **Lockout desync:** `verification_failures` (`Annotated[int, operator.add]`) never resets on success. Two typos before verifying + one failed call afterward sets `verification_failures == 3`, locking `verify_customer` while `verified_customer_id` stays active and `dynamic_context` (`if verified_name: ... elif locked:`) hides the lockout banner.

---

### [H-09] `evals.py` `_MONEY` regex has false negatives on Markdown/unprefixed prices and false positives on `"R$ 1,5 mil"`
- **Location:** [`src/emporio_agent/evals.py`](../src/emporio_agent/evals.py#L45-L56)
- **Mechanism:** `_MONEY = re.compile(r"R\$\s?(\d{1,3}(?:\.\d{3})*(?:,\d{2})?|\d+(?:,\d{2})?)")`
  - **False negatives (hallucinations missed):** `R$ **1.999,00**`, `**R$** 1.999,00`, `R$  1.999,00` (two spaces), and `"1.850 reais"` / `"12x de 150,00"` yield `set()`, bypassing numeric faithfulness completely.
  - **False positive (valid answer failed):** If a customer says `"tenho uns 1,5 mil"` and the agent replies `"na faixa de R$ 1,5 mil"`, `_MONEY` stops before `,5` (since `,5` is not 2 digits) and extracts `Decimal('1')`, failing the turn with `sem origem: 1`.

---

### [H-10] `evals.py` `grounded` set unions all bare user numbers and `consult_policy` thresholds across the conversation
- **Location:** [`src/emporio_agent/evals.py`](../src/emporio_agent/evals.py#L136-L141)
- **Mechanism:** `check_turn` merges `plain_numbers(past.user)` (including haggling offers, quantities, order IDs) and `money_values(out)` from all tools (including `consult_policy`, which contains `R$ 35,00`, `R$ 50,00`, `R$ 80,00`, `R$ 100,00`, `R$ 500,00`, `R$ 2.000,00`). If a customer asks *"Faz o Takamine GD20 por 1800?"* and the agent hallucinates *"Fechado por R$ 1.800,00!"*, `1800` is in `grounded` and `check_turn` **passes**.

---

## 3. Medium Findings

- **[M-01] `catalog.quote` coerces `quantity=0` to `1` ([`catalog.py`](../src/emporio_agent/catalog.py#L280)):** `int(item.get("quantity", 1) or 1)` evaluates `0 or 1` -> `1`, quoting 1 unit (`R$ 599,90`) on direct Python calls and making `if qty < 1:` (`L289`) unreachable for `0`.
- **[M-02] Partial-cart `"total"` and PIX shipping-threshold flip ([`catalog.py`](../src/emporio_agent/catalog.py#L313-L381)):** (a) In mixed carts where one SKU exceeds stock, unavailable items go to `problemas` while top-level `"total"` silently reflects only the remaining SKU; (b) for a Campo Grande cart totaling `R$ 509,80` (`1x #120` + `1x #119`), card gets free shipping (`total_com_frete = R$ 509,80`) while PIX (`R$ 484,32 < R$ 500`) triggers `R$ 35,00` shipping (`total_com_frete = R$ 519,32` — `R$ 9,52` **more expensive** on PIX!), yet `quote` still reports `"economia_no_pix": "R$ 25,48"`.
- **[M-03] `search_catalog` ascending-only `limit<=10` truncation, unbounded `pix_only`, and stopword match-all ([`catalog.py`](../src/emporio_agent/catalog.py#L106-L175)):** With 33 available `violoes`, `search_catalog` always sorts cheapest-first (`max R$ 749,00` in top 10), hiding flagship guitars (`#108 Martin D-28E` at `R$ 12.000,00`) when asked *"Qual o violão mais caro?"*; `product_summary` also omits stock quantity and `promocoes_encerradas`; `pix_only` ignores `min_p` and `limit`; stopword/punctuation-only queries (`"modelo"`, `"???"`) match all 61 available items.
- **[M-04] `rules.alternatives` ignores ukulele body/tuning size ([`rules.py`](../src/emporio_agent/rules.py#L174-L195)):** For `coming_soon` Baritone ukulele `#130` (tuned DGBE), `alternatives()` suggests two Tenor ukuleles (`#126`, `#125`, tuned GCEA) and omits in-stock Baritone `#128` due to price distance.
- **[M-05] `TicketStore` cross-process race, crash on partial JSONL line, `0644` PII permissions, and `--script` side effects ([`tickets.py`](../src/emporio_agent/tickets.py#L30-L72), [`cli.py`](../src/emporio_agent/cli.py#L174)):** `threading.Lock()` does not synchronize across processes (`fcntl.flock`); `all()` crashes with `JSONDecodeError` on truncated lines; `.state/tickets.jsonl` is created `0644` (world-readable) with customer contact PII; `--script` writes real tickets to `.state/tickets.jsonl`.
- **[M-06] Unverified `open_ticket` order spoofing via `summary` & raw `order.notes` injection ([`tools.py`](../src/emporio_agent/tools.py#L282-L308), [`orders.py`](../src/emporio_agent/orders.py#L109-L110)):** Unverified/locked-out users cannot pass `order_id`, but can embed `"Cancelar pedido #10"` in `summary` with an arbitrary `contact` (observed in `evals/report.md:138`). `order.notes` is also passed raw into tool JSON without untrusted-data framing.
- **[M-07] `invalid_tool_calls` and empty post-tool `AIMessage` handling ([`cli.py`](../src/emporio_agent/cli.py#L54-L69), [`graph.py`](../src/emporio_agent/graph.py#L68)):** Malformed tool JSON (`AIMessage.invalid_tool_calls`) routes to `END` with an empty reply; if step 1 emitted narration (`"Vou verificar..."`) and step 3 returned empty content (e.g., `MAX_TOKENS`/safety filter), `replies[-1]` surfaces step 1's stale narration as the final answer.
- **[M-08] Unbounded `state["messages"]` quadratic `O(T^2)` growth ([`graph.py`](../src/emporio_agent/graph.py#L60-L62)):** Every historical `ToolMessage` (`consult_policy` Markdown sections, `search_catalog` JSON arrays) is re-sent on every LLM invocation without trimming or compaction.
- **[M-09] Uncaught exceptions on CLI `--now`, `--script` YAML edge cases, and provider errors ([`cli.py`](../src/emporio_agent/cli.py#L162-L205)):**
  - `--now invalid-date` or `--now 20/02/2026` crashes with a raw `ValueError` traceback (`cli.py:193` only catches `ModelConfigError`).
  - `load_script` (`cli.py:164`) checks `not data.get("turns")` instead of `not isinstance(data.get("turns"), list)`: if `turns: "Oi"`, `for text in script["turns"]` iterates character-by-character (`'O'`, `'i'`), invoking the LLM per character!
  - Unquoted integer turns in YAML (`turns: [130]`) crash `HumanMessage` with Pydantic `ValidationError`; empty string turns (`turns: [""]`) fail in `ChatGoogleGenerativeAI` with `ValueError: contents are required`; malformed YAML syntax crashes with uncaught `yaml.YAMLError`.
- **[M-10] `evals.py --only <typo>` exits `0` (`0/0`) and overwrites `--report` ([`evals.py`](../src/emporio_agent/evals.py#L241-L255)):** A mistyped `--only` name produces `0/0`, overwrites `--report` with an empty report, and returns exit code `0` (CI green); `args.report.write_text` also lacks `parent.mkdir(parents=True, exist_ok=True)`.
- **[M-11] `evals.py` redundant 24x init & missing `TicketStore` assertions ([`evals.py`](../src/emporio_agent/evals.py#L164-L246)):** `evals.py` reloads CSVs and `init_chat_model` 24 times per suite instead of failing fast on missing provider packages, and never asserts on `tickets.all()`.
- **[M-12] Brittle substring bans in `evals/scenarios*.yaml` ([`scenarios.yaml`](../evals/scenarios.yaml#L161), [`scenarios_dificeis.yaml`](../evals/scenarios_dificeis.yaml#L198-L207)):** Banning common Portuguese words `"confirmado"` and `"entregue"` on unverified-access scenarios risks false failures on benign refusals (*"Para saber se seu pedido foi entregue..."*).

---

## 4. Low Findings

- **[L-01] Minor policy & CDC nuances ([`returns.py`](../src/emporio_agent/returns.py#L28-L111), [`policies.md`](../data/policies.md#L193-L198)):** `returns.py` omits §4.4 `boquilhas de instrumentos de sopro`, §8.3 `palhetas de sopro`, and §5.2 transit-damage coverage (`avaria no transporte`); applies §4.4 `"venda final"` to §4.1 online `arrependimento` (unconditional under CDC Art. 49); routes unshipped `preferencia` requests only to `cancelamento`; and `policies.md` does not explicitly contrast online (§4.1) vs. in-store (§4.3 only) withdrawal rights.
- **[L-02] Internal manual section numbers leaked in tool strings ([`catalog.py`](../src/emporio_agent/catalog.py#L336), [`returns.py`](../src/emporio_agent/returns.py#L105-L170)):** `políticas_da_loja.pdf` cover states *"Documento interno — Uso restrito da equipe de atendimento"*, yet tools embed `(seção 3.1)`, `(seção 4.1)`, `(seção 8.1)` without prompt guidance not to cite internal manual section numbers to customers.
- **[L-03] Optional Brazilian holidays reported as open ([`clock.py`](../src/emporio_agent/clock.py#L70-L71)):** `holidays.Brazil(subdiv="MS")` only loads `PUBLIC` holidays, reporting normal weekday hours `09:00–18:00` on `Carnaval` (`16–17/02/2026`) and `Corpus Christi` (`04/06/2026`) without caveat.
- **[L-04] Multi-line `ToolNode` errors break Markdown fences in `--export` ([`cli.py`](../src/emporio_agent/cli.py#L154-L156)):** `f"  {tc.result}"` only indents line 1 of multi-line validation errors inside `<details>`.
- **[L-05] `AIMessage.text` concatenates multiple text content blocks without separator ([`cli.py`](../src/emporio_agent/cli.py#L49-L51)):** Adjacent text blocks join as `"AB"` instead of `"A\nB"`.
- **[L-06] Unused fields and dead helper in `data.py` ([`data.py`](../src/emporio_agent/data.py#L45-L142)):** `Store.category_slug_of` (`L141`) is dead code; `Category.description` (`L45`, containing `"Flautas, clarinetes, saxofones, oboés"`, `"Violinos, violas, violoncelos"`, etc.) is loaded and never indexed; `Customer.first_name` (`self.name.split()[0]`) raises `IndexError` on blank names.
