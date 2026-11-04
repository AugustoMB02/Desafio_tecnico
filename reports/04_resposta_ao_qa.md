# Report 04 — Response to the QA audit (reports 00–03)

The audit (Antigravity with Gemini, read-only, on `main` at `9d5b635`) was checked finding by finding: each reported failing input was reproduced against the code before anything was changed. Every fix below has a regression test in [`tests/test_qa_fixes.py`](../tests/test_qa_fixes.py), and six of the red-team conversations are now live scenarios in [`evals/scenarios_dificeis.yaml`](../evals/scenarios_dificeis.yaml) (ids starting with `qa_`).

**Status legend:** ✅ fixed · 🟡 partly addressed · ⏸ not fixed (reason given)

## Deliverables

| ID | Finding | Status |
|---|---|---|
| D-01 | Repository is private (anonymous 404) | ⏸ Only the owner can change the visibility (GitHub → Settings → Danger Zone). Still required before submitting. |
| D-02 / C-01 | `uv run pytest` fails 4 tests on `LANG=en_US.UTF-8` | ✅ Holiday names are loaded with `language="pt_BR"`; the suite passes under `en_US`. |
| D-03 | `examples/03` states the forecast as the receipt date and the script answers unasked questions | ✅ Examples regenerated on the fixed code; §4.4 no longer applies to the regret right (see L-MED-03). |
| D-07 | `HANDOFF.md` contradicts itself | ✅ §2 marked as "at handoff time"; §4 rewritten with the current state. |
| D-08 | `AI_USAGE.md` has 4 `file:///home/augusto/...` links | ✅ Replaced by repository-relative links. |
| D-04, D-05, D-06, D-10 | Issues in the optional branches (`feat/*`) | ⏸ Those branches are not merged and predate these fixes; the audit's recommendation (don't merge as-is) stands. |
| D-09 | `uv_build` upper bound warns on newer uv; unused `.env.example` entries | ⏸ Cosmetic; the build works. |
| D-11 | No secrets in history | ✅ Confirmed by the audit and re-checked. |

## Security, money and policy

| ID | Finding | Status |
|---|---|---|
| L-CRIT-01 | A typed receipt date reopens returns on 10-month-old (and shipped) orders | ✅ A customer date more than 10 days after the recorded forecast goes to the team to confirm by tracking; no deadline is computed from it. |
| L-CRIT-02 | Unverified caller opens an LGPD deletion ticket for a third party | ✅ `open_ticket(kind="lgpd")` requires a verified customer. 🟡 The "confirm the summary first" rule is still enforced by the prompt, not by code. |
| C-05 / M-01 | Duplicate quote lines bypass stock; quantity 0 becomes 1 | ✅ Lines are merged per product before the stock check (and priced as one line); quantity 0 is invalid. |
| H-02 | Installments approved on PIX / debit / boleto | ✅ Cash payments return "não se aplica". |
| L-MED-02 | Split payment (PIX + card) remainder not checked | ⏸ The policy doesn't define how the split works; the quote already tells the agent that the team confirms combined payments. |
| H-03 / L-HIGH-01 | §7.1 5-minute WhatsApp response time missing | ✅ Added verbatim to `policies.md` (the PDF-fidelity test covers it). |
| L-HIGH-05 / H-08 | Verified session survives a lockout | ✅ Reaching the lockout ends any earlier verification. 🟡 Re-verifying as another customer in the same chat is still allowed. |
| H-05 / L-HIGH-04 | `(067)` / `+55 067` phones fail and burn attempts; order 0 counts as a factor | ✅ |
| L-MED-03 | §4.4 (items not eligible for **exchange**) applied to the online regret right | ✅ §4.4 now applies only to preference exchanges. |
| L-02 | Internal manual section numbers leak to customers | ✅ The prompt says not to cite them. |
| M-06 | Unverified tickets can mention any order in the summary | 🟡 Linking an order still requires verification; non-customers can still leave a contact (e.g. to register interest). |

## Dates, hours and shipping

| ID | Finding | Status |
|---|---|---|
| C-02 | `dd/mm/aa` parsed as year 26 AD; `dd/mm` wrong across New Year; `dd-mm-aaaa` rejected | ✅ |
| L-HIGH-02 / L-03 | Store reported plainly open on Carnaval, Corpus Christi and Campo Grande's municipal holiday | ✅ Those days (and 13/06, 24/12, 31/12) come with "o horário pode mudar; confirme com a loja". |
| H-06 | `--now` between order date and forecast makes `check_return` reject its own forecast | ⏸ Only reachable with a demo clock set inside an order's delivery window. |
| C-03 / L-MED-05 | "Campo Grande - MS", "Campo Grande/MS", "CG" treated as other cities; agent promised a CEP calculation no tool does | ✅ |
| M-02 | PIX can cost more than card after the free-shipping threshold | ⏸ `total_com_frete` already shows both totals, which let the agent advise correctly in the audit (EX-07). |

## Catalog search

| ID | Finding | Status |
|---|---|---|
| C-04 / L-MED-01 | Corrupted descriptions of the 7 flagged SKUs are searchable | ✅ Not indexed anymore. 🟡 SKU 143 (Nord) is not flagged: its brand is consistent and the description is the store's own. |
| H-01 | `get_product("Ibanez")` silently picks the shortest name (a discontinued bass) | ✅ A name contained in several products returns candidates. |
| H-04 | "violão", "acústico", "eletroacústico", "baixo elétrico", "GD-20" miss items | ✅ Category vocabulary, electronics words and hyphen/space-insensitive model codes. |
| L-MED-04 / M-03 | "Most expensive" needs six calls; results always cheapest-first | ✅ `search_catalog(sort="maior_preco")`. |
| L-HIGH-03 | "fingerstyle" request misses the GD20 | 🟡 Descriptions of consistent SKUs are searchable, but the model has to pass the word as `query`. |
| M-04 | Alternatives ignore ukulele size | ⏸ |

## CLI and evaluation harness

| ID | Finding | Status |
|---|---|---|
| C-06 / D-05 | A mid-turn API failure leaves a dangling tool call in the conversation | ✅ The next message forks from the last complete checkpoint (CLI). The optional SQLite branch is not updated. |
| M-09 / L-MED-06 | Bad `--now`, string or empty `turns`, malformed YAML crash with tracebacks | ✅ Clean errors (exit 2 / message). |
| M-10 | `emporio-evals --only <typo>` exits 0 with an empty report | ✅ Exits 2; report directory is created if missing. |
| H-09 / H-10 / M-12 | Numeric-faithfulness check misses bold prices and lets haggling numbers count as grounded; brittle word bans | ⏸ Known limits of the checker. Every transcript is also read, and the haggling scenario bans concrete "fechado por" phrasings. |
| H-07 | `MODEL_EFFORT` breaks Claude Haiku 5.5 | ⏸ Not verified (no Anthropic key was available to the audit or to us); the README marks the variable as optional. |
| M-05, M-07, M-08, M-11, L-01, L-04, L-05, L-06 | Ticket-file locking/permissions, invalid tool calls, history growth, runner init cost, minor policy edges, export formatting, dead code | ⏸ Prototype scope; listed for a next iteration. |
