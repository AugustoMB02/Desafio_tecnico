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
