# AI usage log

A running record of how AI coding assistants were used in this challenge. It's raw material for the README's *"Uso de assistentes de código"* section. Add one entry per working session.

---

## Session 1: repo guidance, plan review and cloud handoff (2026-11-03)

**Tool:** Claude Code (CLI), model Claude Opus 5.5, running locally in this repo. For most of the session I raised the reasoning effort to the maximum with `/effort max`.

**Starting point:** the repo held the brief, the CSVs and the policy PDF. I had written `PLAN.md` (architecture plan + EDA) and `scripts/explore_data.py` and committed them in `e563d6b`.

### What I asked for and what the assistant did

| # | My request | What Claude Code did | Output |
|---|---|---|---|
| 1 | `/init`: analyze the repo and write a `CLAUDE.md` | Read the brief and policy PDFs (`pdftotext`) and sampled the CSVs. Wrote guidance on the task, the deliverables, the data schema and quirks (filenames with spaces, PII in `customers`, the inconsistent e-mail in the policy) | `CLAUDE.md` (committed in `e563d6b`) |
| 2 | "Grill" `PLAN.md` and write a review of what it would do differently, plus any mistakes or risks | Treated the plan as claims to verify, not text to comment on. Details below | `Plan_Review.md` (branch `handoff/emporio-agent`) |
| 3 | Prepare a handoff so a fresh Claude Code cloud session could continue on its own | Audited local-only dependencies, made the repo self-sufficient, wrote `HANDOFF.md`, committed on a dedicated branch, pushed, and verified with a fresh clone | Branch `handoff/emporio-agent` |
| 4 | Write this log on `main` | — | `AI_USAGE_LOG.md` |

### How the plan review was done (request 2)

The useful part was the assistant **checking the plan's claims with code** instead of just reading it:

- **Recomputed the EDA.** Category stats, the 12 violões ≤ R$ 1.000, active promotions, the Takamine GD20 price, the order breakdown and the duplicate e-mail all matched my plan.
- **Probed edge cases I hadn't tested:**
  - float vs `Decimal` rounding (8 PIX prices differ by one centavo);
  - how many SKUs the §3 vs §3.1 installment ambiguity affects (15 of 61);
  - the shipping-threshold basis (the Ohana CK-20 flips between readings);
  - delivery times vs §5.1;
  - which orders become "future" under my proposed reference dates (8 at 2026-02-22).
- **Built the retrieval design I had planned** (SQLite FTS5 + BM25 over the policy sections) and ran the brief's own question against it. It returned **no results**, because the manual says "devolução/arrependimento" and FTS5 has no Portuguese stemming. That one experiment disproved a design choice.
- **Checked the model choices against current Claude docs.** The model IDs in my plan were retired; `temperature=0.0` and forced tool choice are rejected by current models.
- **Spot-checked my citations with web search.** One was the wrong year and attached to the wrong claim (CAREFUL); one had the wrong date. A few others were used for claims the sources don't make, including one source that argues against my retrieval choice.
- **Found data issues my EDA missed:** a seventh SKU with a brand contradiction (#136), and a substitute recommendation that swapped nylon for steel strings.

The review also proposes a narrower scope with a cut line, safer tool signatures (tools take product IDs, never model-typed prices), a revised commit order, 20 test scenarios and 13 extra assumptions. **I have not yet decided which recommendations to accept.** Record those decisions in a later entry; they are the most interesting part for the README.

### Handoff work (request 3)

- **Audit:** no uncommitted work except the review; no gitignored files or local databases; **no LLM credentials anywhere**; Ollama with `qwen3:8b` running locally (can't be used in the cloud); an absolute path to my machine in `explore_data.py`; the verification scripts living only in a temporary folder.
- **Fixes on branch `handoff/emporio-agent`** (3 commits, all `main`-safe):
  - fixed the EDA script path;
  - committed the verification scripts as `scripts/review_checks/`;
  - added `.gitignore`;
  - wrote `HANDOFF.md` (goal, state, decision defaults where the plan and the review disagree, ordered next steps, blockers, when to stop);
  - pointed `CLAUDE.md` to it.
- **Verified by:** comparing `git log origin/handoff/emporio-agent -1` with local, then cloning the branch from GitHub into an empty folder and running all scripts.

### How I steered it

- I gave explicit constraints in the prompts: never commit secrets, use a dedicated branch (not `main`), don't start feature work during the handoff, verify the push.
- The assistant asked no clarifying questions. Where my plan and its review conflicted, it wrote **explicit, reversible defaults** into `HANDOFF.md` and flagged that I hadn't approved them, rather than picking silently.

### Limits worth stating honestly

- The LangGraph/LangChain/Ollama gotchas in the review (parallel tool-call state, `Command` + `ToolMessage`, `SqliteSaver` being sync-only) come from the model's knowledge. They were **not** run against pinned library versions; the handoff schedules a spike to check them.
- The assistant didn't know the submission deadline, and it isn't recorded in the repo.

### Takeaways for the README

- The most valuable use was **adversarial verification**: asking the AI to prove or disprove my own plan with small scripts. Asking it to write more plan would have been less useful.
- **Every number in the AI-written docs is backed by a script I can re-run** (`scripts/review_checks/`).
- **Human decisions stay human.** Scope, which review points to accept and when to merge to `main` were left to me.

---

## Session 2: implementation, live testing and hardening (2026-11-03)

**Tool:** Claude Code in a cloud session (claude.ai/code), working on branch `claude/emporio-agent-handoff-5gfkz8` and following `HANDOFF.md`.

### What I asked for and what the assistant did

| # | My request | What Claude Code did | Output |
|---|---|---|---|
| 1 | Check out the handoff branch, read `HANDOFF.md`, set up the environment and continue; then "stop after you set up everything" | Moved the inputs to `data/` and created the uv project (Python 3.12, ruff, pytest); stopped after the skeleton | `52b0d87`, `3ac2464` |
| 2 | Continue with the next steps, committing and pushing regularly | Implemented the domain rules, curated policies, clock, LangGraph agent, verification/orders, returns/tickets, scenario runner and README, each with tests. Before relying on LangGraph's `Command`/`InjectedState`, ran a spike on the installed version | `fa7b523` … `263c78d` |
| 3 | Use the container's credentials for tests | Checked them first: the AWS keys were proxy placeholders (AWS rejected them) and there was no Anthropic key, so it did not use them | — |
| 4 | Use my Gemini key; the deadline is tonight; "use your best judgement" | Kept the key only in the gitignored `.env` and checked every commit for it. Probed which models answered and picked a dated stable one (`gemini-3.5-flash`). Generated the examples, read them, fixed what they exposed and regenerated | `2d65a27`, `examples/` |
| 5 | While I commuted: re-read the brief, check the requirements, propose improvements and try them, on new branches if needed | Audited the brief (the repo was private and `main` lacked the work), merged `main` into the branch, rewrote the README's AI-usage section to match `AI_USAGE.md` and this log, fixed the eval harness, and built two optional features on separate branches | `9466b7a`, `4d9aa78`, `c9f883e`; branches `feat/persistencia-sqlite`, `feat/web-ui-gradio`, `feat/persistencia-e-web` |
| 6 | Run more and harder examples, including several questions in one message | Wrote 24 hard scenarios, read every transcript, fixed three agent problems and some checker issues, and re-ran both scenario sets | `8a03afc`, `16da6fe`, `evals/report_dificeis.md` |
| 7 | Check the README against the AI-usage files on `main` | Completed the README section with all the steering decisions in `AI_USAGE.md` and wrote this entry | — |

### How the work was checked

- **Unit tests** pinned to hand-checked values (158 on the delivery branch), running the real graph with a scripted fake model, so no API calls.
- **A spike before relying on LangGraph behaviour.** It confirmed that parallel tool calls see the state from before the step, so customer verification returns the orders itself.
- **Live runs against Gemini 3.5 Flash:** the five examples plus 48 scripted scenarios, graded by code (tools called, forbidden content, every R$ amount traceable to a tool output). **Every transcript was also read**, which caught what the checks did not: invented product details, an unsupported claim about a brand's warranty, a complaint left out of a ticket, and the model adding product + shipping itself.

### How I steered it

- **Scope and pace:** stop after setup, then continue; bigger features on separate branches; harder tests with several questions per message.
- **Provider:** Gemini, because it was the key available before the deadline. The code stays provider-agnostic (`MODEL=provider:model`).
- **The review's recommendations** (left open in Session 1): they went in through the decision defaults in `HANDOFF.md`, which I let stand. The README table *O que mudou do plano para a implementação* lists each change and why.
- **What stays mine:** making the repository public, merging into `main` and choosing which optional branches to merge.

### Limits worth stating honestly

- One model and a few runs per scenario: a sample, not a guarantee. Nothing was run against Claude; only its request payload was validated offline.
- The five examples were generated at `b65c638`, before the last prompt changes. The scenario sets were re-run on the final code.

---

## Session 3: independent multi-agent QA, live red-teaming and deliverables audit (2026-11-03)

**Tool:** Antigravity (Google DeepMind agentic coding environment), coordinating three parallel subagents on `main` (`9d5b635`) after PR #1 was merged.

**Why switch assistants again:** Claude Code wrote both the implementation and the 48 evaluation scenarios in Session 2, which creates a blind-spot risk (tests shaped around the author's own assumptions and container environment). Before making final fixes, I brought the merged repo back to Antigravity for an independent adversarial audit.

### What I asked for and what the assistant did

| # | My request | What Antigravity did | Output |
|---|---|---|---|
| 1 | Test the merged system and live chatbot (`google_genai:gemini-3.5-flash`), find shortcomings and failure modes, use multiple agents if needed, **don't fix anything yet**, and write QA reports | Synced the local `uv` environment, ran `pytest` (immediately exposing 4 locale-dependent failures), read all 16 modules, defined a sandboxed `qa-runner` subagent, ran three parallel audit tracks, and wrote four structured QA reports without modifying any existing repo file | [`reports/00_executive_qa_summary.md`](reports/00_executive_qa_summary.md) … [`reports/03_deliverables_and_branches_audit.md`](reports/03_deliverables_and_branches_audit.md) (`5b56d1c`) |
| 2 | Log how I used Antigravity in this phase so code reviewers can see the full AI workflow | Added Session 3 to this log, updated `AI_USAGE.md` with Phase 4, and added step 5 to `README.md`'s *Uso de assistentes de código* section | `AI_USAGE_LOG.md`, `AI_USAGE.md`, `README.md` |

### How the audit was done (request 1)

Three subagents worked concurrently against a read-only working tree (with runtime ticket files isolated in temporary directories outside the repo):

- **Track 1 — Static Code, Domain Logic & Security Auditor:** Read all 16 Python modules, all 8 test files, `data/policies.md` vs. all 8 pages of `políticas_da_loja.pdf`, and `evals/*.yaml`, verifying edge cases against `.venv`:
  - **Locale bug invisible in the cloud container:** `holidays.Brazil(subdiv="MS", years=year)` in `clock.py` omits `language="pt_BR"`. In Session 2's `LANG=C.UTF-8` container it fell back to Portuguese; on a standard `LANG=en_US.UTF-8` Linux machine it returns English holiday names and fails 4/158 unit tests out of the box.
  - **Date, city, phone and stock edge cases:** `_parse_day("20/11/26")` parses as year `0026 AD` (reporting the store open on a national holiday); `is_metro` rejects `"Campo Grande - MS"`, `"Campo Grande/MS"` and `"CG"`; `normalize_phone` rejects `0`-prefixed DDDs (`(067)...`) and burns verification attempts; `quote` checks stock per line item instead of aggregating duplicate `product_id`s and approves installments on `boleto`/`pix`; `_haystack` still indexes corrupted `description` fields on inconsistent SKUs (`135–144`), and SKU `#143` has an unflagged synth/piano contradiction.
  - **Eval-checker blind spots:** `evals.py`'s `_MONEY` regex misses bolded amounts (`R$ **1.999,00**`) and `"reais"` without `R$`, false-fails `"R$ 1,5 mil"`, and lets bare numbers in customer haggling (`"faz por 1800?"`) ground hallucinated discounts.
- **Track 2 — Live Chatbot Red-Teamer (`gemini-3.5-flash`):** Executed **89 live LLM turns** (42 adversarial conversations, 12 `Pass^3` consistency runs on `scenarios_dificeis.yaml`, and 6 CLI subprocess edge probes):
  - Confirmed `pass^3 = 100%` (`12/12`) on scenarios already covered by `evals/`, proving the failures found were deterministic tool/policy gaps rather than random model flakiness.
  - Found live end-to-end exploits and policy gaps: `received_on` spoofing (`"02/11/2026"`) approved 7-day returns with store-paid shipping on 9–10 month old `DELIVERED` and `SHIPPED` orders; unverified Turn-1 callers minted `lgpd` data-deletion tickets for third-party customer emails by asserting *"já confirmo o resumo"*; asking for Policy §7.1's WhatsApp response-time SLA (5 minutes, omitted from both `policies.md` and `prompts.py`) made the agent claim no SLA exists; asking about `26/08` (Campo Grande's municipal holiday) or `Corpus Christi` got a confident `"aberto das 09:00 às 18:00"`; and `"fingerstyle"` missed both `Takamine GD20` and `Tagima Woodstock` due to ascending `limit=5` truncation.
- **Track 3 — Deliverables & Feature-Branches Auditor:** Checked GitHub public access (`HTTP 404` — repo still private), scanned full git history across all branches for leaked secrets/PII (none found), caught an unasked-question flaw in `examples/03_arrependimento_devolucao.md`, and audited `origin/feat/persistencia-e-web` (finding a per-tab `TicketStore` protocol race, Gradio Retry/Undo state desync, `"local"` session fallback, mid-turn SQLite checkpoint corruption, and heavy core `gradio` dependencies).

### How I steered it

- **Strict separation between diagnosis and mutation (*"don't fix anything yet"*):** Instead of letting the agent silently patch code while testing, I required written, evidence-backed QA reports first so I can decide which fixes to apply, whether to merge `feat/persistencia-e-web`, and in what order.
- **Cross-agent verification loop:** Antigravity wrote the plan $\rightarrow$ Claude Code adversarially reviewed the plan and implemented the system $\rightarrow$ Antigravity adversarially red-teamed the implementation across multiple agents.
- **Continuous remote visibility:** Kept the rule of committing and pushing reports directly to `origin/main` (while redacting the live `GOOGLE_API_KEY` from all files, logs, and commits).

### Limits worth stating honestly

- Live red-teaming ran against `google_genai:gemini-3.5-flash` only; Anthropic (`claude-haiku-5-5` / `claude-sonnet-5-5`) findings (`MODEL_EFFORT` compatibility and strict turn-alternation errors after mid-turn failures) were verified statically against the installed `langchain-anthropic` SDK rather than live Anthropic API calls.
- Because fixes were intentionally held back during this session, `main` at this point still reflects the pre-fix state documented in `reports/`.

---

## Session 4: fixing the audit findings (2026-11-03)

**Tool:** Claude Code, in the same cloud session as Session 2, on branch `claude/emporio-agent-handoff-5gfkz8`.

### What I asked for and what the assistant did

| # | My request | What Claude Code did | Output |
|---|---|---|---|
| 1 | Address the QA reports Antigravity wrote on `main` (Session 3) | Reproduced each reported failing input before changing any code (all the top findings reproduced), fixed the confirmed ones with regression tests, turned six red-team conversations into live scenarios, regenerated the five examples, and answered every finding with its status | `c231408`, `ada9f79`, `f1ebc16`, `tests/test_qa_fixes.py`, `reports/04_resposta_ao_qa.md` |
| 2 | "What is left to do before I deliver it?" | Checked the repo state (now public), merged this log's Session 3 and `AI_USAGE.md` Phase 4 from `main` into the branch, added item 6 to the README section and this entry, so the final merge into `main` is a fast-forward | this entry |

### How the work was checked

- 221 unit tests pass, also with `LANG=en_US.UTF-8`; ruff is clean.
- Final live runs on the fixed code: 24/24 regression scenarios and 30/30 hard scenarios (including the six red-team cases); the five examples regenerated on the fixed code, with every R$ amount traceable to a tool output.

### Limits worth stating honestly

- Not everything was fixed. The split-payment remainder check, some limits of the eval checker, a few safeguards that still rely on the prompt (confirming before opening a ticket, switching the verified customer mid-chat) and the issues in the optional `feat/*` branches remain, each with its reason in `reports/04_resposta_ao_qa.md`.

