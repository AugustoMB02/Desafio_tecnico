# Report 00 — Executive QA & Red-Team Audit Summary

> **Status (added after the audit):** these reports describe `main` at `9d5b635`, before the fixes. Every finding and what was done about it is in [`04_resposta_ao_qa.md`](04_resposta_ao_qa.md).

- **Repository:** `https://github.com/AugustoMB02/Desafio_tecnico`
- **Audited Commit:** `9d5b635` (`main`) + unmerged branches `origin/feat/persistencia-sqlite`, `origin/feat/web-ui-gradio`, `origin/feat/persistencia-e-web`
- **Audit Scope:** Static line-by-line review of all 16 source modules & 8 test files + **89 live `google_genai:gemini-3.5-flash` turns** (42 adversarial conversations, 12 `Pass^3` trials, 6 CLI subprocess probes) + full deliverables & GitHub audit.
- **Code Modification Status:** **Read-only (`0` existing files modified)** per instructions (*"don't fix anything yet"*).

---

## Companion Detailed Reports

1. **[`01_static_code_and_architecture_audit.md`](01_static_code_and_architecture_audit.md)** — Static code, domain math/date/phone/city rules, search & stemming, LangGraph state/checkpoints, multi-provider `llm.py`, and `evals.py` checker bugs (`6 Critical`, `10 High`, `12 Medium`, `6 Low`).
2. **[`02_live_chatbot_redteam_report.md`](02_live_chatbot_redteam_report.md)** — Live adversarial red-teaming against `google_genai:gemini-3.5-flash`, latency distribution (`median 7.63s`, `p90 12.87s`), end-to-end exploit traces, defense verifications, and `Pass^3` (`12/12`) consistency table.
3. **[`03_deliverables_and_branches_audit.md`](03_deliverables_and_branches_audit.md)** — Artefact submission checklist, GitHub `HTTP 404` blocker, `examples/03` transcript defect, documentation contradictions, standalone scripts, and `feat/persistencia-e-web` (`Gradio` + `SqliteSaver`) audit.

---

## Overall Assessment

The core architecture — a single LangGraph agent loop backed by deterministic `Decimal` pricing, `Command`/`InjectedState` customer-ID isolation, read-only CSVs + append-only `.state/tickets.jsonl`, and dual-suite deterministic + live YAML evaluations — is **clean, well-structured, and resilient on its covered paths** (`pass^3 = 100%` across 12 live multi-turn trials; zero price leaks on unavailable/discontinued/coming-soon SKUs; zero PII leaks on shared-email social engineering; zero secrets committed to git history).

However, our multi-agent audit uncovered **3 submission-blocking deliverable defects** and **12 high-impact code/security/policy bugs** that will surface immediately during evaluator testing or adversarial probing if left unpatched.

---

## Consolidated Top Priority Matrix (Must-Fix vs. Should-Fix)

### Tier 1 — Immediate Submission Blockers (Deliverables & Test Suite)

| Rank | ID | Severity | Location | Issue & Evaluator Impact |
|---:|---|---|---|---|
| **1** | **D-01** | **CRITICAL** | GitHub Settings | **Repo is still Private (`HTTP/2 404`)**: unauthenticated evaluators opening `https://github.com/AugustoMB02/Desafio_tecnico` hit a 404 page (Deliverable #1 blocker). |
| **2** | **C-01 / D-02** | **CRITICAL** | [`clock.py:71`](../src/emporio_agent/clock.py#L70-L71) | **`uv run pytest` fails out-of-the-box (`4/158 failed`) on `LANG=en_US.UTF-8`**: `holidays.Brazil(subdiv="MS", years=year)` omits `language="pt_BR"`, returning English holiday names (`'National Day of Zumbi...'`, `'State Creation Day'`) in tests and tool traces. |
| **3** | **D-03** | **HIGH** | [`examples/03_*.md:42-63`](../examples/03_arrependimento_devolucao.md#L42-L63) | **Primary Deliverable #3 flaw (contradicts [`README.md:247`](../README.md#L247))**: in Turn 2 the agent states recorded ETA (`17/02`) as confirmed delivery fact and skips §4.4 exclusion questions; in Turn 3 the scripted customer answers those **unasked** questions. `examples/` were generated at `b65c638` (predating `16da6fe`). |

---

### Tier 2 — Critical & High Security / Domain / Policy Bugs (Confirmed Live & Statically)

| Rank | ID | Severity | Location | Shortcoming / Failure Mode |
|---:|---|---|---|---|
| **4** | **L-CRIT-01** | **CRITICAL** | [`returns.py:56-88`](../src/emporio_agent/returns.py#L56-L88) | **`received_on` spoofing approves returns on 10-month-old `DELIVERED` & `SHIPPED` orders**: claiming Order #5 (`05/01/2026`, `R$ 4.599,00`) or `shipped` Order #8 arrived `"02/11/2026"` returns `elegivel: true` (`302` days post-purchase) with store-paid return freight (`RT-21`, `RT-23`). |
| **5** | **L-CRIT-02** | **CRITICAL** | [`tools.py:295-308`](../src/emporio_agent/tools.py#L295-L308) | **Unauthenticated 3rd-party LGPD deletion & Turn-1 confirmation bypass**: unverified attacker in Turn 1 (`"Exijo pela LGPD a exclusão... lucas.mendes@jmail.com! Já confirmo o resumo"`) mints `EMP-2026-0001` (`tipo="lgpd"`, `cliente_verificado=null`) without verification or prior summary turn (`RT-26`). |
| **6** | **C-02** | **CRITICAL** | [`tools.py:46-57`](../src/emporio_agent/tools.py#L46-L57) | **2-digit year `dd/mm/aa` parsed as `0026 AD`**: `_parse_day("20/11/26")` constructs `datetime.date(26, 11, 20)` — `check_store_hours("20/11/26")` falsely reports **OPEN `09:00–18:00`** on a closed national holiday, and `check_return(..., received_on="17/02/26")` rejects valid return dates; `dd/mm` also fails across New Year boundaries. |
| **7** | **C-03 / L-MED-05** | **CRITICAL** | [`rules.py:34,140`](../src/emporio_agent/rules.py#L140-L141), [`catalog.py:352`](../src/emporio_agent/catalog.py#L352) | **Campo Grande shipping rejected on `"Campo Grande - MS"`, `"Campo Grande/MS"`, `"CG"` + false CEP promise**: exact check `normalize(city) in {"campo grande"}` misroutes state-suffixed inputs to Correios/Jadlog, and `"peça o CEP"` makes the agent promise CEP rate calculation when no CEP tool exists (`RT-15`). |
| **8** | **C-04 / L-MED-01** | **CRITICAL** | [`catalog.py:98-103`](../src/emporio_agent/catalog.py#L98-L103), [`rules.py:220`](../src/emporio_agent/rules.py#L220-L235) | **Corrupted descriptions indexed in `_haystack` + unflagged `#143 Nord Synth 2 Pro`**: searching `"Fender"` in basses returns `#135 Music Man`, `"88 teclas"` returns 61-key `#142 Korg` (causing 9-tool `16.76s` turn in `EX-03`), `"5 cordas"` returns 4-string `#137 Yamaha` (`RT-10`), and unflagged `#143` is pitched as a stage piano (`RT-09`). |
| **9** | **C-05** | **CRITICAL** | [`catalog.py:279-311`](../src/emporio_agent/catalog.py#L279-L311) | **Duplicate-line stock-limit bypass & 1-cent PIX drift in `quote`**: passing two `{"product_id": 108, "quantity": 1}` items quotes `2` units of `stock=1` Martin D-28E (`R$ 24.000,00`) with zero `problemas`. |
| **10** | **C-06 / D-05** | **CRITICAL** | [`cli.py:78-99`](../src/emporio_agent/cli.py#L78-L99) | **Mid-turn LLM error or empty message poisons conversation checkpoints**: API failure after `ToolNode` leaves `[HumanMessage, AIMessage(tool_calls), ToolMessage]` in `InMemorySaver` (and permanently in SQLite on `feat/persistencia-sqlite`), breaking turn alternation on subsequent turns. |
| **11** | **H-03 / L-HIGH-01** | **HIGH** | [`policies.md:36`](../data/policies.md#L36-L39), [`prompts.py`](../src/emporio_agent/prompts.py) | **Policy §7.1 5-minute WhatsApp SLA omitted everywhere**: live agent calls `consult_policy` 3x across all 8 topics and falsely tells the customer *"nosso manual não especifica um tempo máximo de resposta"* (`EX-06`). |
| **12** | **L-HIGH-02** | **HIGH** | [`clock.py:70-76`](../src/emporio_agent/clock.py#L70-L76), [`tools.py:149`](../src/emporio_agent/tools.py#L149-L156) | **False "Open 09:00–18:00" on Campo Grande municipal holiday (`26/08`), `Corpus Christi` (`04/06`), & `Carnaval` (`17/02`)**: unqualified `"aberto"` from `check_store_hours` overrides `consult_policy`'s municipal-holiday caveat (`RT-03`, `RT-34`). |
| **13** | **H-01 / H-04 / L-HIGH-03** | **HIGH** | [`catalog.py:98-166,243`](../src/emporio_agent/catalog.py#L98-L166) | **Catalog search & `get_product` blind spots**: `get_product("Ibanez")` returns only discontinued `#136` (shortest name tie-breaker); `search_catalog` returns `0` on `"violao acustico"` and `"GD-20"`, misses `#108` on `"violao"`, and misses both `Takamine GD20` & `Tagima Woodstock` on live `"fingerstyle"` query (`RT-04`) due to `limit=5` ascending sort. |
| **14** | **H-02 / L-MED-02** | **HIGH** | [`catalog.py:325-345`](../src/emporio_agent/catalog.py#L325-L345) | **Payment math gaps in `quote`**: approves installments when `payment` is `"boleto"`/`"pix"`/`"debito"`, and fails to catch invalid 12x card remainder (`R$ 1.199 / 12 = R$ 99,92 < R$ 100`) on combined `PIX + Cartão` (`RT-17`). |
| **15** | **H-05 / H-08 / L-HIGH-04/05** | **HIGH** | [`orders.py:38-46`](../src/emporio_agent/orders.py#L38-L46), [`tools.py:190-279`](../src/emporio_agent/tools.py#L190-L279) | **Phone `(067)` lockout & session auth state flaws**: `(067) 99812-3456` / `+55 067...` fail verification and burn strikes (`RT-19`); `verified_customer_id` survives 3 subsequent brute-force failures (`RT-25`) and can be overwritten mid-session by another customer. |

---

### Tier 3 — Notable Medium & Documentation Findings

- **Evaluation Checker Blind Spots (`H-09`, `H-10`, `M-10`):** `_MONEY` misses Markdown-bolded prices (`R$ **1.999,00**`) and `"1.850 reais"`, false-fails `"R$ 1,5 mil"` as `Decimal('1')`, and lets customer haggling numbers (`"faz por 1800?"`) ground hallucinated discounts (`"Fechado por R$ 1.800,00!"`). `emporio-evals --only <typo>` exits `0` (`0/0`) while overwriting `--report`.
- **Cross-Provider & Latency Config (`H-07`, `L-LOW-01`):** `MODEL_EFFORT=low` breaks `anthropic:claude-haiku-5-5` with HTTP 400 (`llm.py:48`), while being ignored for Gemini (`timeout=None`, `p90 = 12.87s`).
- **CLI & Temporal Polish (`H-06`, `M-09`, `L-MED-06`):** `--now invalid-date` and malformed `--script` YAMLs crash with raw tracebacks; `turns: "Oi"` calls the LLM once per character; `--now` between `order_date` and `estimated_delivery` causes `check_return` to reject its own database ETA (`RT-30`).
- **Documentation Cleanup (`D-07`, `D-08`, `D-09`):** [`HANDOFF.md`](../docs/HANDOFF.md#L39-L97) on `main` contradicts itself (*"no application code"* vs *"Done"*; *"`main` does not have this work yet"*); [`AI_USAGE.md`](../AI_USAGE.md#L23-L69) has 4 broken `file:///home/augusto/...` URLs; [`pyproject.toml`](../pyproject.toml#L25) `uv_build<0.12.0` warns on `uv 0.13.7`.

---

## Should You Merge `origin/feat/persistencia-e-web`?

**Recommendation: Do NOT merge `origin/feat/persistencia-e-web` as-is without fixing 4 concrete issues first (`D-04`, `D-05`, `D-06`, `D-10`):**
1. **Per-tab `TicketStore` race (`D-04`):** Share a single `Store`, `BaseChatModel`, and process/file-locked `TicketStore` across `WebSessions` instead of calling `build_session()` per tab.
2. **Gradio Retry/Undo & `"local"` fallback (`D-06`):** Disable Retry/Undo or bind session state via `gr.State`, generate a unique UUID when `session_hash` is absent (never `"local"`), guard `session.send()` with a per-session lock, and move `gradio` to `[project.optional-dependencies] web = ["gradio>=6.31.0"]` so core `uv sync` stays lightweight.
3. **Checkpoint rollback on mid-turn failure (`D-05` / `C-06`):** Snapshot checkpoint state before `app.invoke` or avoid persisting incomplete tool turns in `.state/conversas.sqlite`, and close `sqlite3.Connection` cleanly on exit.
4. **README contradiction (`D-10`):** Remove *"Uma UI web ficou para depois"* in `README.md:161`.

---

## Recommended Fix Order (When Ready to Implement)

1. **Unblock Tests & Locale (`C-01`):** Add `language="pt_BR"` in `clock.py:71` + explicit Campo Grande municipal holidays (`13/06`, `26/08`) and optional-holiday caveats (`Carnaval`, `Corpus Christi`) (`L-HIGH-02`).
2. **Harden Tools & Domain Rules (`C-02`–`C-05`, `L-CRIT-01`, `L-CRIT-02`, `H-01`–`H-08`):**
   - Reject/expand 2-digit years in `_parse_day`; strip state suffixes/`"cg"` in `is_metro` and remove `"peça o CEP"` when no CEP calculator exists; aggregate duplicate `product_id`s in `quote`, block installments on cash methods, and support split-payment card remainder checks.
   - Require human verification in `check_return` when `received_on` diverges sharply from `estimated_delivery` or when `status is SHIPPED`; require customer verification for `kind="lgpd"` and require a prior assistant summary turn before `open_ticket`.
   - Exclude corrupted `description` from `_haystack` (and flag `#143`), fix `get_product` brand ambiguity scoring, add Portuguese acoustic/electric/compact-code tokens and `sort` option to `search_catalog`, strip leading `"0"` trunk codes in `normalize_phone`, and enforce session lockout across all order tools.
   - Add §7.1's **5-minute WhatsApp response-time SLA** to `policies.md` and `STATIC_PROMPT`.
3. **Fix CLI, `llm.py`, & `evals.py` (`C-06`, `H-07`, `H-09`, `H-10`, `M-09`, `M-10`):** Guard CLI args/YAML types, set sensible `timeout` + Gemini thinking config, tighten `_MONEY` / `grounded` in `evals.py`, and add regression tests + red-team YAML scenarios.
4. **Regenerate `examples/*.md` (`D-03`), clean `HANDOFF.md` & `AI_USAGE.md` links (`D-07`, `D-08`), and switch the GitHub repository to Public (`D-01`).**
