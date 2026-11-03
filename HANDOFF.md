# HANDOFF: Empório da Música agent (Artefact AI Engineer take-home)

Written 2026-11-03 for a fresh Claude Code cloud session working on branch `handoff/emporio-agent`.

Read this file fully, then `PLAN.md` (the user's original plan) and `Plan_Review.md` (a verified review of that plan). The brief is `desafio_tecnico_ai_eng_artefact.pdf` and the store's policy manual is `políticas_da_loja.pdf`. The Read tool opens PDFs directly, or use `pdftotext -layout <file> -`.

---

## 1. Goal

Deliver phase 1 of the Artefact AI Engineer selection process: a **Python** text-message customer-service agent for **Empório da Música**, a fictional musical-instrument store in Campo Grande/MS. The agent must:
- speak pt-BR in the store's persona: informal but professional, *"um amigo que entende de música"*, slogan *"Sua música começa aqui."*;
- decide when to query operational data (prices, stock, promotions, order status) and when to consult policies (hours, payment, returns, shipping, warranty);
- handle out-of-scope requests. The store sells **only instruments**: no strings, picks, cables, cases, pedals or amplifiers.

Deliverables, from the brief:
1. **This public GitHub repo** with a real, incremental commit history: no squash, no force-push, and nothing changed after the deadline.
2. **`README.md`** covering setup and run instructions, the justification of each technical decision (framework, LLM, retrieval, prompt strategy), known limitations and next steps, and how AI coding assistants were used.
3. **3–5 example conversations** (`.md`, `.txt` or image), at least one non-trivial (a live data lookup or a policy rule being applied).

The brief values logic, clarity and initiative over perfection. It says the interface can be a plain CLI: *"o foco é o agente funcionando corretamente"*.

**The submission deadline is not known to this session.** It is in the user's e-mail; see §8 and §9.

---

## 2. Done so far

| Path | What it is |
|---|---|
| `CLAUDE.md` | Repo guidance (task, deliverables, data quirks). Auto-loaded by Claude Code. |
| `PLAN.md` | The user's original plan: EDA findings, architecture, tool list, eval strategy, commit plan (commit `e563d6b`). |
| `Plan_Review.md` | Adversarial review of `PLAN.md`. It confirms the EDA, finds bugs and gaps, and proposes a narrower scope, safer tool signatures, a revised commit sequence, 20 test scenarios and 13 extra README assumptions. **The user has not yet accepted or rejected its recommendations**; §3.2 says what to do about that. |
| `scripts/explore_data.py` | The user's EDA script. Its hardcoded absolute path was fixed on this branch. |
| `scripts/review_checks/check_numbers.py` | Recomputes every number cited in `Plan_Review.md`. |
| `scripts/review_checks/fts5_policy_probe.py` | Reproduces the FTS5/BM25 failure from `Plan_Review.md` §3.2. |
| `.gitignore` | Keeps `.env`, virtualenvs, caches and `.state/` (runtime state, may contain customer PII) out of git. |

Nothing else exists yet: no application code, no `pyproject.toml`, no tests, no `examples/`, and `README.md` is a one-line stub.

---

## 3. Decisions

### 3.1 Facts established (not up for debate)

- The EDA numbers in `PLAN.md` are correct (`Plan_Review.md` §2).
- The Claude model IDs in `PLAN.md` are **retired**: Claude Haiku 3.5 (2026-02-19) and Claude Sonnet 4 (2026-06-15). The current generation is `claude-haiku-5-5`, `claude-sonnet-5-5` and `claude-opus-5-5`.
- Current Claude models **reject `temperature`** (non-default values return a 400 on Sonnet 5.5 and Haiku 5.5; Opus 5.5 removed it), and they **reject forced `tool_choice`** (`any`/`tool` returns a 400 on Sonnet 5.5 and Opus 5.5). Send neither.
- SQLite FTS5/BM25 over the policy sections returns **no results** for the brief's own question ("Me arrependi da minha compra, posso devolver meu pedido?") and for "devolver pedido". The manual only uses "devolução" and "arrependimento", and FTS5 has no Portuguese stemming.
- `float` rounding and `Decimal` ROUND_HALF_UP disagree by one centavo on 8 PIX prices (e.g. Yamaha C40: 569,90 vs 569,91).
- The §3.1 installment tiers and the §3 flat R$ 100 minimum give different answers for **15 of the 61 sellable SKUs** (all under R$ 600).
- **7 SKUs** (135, 136, 137, 139, 140, 142, 144) have descriptions naming a different brand or model than the product name. `PLAN.md` lists six; it misses 136.
- Today (November 2026) is 7–13 months after every order. Setting the date back to 2026-02-22, as `PLAN.md` suggests, puts orders 10–16 and 20 in the future.

Re-check any of these with `python3 scripts/review_checks/check_numbers.py` and `python3 scripts/review_checks/fts5_policy_probe.py`.

### 3.2 Decision defaults where `PLAN.md` and `Plan_Review.md` disagree

The user hasn't chosen between the plan and the review. Implement these defaults: each is either forced by a fact in §3.1 or cheap to reverse. **If the user's prompt to you says otherwise, the user wins.**

| Topic | `PLAN.md` said | Default to implement | Why |
|---|---|---|---|
| Agent framework | LangGraph `StateGraph` + `ToolNode` + `InjectedState` + `Command` | **Keep LangGraph.** Pin versions, and spike the gotchas in `Plan_Review.md` §3.6 before relying on them | User's choice, and sound |
| LLM access | Bedrock primary, Ollama local, OpenAI/Gemini fallbacks; retired IDs | Provider-agnostic through LangChain `init_chat_model`, configured by a `MODEL` env var (`provider:model`). **No default model in code**: fail with a clear message if unset. Current IDs only; no `temperature` | Retired IDs are a fact; this avoids choosing the provider for the user |
| Policy access | FTS5 BM25 + topic lookup | Hand-curated `data/policies.md` + `consult_policy(topics: list[enum])` returning whole sections. The §7 and §10 rules go in the system prompt | The FTS5 failure is reproducible; an enum keeps "consulting policies" visible in traces |
| Data layer | SQLite `emporio.db` built by `build_data.py`, views, FTS5 | Typed in-memory objects loaded from the CSVs at startup, queried by pure functions. (SQLite with per-call read-only connections is the reversible alternative.) | No build step. `ToolNode` runs parallel sync tool calls in a thread pool, where one shared `sqlite3` connection would trip `check_same_thread` |
| Data location | `git mv` to `data/raw/` | `git mv` to `data/` (the brief's layout), keeping the original filenames | Matches the brief; there's no processed layer to separate |
| Money | "exact Python math" | `Decimal`, ROUND_HALF_UP per line, one `fmt_brl()` helper (no `locale`) | Fact in §3.1 |
| Installments | §3.1 tiers | §3.1 tiers, recorded as an assumption | Same as the plan |
| Shipping threshold | free at ≥ R$ 500 | Free when the **amount paid** (after promotion and PIX) is ≥ R$ 500,00, otherwise R$ 35, inside the Campo Grande metro region. Other cities: "calculado pelo CEP", never a number | Ohana CK-20 flips between the two readings; keeps the plan's ≥ |
| Authentication | Simulated OTP in a web UI + conversational 2-of-3 | Conversational 2-of-3 only: whole-tuple match, 3-attempt cap, generic failure messages, verified customer kept in state, orders returned on success | An OTP shown on screen adds no security; returning orders fixes the parallel-call race |
| Clock | Real clock + `REFERENCE_DATE` + a UI picker | One injectable `now()` in `America/Campo_Grande`, real time by default. A `NOW` override for scripted runs hides records dated after it. Holidays from `holidays` (Brazil, subdivision MS) | Fixes the future-dated-orders bug |
| Interface | FastAPI bespoke web chat + Rich CLI | **CLI only**: `--trace`, `--now`, and a Markdown transcript export that includes tool calls. No web UI until the user decides | The brief says a CLI is enough; the UI is stretch |
| Persistence | `SqliteSaver` | `InMemorySaver` first; sync `SqliteSaver` under gitignored `.state/` later | Simplest first |
| Tickets | `create_service_protocol` into `sessions.db` | `open_ticket(kind, summary, order_id?)` appending JSON lines to `.state/tickets.jsonl` | No database needed |
| Evals | Three tiers, incl. an LLM judge at temperature 0 and persona simulation | Unit tests + a scripted scenario runner (YAML user turns; assertions on tool calls, on R$ values, on forbidden content). No judge or simulation in the Must tier | Temperature 0 is rejected; scripted runs are reproducible |

### 3.3 Tried and rejected (don't redo these)

- **FTS5/BM25 for policies:** fails on Portuguese word forms (reproduced above).
- **`temperature=0.0` for determinism:** rejected by current Claude models.
- **Hand-picked product alternatives:** the plan's alternative for the nylon 7-string #113 was a steel-string guitar (#112). Compute alternatives in code: same category, same `strings`, nearest price.
- **Volunteering expired promotions on a plain price question:** §7.3 applies only when the customer asks about a promotion.
- **`float` for money.**

---

## 4. Current state

*Updated 2026-11-03, 17:05 (Brasília), by the cloud session, on branch `claude/emporio-agent-handoff-5gfkz8`.*

- **Done:** every step of §5. 153 unit tests pass (no LLM); ruff is clean. `main` was merged into this branch (bringing `AI_USAGE.md` and `AI_USAGE_LOG.md`), so merging this branch into `main` is a fast-forward.
- **Live model:** `google_genai:gemini-3.5-flash` with the user's Google AI Studio key (only in the gitignored `.env`). The five `examples/*.md` were generated by the real agent at `b65c638`. `evals/report.md`: 24/24 scenarios on the final code (median 5.2 s per message), after a harness fix round (20/23 → 23/24) and one prompt nudge.
- **Optional branches, each tested and pushed, not merged:** `feat/persistencia-sqlite` (`--session`, conversations resumable from SQLite), `feat/web-ui-gradio` (`uv run emporio-web`, Gradio chat with tool steps; screenshot in `docs/web-ui.png`), `feat/persistencia-e-web` (this branch + both, conflicts resolved, 162 tests). Each single branch also merges cleanly into this one.
- **Needs the user before submitting:** the GitHub repository is **private** (the brief asks for a public link); `main` does not have this work yet; the deadline is tonight.
- **Not done:** no run against Claude (only the request payload was validated offline).

---

## 5. Next steps, in order

Make one or more small commits per step and push after each; every commit must leave the repo runnable. The detailed designs are in `Plan_Review.md` §5: tools §5.2, policy §5.3, clock §5.4, authentication §5.5, evals §5.8.

1. **Read** this file, `PLAN.md`, `Plan_Review.md`, the brief PDF and the policy PDF.
2. **Skeleton** (`chore:`)
   - `uv init` with `uv python pin 3.12`, using the package layout from `PLAN.md` §9 (`src/emporio_agent/`, `tests/`). Add `pytest` and `ruff` as dev dependencies.
   - Add `.env.example` with variable **names** only (`MODEL=` and the provider key names).
   - `git mv` the six CSVs and both PDFs into `data/`.
   - Update the default paths in `scripts/explore_data.py` and `scripts/review_checks/*.py`, then re-run all three.
   - Start `README.md` (pt-BR) with a setup section, and put the commands in `CLAUDE.md`.
3. **Domain rules** (`feat(domain):`)
   - CSV loaders into typed objects.
   - Availability enum: available = `active AND stock > 0`; discontinued; `coming_soon` = "em breve", not pre-sale.
   - Promotions from `is_active = 1` rows only; PIX 5% only on non-promotional lines.
   - §3.1 installments; shipping per §3.2.
   - `fmt_brl()` and `dd/mm/aaaa` dates; computed alternatives; rule-based data-quality flags (must catch all 7 SKUs).
   - Tests pinned to the values in `Plan_Review.md` §2–§3: GD20 R$ 2.199,00 / PIX R$ 2.089,05 / 12x R$ 183,25; the 12 violões ≤ R$ 1.000; C40 PIX R$ 569,91; R$ 159,90 → 3x.
4. **Policy** (`feat(policy):`)
   - Hand-curate `data/policies.md`: the manual's text verbatim, plus a separate "Notas de interpretação" block.
   - Implement `consult_policy(topics)`.
   - Add a fidelity test that the key facts (address, hours, both phone numbers, 5%, 7/30/90 days, R$ 500 / R$ 35) match the PDF. Use `pypdf` as a dev dependency so tests don't need poppler.
5. **Clock** (`feat(clock):`)
   - Injectable `now()`; add the `tzdata` and `holidays` dependencies.
   - Open/closed status including holidays.
   - Tests: 2026-11-20 closed (Consciência Negra), Saturday 09:00–13:00, Sunday closed.
6. **Agent** (`feat(agent):`), starting with a throwaway spike.
   - The spike confirms, in the installed LangGraph version, that (a) a tool returning `Command` must include a `ToolMessage`, and (b) parallel tool calls see the state from before the step.
   - Persona system prompt in pt-BR. It includes the §7 and §10 rules, no partner-store names (none exist), no price negotiation, and short WhatsApp-style replies.
   - Tools `search_catalog`, `get_product`, `quote`, `consult_policy`, with the signatures in `Plan_Review.md` §5.2.
   - CLI with `--trace`, `--now` and transcript export.
   - Tests with a fake chat model; you'll likely need a small subclass that implements `bind_tools`.
7. **Examples 1 and 5** (`docs(examples):`). Needs an LLM key (§8). Generate them by running the real agent from scripted user turns:
   - (1) violões até R$ 1.000, then installments;
   - (5) address and hours, then a saxophone (empty category).
   - Each file's header records the model, the date, the commit and any `NOW` override.
8. **Orders** (`feat(orders):`): `verify_customer` plus the orders tool. Tests cover customer 43 (the shared e-mail), the 3-attempt lock and generic failure messages.
9. **Returns and handoff** (`feat(returns):`): `check_return` branches on order status first; add `open_ticket`; tests.
10. **Examples 2–4** (`docs(examples):`). Needs an LLM key.
    - (2) Takamine GD20; the customer mentions the old 12% promotion, then asks for strings and an amplifier (decline).
    - (3) "Me arrependi da minha compra" with verification. With the real clock every window has expired, so the answer goes down the warranty path. Optionally add a `NOW=2026-02-20` run where order 7 is eligible, stated in the header.
    - (4) Order status with the Bruno Martins e-mail collision.
11. **Scenario runner** (`test(evals):`): YAML scenarios for the 20 cases in `Plan_Review.md` §6, with assertions on tool calls, on R$ values appearing in tool outputs, and on forbidden content. Run it sparingly, since it makes paid API calls.
12. **README** (`docs(readme):`, pt-BR)
    - Setup, then the architecture and decisions with their justifications (cite the evidence in `Plan_Review.md`).
    - Assumptions: `PLAN.md` §8 plus `Plan_Review.md` §7.
    - Limitations and next steps.
    - "Uso de assistentes de código": Claude Code for `/init`, the plan, the adversarial review and the implementation. Say which review points were accepted or rejected, and why.
13. Update `CLAUDE.md` with the real commands, then **stop** (§9).

---

## 6. Setup

```bash
git clone https://github.com/AugustoMB02/Desafio_tecnico && cd Desafio_tecnico
git checkout handoff/emporio-agent

# What exists today: plain Python 3, standard library only
python3 scripts/explore_data.py
python3 scripts/review_checks/check_numbers.py
python3 scripts/review_checks/fts5_policy_probe.py   # needs pdftotext (poppler-utils)

# Tools for the next steps (install if missing)
command -v uv || curl -LsSf https://astral.sh/uv/install.sh | sh   # or: pip install uv
command -v pdftotext || sudo apt-get install -y poppler-utils        # optional; the Read tool opens PDFs too
```

From step 2 on, the project commands are `uv sync`, `uv run pytest`, `uv run ruff check .` and the CLI entry point. Record them in `CLAUDE.md` once they exist.

Expected runtime dependencies: `langgraph`, `langchain` (for `init_chat_model`), the provider's LangChain package (e.g. `langchain-anthropic`), `tzdata`, `holidays`, and optionally `rich`. Dev dependencies: `pytest`, `ruff`, `pypdf`. Pin them through `uv.lock`.

**Environment variables.** Set these in the environment, never in the repo:
- `MODEL`, e.g. `anthropic:claude-sonnet-5-5` or `anthropic:claude-haiku-5-5` (the current generation of the Haiku/Sonnet tiers `PLAN.md` named);
- the provider's key: `ANTHROPIC_API_KEY` for the first-party Claude API, AWS credentials plus a region with model access for Bedrock, or `OPENAI_API_KEY`, and so on.

---

## 7. Conventions

- **Language:** developer docs (plan, review, handoff) in English. Customer-facing text (system prompt, agent replies, examples, README) in pt-BR.
- **Commits:** conventional prefixes (`docs:`, `chore:`, `fix(scope):`, `feat(scope):`, `test(scope):`), small, each leaving the repo runnable; push regularly. **Never squash, rebase pushed commits or force-push.** The brief grades the history.
- **Tooling:** Python 3.12 via `uv`, `ruff` and `pytest`. Python must stay the repo's main language, so keep JS/CSS/HTML minimal.
- **Formats:** money in `Decimal` (ROUND_HALF_UP); BRL written as `R$ 1.967,18`; dates as `dd/mm/aaaa`; timezone `America/Campo_Grande`.
- **Tools** take IDs, never prices or amounts typed by the model, and return pre-formatted strings next to the raw values.
- **Evidence:** back every number written in a doc with a script or a test, as `Plan_Review.md` does.
- **Paths:** the CSV filenames contain spaces, so always quote them.
- **Secrets:** never commit them. `.env` is gitignored; `.env.example` lists names only.

---

## 8. Known blockers and local-only resources

| Resource | Status | Effect on the cloud session |
|---|---|---|
| LLM API credentials | **None exist yet.** The user's machine had no `.env`, no provider environment variables and no `~/.aws` | **Blocker** for running the agent, generating `examples/` and running the scenario runner. Code plus tests with a fake model can proceed without it |
| Ollama, `qwen3:8b`, RTX 4070 GPU | Local only. Ollama was running on the user's machine with `qwen3:8b` pulled | The local-model path can't be tested in the cloud. Not needed for the deliverables |
| AWS Bedrock access | Not configured | Only matters if the user picks Bedrock |
| Submission deadline | Unknown to this session | Ask the user before relying on it. Nothing may be pushed to the delivery branch after it |
| Merge into `main` | Reviewers will look at `main` | The user's decision (§9) |
| `uv`, `pdftotext` | Installed on the user's machine | Recreate with the commands in §6 |
| Claude Code memory and session context | Local memory was empty; all relevant context is in this file and in `Plan_Review.md` | None |

---

## 9. When to stop

**Done** means the Must tier is complete and pushed to this branch:
- the agent runs from the CLI with a configured model;
- `examples/` holds 3–5 transcripts generated by the real agent;
- the unit tests pass;
- the pt-BR README covers the four required topics;
- `CLAUDE.md` lists the real commands.

Then stop and summarize what was done, what was skipped, and what the user must check.

**If no LLM key is configured:** finish every step that doesn't need a live model. Write the code and the scenario files, and draft the README, noting that the examples are pending. Then stop and report that the examples are blocked on credentials.

**Stop and ask the user before doing any of these:**
- merging into `main`, pushing to it or opening a PR against it, or changing the default branch;
- force-pushing, rebasing or squashing anything already pushed, or deleting branches;
- deleting or editing the raw input files (moving them with `git mv` in step 2 is fine);
- committing any secret, `.env` file or credential;
- pushing anything after the deadline, once it is known;
- building Stretch-tier items (web UI, LLM judge, persona simulation, OTP) or reversing a default in §3.2;
- long or repeated paid API runs beyond generating the examples and a few scenario runs.
