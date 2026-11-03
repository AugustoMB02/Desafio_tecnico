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
