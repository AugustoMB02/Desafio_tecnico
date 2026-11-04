# Report 03 — Deliverables, Documentation, Scripts & Feature Branches Audit

- **Target Repository:** `https://github.com/AugustoMB02/Desafio_tecnico`
- **Audited Commit on `main`:** `9d5b635`
- **Audited Unmerged Remote Branches:** `origin/feat/persistencia-sqlite` (`20bb8ce`), `origin/feat/web-ui-gradio` (`cd120ef`), `origin/feat/persistencia-e-web` (`49dd014`)
- **Reference Brief:** [`data/desafio_tecnico_ai_eng_artefact.pdf`](../data/desafio_tecnico_ai_eng_artefact.pdf)

---

## Executive Severity Matrix

| ID | Severity | Deliverable / Branch | Finding Summary |
|---|---|---|---|
| **D-01** | **CRITICAL** | Deliverable #1 (GitHub Visibility) | `https://github.com/AugustoMB02/Desafio_tecnico` returns **`HTTP/2 404`** — repository is still **private**, blocking evaluator access. |
| **D-02** | **HIGH** | Deliverable #2 (`README.md` Quick-Start) | `uv run pytest` fails **4/158 tests** out-of-the-box on `LANG=en_US.UTF-8` systems due to missing `language="pt_BR"` in [`src/emporio_agent/clock.py`](../src/emporio_agent/clock.py#L70-L71), breaking the `README.md` evaluation check. |
| **D-03** | **HIGH** | Deliverable #3 ([`examples/03_arrependimento_devolucao.md`](../examples/03_arrependimento_devolucao.md#L42-L63)) | In Turn 2, the agent asserts recorded ETA (`17/02`) as confirmed delivery fact and skips §4.4 exclusion questions; in Turn 3, the scripted customer answers those **unasked** questions — directly contradicting [`README.md`](../README.md#L247). |
| **D-04** | **MEDIUM** | `origin/feat/persistencia-e-web` (`web.py` + `tickets.py`) | Race condition across Gradio tabs: `factory()` creates a separate `TicketStore()` (with a private instance `threading.Lock()`) per tab, allowing concurrent `open_ticket` calls to mint **duplicate `EMP-2026-NNNN` protocols** in `.state/tickets.jsonl`. Also reloads CSVs/LLM per tab. |
| **D-05** | **MEDIUM** | `cli.py` + `origin/feat/persistencia-sqlite` (`persistence.py`) | Mid-turn LLM failure after tool execution checkpoints dangling `['HumanMessage', 'AIMessage', 'ToolMessage']` permanently into `.state/conversas.sqlite`, breaking resumed `--session` runs. |
| **D-06** | **MEDIUM** | `origin/feat/web-ui-gradio` (`web.py`, `persistence.py`) | Gradio Web UI state & security flaws: (1) Retry/Undo (`fresh=not history`) wipes verified state on Turn 1 or desyncs LangGraph state from UI on Turn 2+; (2) `session_hash` fallback `"local"` collides for stateless API callers; (3) no per-`Session` lock around `session.send()` and unbounded `_sessions` dict RAM leak; (4) unclosed `sqlite3.Connection`; (5) `gradio` added as mandatory core dependency (+34 packages). |
| **D-07** | **MEDIUM** | [`HANDOFF.md`](../HANDOFF.md#L39-L97) on `main` | Internal contradictions: §2 (`L39`) claims *"no application code"* exists while §4 (`L93`) says *"Done"*; §4 (`L96`) falsely states *"`main` does not have this work yet"*; §4 (`L95`) cites `162 tests` for `feat/persistencia-e-web` (actual: `167`). |
| **D-08** | **MEDIUM** | [`AI_USAGE.md`](../AI_USAGE.md#L23-L69) on `main` | Contains 4 non-portable `file:///home/augusto/Desktop/Desafio_tecnico/...` URLs (`L23`, `L28`, `L39`, `L69`) that render as dead links on GitHub and leak local filesystem paths. |
| **D-09** | **LOW** | [`pyproject.toml`](../pyproject.toml#L25), [`.env.example`](../.env.example#L12-L16), [`scripts/`](../scripts/) | `uv_build>=0.11.32,<0.12.0` emits a warning on `uv 0.13.7`; no static type checker configured despite `# type: ignore[misc]` and `.mypy_cache/`; `.env.example` lists uninstalled OpenAI/AWS variables; stale path comments in `scripts/`; `fts5_policy_probe.py` requires system `pdftotext`. |
| **D-10** | **LOW** | Feature Branch Docs (`README.md`, `HANDOFF.md`, `CLAUDE.md`) | On `feat/web-ui-gradio` & `feat/persistencia-e-web`, `README.md` says *"Uma UI web ficou para depois"* right above *"acrescentei um chat web"*; adjacent `167` vs `162` test counts in `HANDOFF.md`; stale `158 testes` on single-feature branches; `CLAUDE.md` omits `persistence.py` / `--session`. |
| **D-11** | **LOW** | Git History & [`evals/report_dificeis.md`](../evals/report_dificeis.md#L20-L140) | Zero secrets/PII in git history (verified). Minor: PR #1 merge commit `9d5b635` body says `fix(scripts): resolve EDA data path relative to the repo`; in `report_dificeis.md:20,100` agent asks customer for CEP despite having no CEP tool. |

---

## 1. GitHub Visibility & Git History Audit

### [D-01 — CRITICAL] GitHub Repository Returns HTTP 404 (Still Private)
- **Brief Requirement:** [`data/desafio_tecnico_ai_eng_artefact.pdf`](../data/desafio_tecnico_ai_eng_artefact.pdf) p. 2 (*"1. Repositório Git Público: Link para o repositório público do seu projeto no GitHub"*) and p. 3 (*"O link do repositório público"*).
- **Verification:**
  ```bash
  $ curl -sI https://github.com/AugustoMB02/Desafio_tecnico | head -n 5
  HTTP/2 404
  date: Wed, 04 Nov 2026 00:28:24 GMT
  content-type: text/html; charset=utf-8
  ```
- **Impact:** Any unauthenticated reviewer opening the repository URL gets a 404 page and cannot inspect the submission.

### [D-11a — PASS / LOW] Secrets, PII & Commit History Check
- **Secrets & Runtime PII Scan (PASS):** Scanned all reachable git objects (`git rev-list --all --objects`) and patch history (`git log --all -p`) across all local and remote branches for `AIza*`, `AQ.*`, `sk-ant-*`, `sk-*`, `AKIA*`, `.env`, `.state/`, `.sqlite`, and `.jsonl`. **Zero secrets, `.env` files, or customer PII files were ever committed.**
- **Minor Commit History Notes:**
  - Merge commit `9d5b635` (`Merge pull request #1 from AugustoMB02/claude/emporio-agent-handoff-5gfkz8`) auto-copied its body from the first commit on the branch (`fix(scripts): resolve EDA data path relative to the repo`), understating that PR #1 merged the entire implementation.
  - Commits `52b0d87..e602a39` are authored as `Claude <noreply@anthropic.com>` with `Claude-Session:` trailers, matching the transparent narrative in `README.md` and `AI_USAGE_LOG.md`.

---

## 2. Deliverable #3 (`examples/*.md`) & Documentation Cross-Audit

### [D-03 — HIGH] Unasked Scripted Answer & Unconfirmed ETA Fact in `examples/03_arrependimento_devolucao.md`
- **Locations:** [`examples/03_arrependimento_devolucao.md`](../examples/03_arrependimento_devolucao.md#L42-L63), [`examples/scripts/03_arrependimento_devolucao.yaml`](../examples/scripts/03_arrependimento_devolucao.yaml#L14), and [`README.md`](../README.md#L247).
- **Evidence:**
  1. In Turn 2 (`examples/03_arrependimento_devolucao.md:42`), `check_return` returns:
     - `"recebimento": "17/02/2026 (previsão de entrega registrada; confirme com o cliente)"`
     - `"verificar_com_cliente": ["instrumento com personalização ou ajuste sob encomenda (setup, regulagem especial)", "compra em liquidação com aviso explícito de \"venda final\""]`
  2. Yet in Turn 2 (`L49-61`), the agent **asserts `Como ele foi entregue dia 17/02` as established fact** and **never asks** whether the item arrived on 17/02, had custom setup, or was bought on final-sale clearance! (It also paraphrases Policy §4.1's *"na mesma forma de pagamento original"* into *"na mesma fatura do cartão de crédito"* at `L54`, which is inaccurate if the card cycle closed, and omits *"acessórios"* at `L52`.)
  3. Then in Turn 3 (`L63`), the pre-scripted user turn replies:
     > `**Cliente:** Recebi no dia 17 mesmo, e não fiz nenhum ajuste nem comprei em liquidação. Pode abrir a devolução, por favor.`
     — answering two policy verification questions **the agent never asked**!
  4. **Contradiction with `README.md:247`:** `README.md` explicitly cites this exact failure mode as solved (`"afirmava a previsão de entrega como data de recebimento... A correção foi nas ferramentas e no prompt (commit 2d65a27)... Os exemplos foram gerados de novo"`), yet all 5 files in `examples/` were generated at commit `b65c638` (also predating `16da6fe`'s `quote`/`prompts` fixes) and still contain the defect in `examples/03_arrependimento_devolucao.md`.

### [D-07 — MEDIUM] Stale & Self-Contradictory Statements in `HANDOFF.md` on `main`
- **Locations:** [`HANDOFF.md`](../HANDOFF.md#L39) and [`HANDOFF.md`](../HANDOFF.md#L93-L96).
- **Evidence:**
  1. Line 39 states in the present tense: *"Nothing else exists yet: no application code, no `pyproject.toml`, no tests, no `examples/`, and `README.md` is a one-line stub"*, directly contradicting §4 (`L93`: *"Done: every step of §5. 158 unit tests pass"*).
  2. Line 96 states *"`main` does not have this work yet"*, even though `HANDOFF.md` is now on `main` (`9d5b635`).
  3. Line 95 states `feat/persistencia-e-web (this branch + both, conflicts resolved, 162 tests)`, whereas `origin/feat/persistencia-e-web` actually has **167 tests**.

### [D-08 — MEDIUM] Broken / Non-Portable `file://` URLs in `AI_USAGE.md`
- **Locations:** [`AI_USAGE.md`](../AI_USAGE.md#L23), [`L28`](../AI_USAGE.md#L28), [`L39`](../AI_USAGE.md#L39), and [`L69`](../AI_USAGE.md#L69) (linked directly from [`README.md`](../README.md#L240)).
- **Evidence:** Four Markdown links use `file:///home/augusto/Desktop/Desafio_tecnico/...` instead of relative repository paths (`CLAUDE.md`, `scripts/explore_data.py`, `PLAN.md`). GitHub strips `file://` URLs as non-clickable text while exposing the local machine path. (All other links across `README.md`, `CLAUDE.md`, `PLAN.md`, `Plan_Review.md`, `AI_USAGE_LOG.md`, `examples/*.md`, and `evals/*.md` were verified valid.)

### [D-11b — LOW] False Capability Offer (CEP Calculation) in `evals/report_dificeis.md`
- **Locations:** [`evals/report_dificeis.md`](../evals/report_dificeis.md#L20) and [`L100`](../evals/report_dificeis.md#L100).
- **Evidence:** Because `catalog.py:352` outputs `"peça o CEP"`, the agent invites non-Campo-Grande customers to share their CEP (*"Se quiser me passar o CEP pra gente calcular o frete"*), even though no tool can compute freight from a CEP. Also at `L140`, the agent apologizes for *"atraso no envio do seu pedido #8"* when Order #8 is already `shipped` (delayed in transit, not dispatch).

---

## 3. Standalone Scripts & Build Configuration Check

- **Script Execution Verification:**
  - `python3 scripts/explore_data.py` -> **PASS** (`exit=0`)
  - `python3 scripts/review_checks/check_numbers.py` -> **PASS** (`exit=0`)
  - `python3 scripts/review_checks/fts5_policy_probe.py` -> **PASS** (`exit=0` when `/usr/bin/pdftotext` is installed)
- **[D-09 — LOW] Build & Script Hygiene Issues:**
  1. **`uv_build` upper bound ([`pyproject.toml`](../pyproject.toml#L25)):** `requires = ["uv_build>=0.11.32,<0.12.0"]` prints `warning: build_system.requires = ["uv-build>=0.11.32,<0.12.0"] does not contain the current uv version 0.13.7` during `uv sync`.
  2. **No configured static type checker:** [`.gitignore`](../.gitignore#L12) lists `.mypy_cache/` and [`src/emporio_agent/clock.py`](../src/emporio_agent/clock.py#L115) has `# type: ignore[misc]`, but no type checker (`mypy`/`pyright`/`ty`) is in `dev` dependencies.
  3. **Uninstalled provider env vars ([`.env.example`](../.env.example#L12-L16)):** Lists `OPENAI_API_KEY` and `AWS_*` keys without inline comments noting that `langchain-openai` / `langchain-aws` must be installed via `uv add`.
  4. **Stale path comments & `pdftotext` binary dependency in `scripts/`:** [`scripts/explore_data.py`](../scripts/explore_data.py#L7) and [`scripts/review_checks/check_numbers.py`](../scripts/review_checks/check_numbers.py#L6-L7) still comment that CSVs live at the repository root; [`scripts/review_checks/fts5_policy_probe.py`](../scripts/review_checks/fts5_policy_probe.py#L23-L26) shells out to `pdftotext` instead of `pypdf` (already in `dev` dependencies).

---

## 4. Unmerged Feature Branches Audit (`origin/feat/persistencia-e-web`)

Audited `origin/feat/persistencia-sqlite` (`20bb8ce`), `origin/feat/web-ui-gradio` (`cd120ef`), and `origin/feat/persistencia-e-web` (`49dd014`) in an isolated `/tmp` extraction (`ruff` clean; `167/167` tests pass under `LANG=C.UTF-8`, `4/167` fail under `LANG=en_US.UTF-8` due to `C-01`/`D-02`):

### [D-04 — MEDIUM] Race Condition Minting Duplicate Ticket Protocols Across Gradio Tabs (`web.py` + `tickets.py`)
- In `web.py:131-132`, `factory()` calls `build_session(args.model, args.now)[0]` on **every new browser tab**:
  1. Re-parses all 6 CSVs and re-initializes the LLM client per tab.
  2. Instantiates a fresh `TicketStore()` whose `self._lock = threading.Lock()` is an **instance attribute**, not a shared or file lock.
- Concurrent `open_ticket` calls from two browser tabs read the same line count in `.state/tickets.jsonl` and write **duplicate `EMP-2026-NNNN` protocol numbers**.

### [D-05 — MEDIUM] Mid-Turn Model Failure Persists Corrupted History in `.state/conversas.sqlite` (`persistence.py`)
- Reproduced on `origin/feat/persistencia-e-web`: if `ToolNode` finishes step 2 and the synthesis LLM call fails (`429` / `503`), `SqliteSaver` permanently persists `['HumanMessage', 'AIMessage', 'ToolMessage']` in `.state/conversas.sqlite`. Resuming `--session <nome>` appends a new `HumanMessage` directly after `ToolMessage`, breaking strict turn-alternation providers on every subsequent message in that session.

### [D-06 — MEDIUM] Gradio Web UI State Desync, `"local"` Fallback Collision & Resource Leaks (`web.py`, `persistence.py`)
1. **Gradio Retry / Undo Desync (`web.py:82`):** `session = sessions.get(key, fresh=not history)` ignores `history` contents except emptiness. Clicking **Retry** on Turn 1 passes `history=[]` (`fresh=True`), wiping customer verification; clicking **Undo/Retry** on Turn 2+ passes non-empty `history` (`fresh=False`), leaving undone messages inside LangGraph's `InMemorySaver` while removing them from the browser UI.
2. **Shared `"local"` Fallback (`web.py:81`):** `key = getattr(request, "session_hash", None) or "local"` maps any direct API caller omitting `session_hash` to one shared `"local"` session (risking cross-caller PII bleed after `verify_customer`). (Normal browser tabs were verified live with two `gradio_client.Client` instances to receive separate `session_hash` keys.)
3. **Concurrency & Leaks (`web.py:58-70`, `persistence.py:23`):** `WebSessions._lock` only guards dictionary lookup, not `session.send(message)`; `_sessions` never evicts closed tabs (unbounded memory growth); `persistence.py:23` never closes `sqlite3.Connection`; and `gradio>=6.31.0` adds 34 transitive packages (`pandas`, `numpy`, `fastapi`, `uvicorn`, etc.) to mandatory core dependencies instead of `[project.optional-dependencies]`.

### [D-10 — LOW] Documentation Contradictions on the Feature Branches
- On `origin/feat/web-ui-gradio` & `origin/feat/persistencia-e-web`, `README.md:161-163` retains *"Uma UI web ficou para depois (ver próximos passos)."* directly above *"Depois de o agente estar pronto, acrescentei um chat web em Python puro (Gradio, `uv run emporio-web`)"*.
- `HANDOFF.md:95-96` on `feat/persistencia-e-web` states both `167 tests` and `162 tests` on adjacent lines; single-feature branches leave `158 testes` stale in `README.md`; `CLAUDE.md` omits `persistence.py` and `--session`.

---

## 5. Brief Deliverable Checklist (`desafio_tecnico_ai_eng_artefact.pdf`)

| Brief Requirement | Status on `main` (`9d5b635`) | Notes |
|---|---|---|
| **1. Public GitHub Repository** | ❌ **BLOCKED (`D-01`)** | Returns `HTTP/2 404` — must flip visibility to **Public** in GitHub Settings before sending link. |
| **Incremental Commit History** | ✅ **PASS** | 36+ granular commits with clear conventional messages across EDA, domain, graph, evals, and docs. |
| **Python as Primary Language** | ✅ **PASS** | Python 3.12 (`src/emporio_agent/`, `tests/`, `scripts/`). |
| **Operational Data vs. Policy Routing + Persona + Out-of-Scope Refusal** | ✅ **PASS (with bugs in Report 01 & 02)** | Implemented cleanly via LangGraph + 8 typed tools; fix critical edge cases (`C-01..C-06`) before final tag. |
| **2. Comprehensive `README.md` (Setup, Justifications, Limitations, AI Usage, Assumptions)** | ⚠️ **MOSTLY PASS (`D-02`, `D-03`, `D-08`)** | Thorough pt-BR `README.md` with 18 explicit assumptions, but `uv run pytest` fails 4 tests on `en_US` (`D-02`), `README.md:247` contradicts `examples/03` (`D-03`), and linked `AI_USAGE.md` has 4 `file://` links (`D-08`). |
| **3. Example Interactions (`examples/*.md`)** | ⚠️ **NEEDS REGENERATION (`D-03`)** | 5 real transcripts with tool traces exist, but `examples/03_arrependimento_devolucao.md` has the unasked-question / unconfirmed-ETA flaw and predates commit `16da6fe`. |
