# How AI coding assistants were used

The brief asks candidates to explain which AI coding assistants they used and how (*"Uso de assistentes de código: caso faça uso de algum recurso de IA, explique qual a escolhida e como utilizou. Queremos entender o seu workflow"*). The README section *Uso de assistentes de código* (pt-BR) is the short version; this file is the detailed, chronological record.

---

## 1. Summary

- **Tools:** **Antigravity** (Google DeepMind agentic coding environment) for planning and for an independent QA audit; **Claude Code** for an adversarial review of the plan, the implementation and the fixes. [`CLAUDE.md`](CLAUDE.md), generated with Claude Code's `/init`, gave both assistants the same context: the brief's hard constraints (Python, pt-BR answers, incremental Git history), the data schema and the known data quirks.
- **Workflow:** research and specification first → Socratic design review (`/grill-me`) → adversarial verification of the plan → incremental implementation with tests and live scenarios → read-only multi-agent QA before patching → fixes with regression tests.
- **Why two assistants:** instead of treating one assistant as an autonomous code generator, which tends to bake its own assumptions into both the code and the tests, I pitted two different assistants against each other: each one audited the other's work. Scope, architecture, security and merge decisions stayed with me.

| Phase | Tool | What it produced |
|---|---|---|
| 1. Planning | Antigravity | EDA ([`scripts/explore_data.py`](scripts/explore_data.py)), literature review and plan ([`docs/PLAN.md`](docs/PLAN.md)) |
| 2. Adversarial plan review and handoff | Claude Code (CLI, local) | [`docs/Plan_Review.md`](docs/Plan_Review.md), [`scripts/review_checks/`](scripts/review_checks), [`docs/HANDOFF.md`](docs/HANDOFF.md) |
| 3. Implementation and live testing | Claude Code (cloud session) | [`src/`](src), [`tests/`](tests), [`evals/`](evals), [`examples/`](examples), README |
| 4. Independent QA and red-teaming | Antigravity (3 subagents) | [`reports/00`](reports/00_executive_qa_summary.md)–[`03`](reports/03_deliverables_and_branches_audit.md) |
| 5. Fixing the audit findings | Claude Code (cloud session) | [`tests/test_qa_fixes.py`](tests/test_qa_fixes.py), [`reports/04_resposta_ao_qa.md`](reports/04_resposta_ao_qa.md) |

---

## 2. Phase 1 — Planning with Antigravity

### Forensic EDA and policy cross-audit
- **My direction:** no application code yet; first a rigorous data exploration of the 6 CSVs and `políticas_da_loja.pdf`, recording and justifying how the data should be organized and cleaned.
- **What the assistant did:** wrote and ran [`scripts/explore_data.py`](scripts/explore_data.py) to cross-check every row, foreign key, JSON schema, price calculation and policy rule.
- **Traps it uncovered:**
  1. **Expired promotion on a suggested prompt:** the Takamine GD20 (`product_id=95`, R\$ 2.199,00) has a 12% promotion with `is_active=0`; a join without `is_active=1` would violate Policy §7.3.
  2. **Availability traps in "violões até R\$ 1.000":** ID 96 is `active` with `stock_quantity=0`; ID 113 is `discontinued`; ID 136 is `discontinued` despite 13 units; ID 101 (R\$ 1.049,00) drops to R\$ 996,55 with the 5% PIX discount.
  3. **Synthetic catalog contradictions** in categories 2–4: brand, wood and string/key counts conflict across `name`, `description` and `specs`.
  4. **Empty store categories (6, 7, 8):** woodwinds, brass and orchestral strings exist in the taxonomy and the manual but have no products — different from out-of-scope accessories.
  5. **Shared e-mail:** `bruno.martins@jmail.com` belongs to two customers (11, with an R\$ 8.732 order, and 43, with none).
  6. **Inconsistencies inside the PDF:** two spellings of the e-mail, two phone numbers, §3's flat "parcela mínima R\$ 100" vs §3.1's tiers, and §4.2 (30-day exchange) vs §8.1 (90-day legal warranty).

### Literature review and evaluation design
- **My direction:** a review of the state of the art (2023–2026) to justify the framework, data organization, retrieval strategy and the evaluation approach.
- **What the assistant did:** synthesized the sources in [`docs/PLAN.md`](docs/PLAN.md): τ-bench and ReAct (why arithmetic, discounts and auth gates belong in deterministic tools), BIRD and the OWASP LLM Top 10 (typed domain tools instead of text-to-SQL, with server-side authorization state), Cache-Augmented Generation (keep the short manual's sections intact) and the LLM-as-a-judge literature (code graders first).

### Design interrogation (`/grill-me`) and my decisions
I walked the design tree one decision at a time and overrode several of the assistant's first suggestions. Some of these planning decisions changed later, after the adversarial review (Phase 2) or because of the deadline; the last column says what was finally built.

| Topic | Assistant's first suggestion | My decision in the plan | What was finally built |
|---|---|---|---|
| Agent framework | PydanticAI, with LangGraph as alternative | **LangGraph** (`StateGraph`) for explicit state and checkpointing | LangGraph, kept |
| LLM provider and privacy | Public cloud APIs (Gemini / OpenAI) | **Local or AWS** for data safety: Ollama on my RTX 4070 (8 GB) + AWS Bedrock | Provider set by one variable (`MODEL=provider:model`). Live runs used Gemini 3.5 Flash because it was the key I had at hand before the deadline; **in production I would use AWS Bedrock or a local model** (README, *O que mudaria em produção*) |
| User interface | CLI + generic Chainlit/Streamlit | A customer-first web chat (FastAPI) with an evaluator drawer, plus the CLI | CLI with `--trace` and Markdown export (the brief accepts a CLI); a Gradio web chat exists on an optional, unmerged branch |
| Customer authentication | Conversational 2-of-3 only | Simulated OTP login + 2-of-3 as fallback | 2-of-3 only, with an attempt cap: a code shown on screen protects nothing |
| Reference clock | A fixed date (2026-03-23) | **Real clock** in `America/Campo_Grande` with an explicit override | Real clock + `--now`, which also hides records dated after it |
| Git workflow | Wait for manual review before committing | Commit and push continuously | Continuous small commits, on a dedicated branch merged into `main` through pull requests |

Two choices that came from the literature review were also revised after Phase 2: SQLite FTS5/BM25 for the policies (it returned nothing for the brief's own question) became a topic lookup over a curated `data/policies.md`, and an LLM judge at `temperature=0` (rejected by current models) became scripted scenarios graded by code. The README table *O que mudou do plano para a implementação* has the reasons.

---

## 3. Phase 2 — Adversarial plan review and handoff (Claude Code, CLI)

**Tool:** Claude Code running locally in this repository, with the reasoning effort raised to the maximum (`/effort max`) for most of the session. **Starting point:** the brief, the CSVs, the policy PDF, `PLAN.md` and `scripts/explore_data.py`.

| # | My request | What Claude Code did | Output |
|---|---|---|---|
| 1 | `/init`: analyze the repo and write a `CLAUDE.md` | Read the brief and the policy PDF and sampled the CSVs; wrote guidance on the task, the deliverables, the schema and the quirks (filenames with spaces, PII in `customers`, the inconsistent e-mail) | [`CLAUDE.md`](CLAUDE.md) |
| 2 | "Grill" the plan and write what it would do differently, plus mistakes and risks | Treated the plan as claims to verify with code, not text to comment on | [`docs/Plan_Review.md`](docs/Plan_Review.md) |
| 3 | Prepare a handoff so a fresh cloud session could continue on its own | Audited local-only dependencies, made the repo self-sufficient, wrote the handoff, pushed to a dedicated branch and verified it from a fresh clone | [`docs/HANDOFF.md`](docs/HANDOFF.md) |

**How the review was done.** The useful part was the assistant **checking the plan's claims with code**:
- it recomputed the EDA (all numbers matched) and probed edge cases I hadn't tested: `float` vs `Decimal` rounding (8 PIX prices differ by one centavo), how many SKUs the §3 vs §3.1 installment ambiguity changes (15 of 61), the shipping-threshold basis, delivery times vs §5.1, and which orders become "future" under my proposed reference dates (8 at 2026-02-22);
- it **built the retrieval I had planned** (SQLite FTS5 + BM25) and ran the brief's own question against it: **no results**, because the manual says "devolução/arrependimento" and FTS5 has no Portuguese stemming — one experiment disproved a design choice;
- it checked the model choices against current documentation (the IDs in my plan were retired; `temperature=0` and forced tool choice are rejected) and spot-checked my citations on the web (one had the wrong year and topic, others were used for claims the sources don't make);
- it found data issues my EDA missed: a seventh inconsistent SKU (136) and a substitute that swapped nylon for steel strings.

The handoff wrote **explicit, reversible defaults** wherever the plan and the review disagreed, flagged as not yet approved by me, instead of choosing silently. My constraints for that session: never commit secrets, use a dedicated branch, no feature work during the handoff, verify the push.

---

## 4. Phase 3 — Implementation and live testing (Claude Code, cloud session)

**Tool:** Claude Code in a cloud session, on branch `claude/emporio-agent-handoff-5gfkz8`, following the handoff.

| # | My request | What Claude Code did |
|---|---|---|
| 1 | Set up the environment, then "stop after you set up everything" | Moved the inputs to `data/`, created the uv project (Python 3.12, ruff, pytest) and stopped |
| 2 | Continue with the next steps, committing and pushing regularly | Implemented the domain rules, curated policies, clock, LangGraph agent, verification/orders, returns/tickets, scenario runner and README, each with tests; ran a spike on the installed LangGraph before relying on `Command`/`InjectedState` |
| 3 | Use the container's credentials for tests | Checked them first: the AWS keys were proxy placeholders and there was no Anthropic key, so it did not use them |
| 4 | Use my Gemini key; "use your best judgement" | Kept the key only in the gitignored `.env`, checked every commit for it, picked a dated stable model (`gemini-3.5-flash`), generated the examples, read them, fixed what they exposed and regenerated |
| 5 | While I commuted: re-check the brief, propose improvements and try them, on new branches if needed | Found the repo private and `main` without the work, aligned the README's AI-usage section with my own notes, fixed the eval harness, and built two optional features (persistent sessions, a Gradio web chat) on separate branches |
| 6 | Run more and harder examples, including several questions in one message | Wrote 24 hard scenarios, read every transcript, fixed three agent problems and some checker issues |

**How the work was checked:** unit tests pinned to hand-checked values, running the real graph with a scripted fake model (no API calls); a LangGraph spike, which confirmed that parallel tool calls see the state from before the step (so verification returns the orders itself); and live runs on Gemini 3.5 Flash graded by code — tools called, forbidden content, every R\$ amount traceable to a tool output. **Every transcript was also read**, which caught what the checks did not: invented product details, an unsupported claim about a brand's warranty, a complaint left out of a ticket, and the model adding product + shipping itself.

**How I steered it:** stage gates (stop after setup, then continue), bigger features on separate branches, harder tests with several questions per message. The review's recommendations went in through the handoff's defaults, which I let stand. Making the repository public, merging into `main` and choosing which optional branches to merge stayed with me.

---

## 5. Phase 4 — Independent QA and red-teaming (Antigravity)

**Why switch assistants again:** Claude Code had written both the implementation and its evaluation scenarios, which risks blind spots — tests shaped around the author's own assumptions and its container environment. After merging into `main`, I brought the repository back to Antigravity for an independent audit, with an explicit instruction: **test everything, use multiple agents, don't fix anything yet, and write the findings down first.**

Three subagents worked in parallel on a read-only tree, with runtime ticket files isolated outside the repository and the API key redacted from every file and log:

1. **Static code, domain logic and security** ([`reports/01`](reports/01_static_code_and_architecture_audit.md)): all Python modules, tests, `policies.md` vs the PDF and the eval runner. It caught a locale dependency invisible in the cloud container (`holidays` returned English names on `en_US` machines, failing 4 tests), 2-digit years read as year 26, "Campo Grande - MS" not recognized, a stock bypass through duplicate quote lines, installments on cash payments, corrupted descriptions being searchable, and blind spots in the eval checker.
2. **Live red-teaming on Gemini 3.5 Flash** ([`reports/02`](reports/02_live_chatbot_redteam_report.md)): 89 live turns (42 adversarial conversations, 12 `pass^3` consistency runs, 6 CLI probes). It confirmed `pass^3 = 100%` on the scenarios already covered, and found real exploits: a typed receipt date reopened the return window of 10-month-old orders, an unverified caller opened an LGPD deletion ticket for someone else, the §7.1 WhatsApp response time was missing, and the store was reported plainly open on a municipal holiday.
3. **Deliverables and branches** ([`reports/03`](reports/03_deliverables_and_branches_audit.md)): no secrets in the history; the repository was still private; an example answered a question the agent never asked; and issues in the optional branches. Summary in [`reports/00`](reports/00_executive_qa_summary.md).

---

## 6. Phase 5 — Fixing the audit findings (Claude Code, cloud session)

| # | My request | What Claude Code did |
|---|---|---|
| 1 | Address the QA reports | Reproduced each reported failing input before changing any code (all the top findings reproduced), fixed the confirmed ones with regression tests ([`tests/test_qa_fixes.py`](tests/test_qa_fixes.py)), turned six red-team conversations into live scenarios, regenerated the five examples, and answered every finding with its status in [`reports/04_resposta_ao_qa.md`](reports/04_resposta_ao_qa.md) |
| 2 | Clean up before delivery | Merged the two AI-usage logs into this file, moved the process documents to [`docs/`](docs), resolved conflicting statements across the documents, added the production section to the README, and merged into `main` |

**Result on the final code:** 221 unit tests (also with `LANG=en_US.UTF-8`), 24/24 regression scenarios and 30/30 hard scenarios (including the six red-team cases), and the five examples regenerated with every R\$ amount traceable to a tool output. What was not fixed — and why — is listed in `reports/04`.

---

## 7. Who did what

- **Me (Augusto):** the phased method (data and literature before code; two assistants reviewing each other; read-only QA reports before any patch); the architecture decisions (LangGraph, privacy posture, authentication constraints, real clock, read-only data with tickets); the stage gates (*"stop after setup"*, *"don't fix anything yet — write reports first"*); which review points and fixes to accept; when to merge.
- **Antigravity:** the EDA script, the literature review and the `/grill-me` walkthrough behind `docs/PLAN.md` (Phase 1); the three-track QA and red-team audit in `reports/` (Phase 4).
- **Claude Code:** the adversarial plan review with reproducible scripts and the handoff (Phase 2); the implementation, tests, scenarios and examples (Phase 3); the fixes and the response to the audit (Phase 5).

## 8. Takeaways and limits

- **The most valuable use of AI was adversarial verification:** asking one assistant to prove or disprove the other's work with code. It disproved a planned design (FTS5), found a data trap the EDA missed, and — in the audit — found defects that the implementation's own tests and scenarios had missed.
- **Every number in the documents is backed by a script or a test** (`scripts/review_checks/`, `tests/`).
- **Live checks used one model** (Gemini 3.5 Flash) with a few runs per scenario: a sample, not a guarantee. Nothing was run against Claude; the Anthropic-specific findings were checked statically.
