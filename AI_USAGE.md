# AI Coding Assistants Usage Log & Workflow Documentation

> **Status note (2026-11-03):** this log covers the planning phase. Some plan choices described below (FTS5/BM25 retrieval, Bedrock + Ollama, a FastAPI web chat, simulated OTP login, an LLM judge at temperature 0) were changed after the review in [`Plan_Review.md`](Plan_Review.md); the README has the final decisions. The pt-BR draft in section 4 was superseded by the README section *Uso de assistentes de código*.

> **Purpose of this file:** The Artefact AI Engineer challenge brief explicitly asks candidates to explain which AI coding assistants were used and how they were integrated into the engineering workflow (*"Uso de assistentes de código: caso faça uso de algum recurso de IA, explique qual a escolhida e como utilizou. Queremos entender o seu workflow"*).
>
> This document tracks our human-in-the-loop AI workflow incrementally on `main` as the project evolves, and includes a ready-to-use `pt-BR` section at the bottom for the final `README.md`.

---

## 1. Tools Used & Core Workflow Philosophy

- **Tools Used:** **Antigravity** (Google DeepMind agentic coding environment) and **Claude Code** (`CLAUDE.md` project context convention).
- **Workflow Paradigm:** **Research & Specification First $\rightarrow$ Socratic Design Review (`/grill-me`) $\rightarrow$ Human Architectural Steering $\rightarrow$ Test-Driven Incremental Implementation.**

Instead of treating the AI assistant as an autonomous "one-shot code generator" (which often produces brittle architectures that miss domain edge cases), the AI was used as a **pair-programming researcher, forensic data auditor, and devil's advocate**, while all high-level architectural decisions, security boundaries, UX requirements, and business-rule trade-offs were actively steered and validated by the human engineer.

---

## 2. Phase-by-Phase Log of How AI Was Used So Far

### Phase 0: Context Bootstrapping (`CLAUDE.md`)
- **How AI was used:** Created [CLAUDE.md](file:///home/augusto/Desktop/Desafio_tecnico/CLAUDE.md) to establish persistent repository context from `desafio_tecnico_ai_eng_artefact.pdf` and `políticas_da_loja.pdf` (relational join keys, hard constraints like Python as primary language and `pt-BR` customer outputs, and deliverable rules such as incremental Git history without force-pushes).
- **Why it mattered:** Prevented context drift across turns and ensured every subsequent action respected the challenge's non-negotiable constraints.

### Phase 1: Forensic Exploratory Data Analysis (EDA) & Policy Cross-Audit (`scripts/explore_data.py` & `PLAN.md`)
- **Prompt / Direction given by Engineer:** Instructed the assistant not to write application code yet, but first to conduct a rigorous **data exploration phase** across all 6 CSVs and `políticas_da_loja.pdf`, recording, documenting, and justifying how the data should be organized and cleaned.
- **How AI accelerated the work:** Generated and executed [scripts/explore_data.py](file:///home/augusto/Desktop/Desafio_tecnico/scripts/explore_data.py) to cross-check every row, foreign key, JSON schema, price calculation, and policy rule.
- **Key traps uncovered through this audit:**
  1. **Expired promotion trap on a suggested prompt:** `Takamine GD20` (`product_id=95`, R\$ 2.199,00) has a 12% discount row in `promotions.csv` with `is_active=0` (`promotion_id=4`). A naive join without `is_active=1` violates Policy §7.3.
  2. **Availability vs. status traps on *"violões até R\$ 1.000"*:** `ID=96` (R\$ 799,90) has `status='active'` but `stock_quantity=0`; `ID=113` (R\$ 749,00) is `discontinued`; `ID=136` is `discontinued` *despite* `stock_quantity=13`; and `ID=101` (R\$ 1.049,00) drops to **R\$ 996,55 via the 5% PIX discount** (§3).
  3. **Synthetic catalog contradictions (`IDs 135, 137, 139, 140, 142, 144`):** Brand, wood, and string/key counts conflict across `name`, `description`, and `specs` JSON in Categories 2, 3, and 4.
  4. **Empty store categories (`6, 7, 8`):** Woodwinds, Brass, and Orchestral Strings exist in `categories.csv` and Policy §1, but have 0 rows in `products.csv` (distinct from out-of-scope accessories like strings, picks, cables, cases, pedals, and amps).
  5. **LGPD duplicate-email collision:** `bruno.martins@jmail.com` belongs to **two different customers** (`customer_id=11` with an R\$ 8.732 order, and `customer_id=43` with 0 orders).
  6. **Policy PDF internal inconsistencies:** Accented `contato@empóriodamusica.com.br` (§1.2) vs. valid ASCII `contato@emporiodamusica.com.br` (Cover); two phone/WhatsApp numbers (`(67) 3341-4444` vs. `(67) 3321-4500`); §3 summary table (`Parcela mínima R$ 100`) vs. §3.1 tiered minimums (`R$ 50 / R$ 80 / R$ 100`); and §4.2 (30-day store defect exchange) vs. §8.1 (90-day CDC legal warranty).

### Phase 2: SOTA Literature Review & Evaluation Design (`PLAN.md`)
- **Prompt / Direction given by Engineer:** Asked the assistant to conduct a literature review of the current State of the Art (2023–2026) to justify framework choices, data organization, retrieval strategy, and whether to use **LLM-as-a-Judge** or another evaluation approach.
- **How AI accelerated the work:** Synthesized academic and industry benchmarks in [PLAN.md](file:///home/augusto/Desktop/Desafio_tecnico/PLAN.md):
  - **$\tau$-bench (Yao et al., 2024)** & **ReAct (Yao et al., 2023):** Showed why retail customer-service agents fail when arithmetic, discounts, or auth gates are left to LLM token prediction rather than deterministic tools.
  - **BIRD (Li et al., 2023) & CAREFUL / OWASP LLM Top 10 (2025):** Grounded the rejection of raw Text-to-SQL in favor of parameterized domain functions with server-side authorization state (`InjectedState`).
  - **Cache-Augmented Generation — CAG (Chan et al., WWW 2025):** Grounded why chunking an 8-page (~2,350-token) policy manual into a vector DB is an anti-pattern that severs tables (§3) from exception clauses (§3.1), justifying **Section-Aware Structured Markdown + SQLite FTS5 (`bm25`)** instead.
  - **MT-Bench (Zheng et al., 2023), G-Eval (Liu et al., 2023), Prometheus 2 (Kim et al., 2024) & Anthropic Evals (2025):** Grounded our **3-Tier Hybrid Evaluation Pyramid** — deterministic `pytest` code & trajectory graders first for objective math/routing/PII checks, paired with **decomposed binary (`PASS`/`FAIL`) Chain-of-Thought LLM-as-a-Judge rubrics** (`temperature=0.0`, no 1–5 Likert scales) strictly for tone, empathy, and policy completeness.

### Phase 3: Interactive Design Interrogation (`/grill-me`) & Human Overrides
Rather than accepting the AI's initial draft plan as-is, I used the `/grill-me` workflow to walk down each branch of the design tree one decision at a time. **Several key architectural choices were actively overridden or refined by human engineering judgment:**

| Design Topic | Initial AI Draft / Options | Human Engineer Steering / Override | Resulting Architecture in `PLAN.md` |
| :--- | :--- | :--- | :--- |
| **1. Agent Framework** | Initially proposed `PydanticAI` as primary, with `LangGraph` as alternative. | **Overrode to `LangGraph`:** Chose `LangGraph` (`StateGraph`) as the better fit for explicit stateful orchestration and checkpointing. | Unified `LangGraph` `StateGraph` with `context_and_guardrail_node`, `ToolNode` (`Command` + `InjectedState`), and `SqliteSaver`. |
| **2. LLM Provider & Privacy** | Initially suggested public cloud APIs (Gemini / OpenAI). | **Steered toward Local + Enterprise AWS:** Requested local execution or **AWS** for enterprise data safety. Assistant inspected local hardware (`i9-13900HX`, `RTX 4070 8 GB VRAM`), and we converged on a dual setup. | **Dual-Provider Factory:** **AWS Bedrock** (`ChatBedrockConverse` for LGPD governance & LLM-as-a-Judge) + **Local Ollama** (`qwen3:8b` / `qwen2.5:7b` sized for 8 GB VRAM). |
| **3. User Interface** | Initially emphasized CLI + generic Chainlit/Streamlit. | **Steered toward Customer-First UX:** Specified that the UI must be genuinely pretty and intuitive for a real customer. | **FastAPI + Bespoke *Empório da Música* Web Chat** (WhatsApp-inspired UX, starter chips, MS store-hours badge) + hidden-by-default **Evaluator Inspector Drawer** + CLI. |
| **4. Customer Auth UX** | Initially proposed conversational 2-of-3 verification only. | **Designed Dual-Path Login + Fallback:** Proposed that logged-in customers verify via a **simulated OTP code** sent to email/phone (documenting real SMS/email as a prototype limitation), with **2-of-3 verification** as the fallback for unlogged visitors. | Hybrid Auth supporting both in-app simulated OTP login and conversational 2-of-3 (`Order ID`, `E-mail`, `Phone`), safely disambiguating `bruno.martins@jmail.com`. |
| **5. Reference Clock** | AI recommended defaulting the clock to `2026-03-23` (day after last CSV order). | **Overrode to Real Wall-Clock Default:** Chose real `datetime.now()` in `America/Campo_Grande` (`UTC-4`) as default so live store hours match reality, keeping `REFERENCE_DATE` as an explicit override for historical return-window demos. | Live `America/Campo_Grande` (`UTC-4`) clock by default + `.env` / UI Evaluator Drawer date override. |
| **6. Git Workflow** | AI waited for manual review before committing. | **Enforced Continuous Pushing:** Instructed the assistant to commit and push to `origin/main` continuously at every milestone. | Incremental, transparent commits pushed live to `origin/main`. |

---

## 3. Summary of Responsibilities (Human vs. AI)

- **Human Engineer (Augusto):**
  - Defined the phased engineering methodology (EDA & literature review before coding; documented justifications for every choice).
  - Selected **LangGraph** as the orchestration framework and defined the enterprise privacy posture (**AWS Bedrock** + **local RTX 4070 Ollama**).
  - Set the product UX bar (customer-friendly interface) and designed the **hybrid authentication flow** (simulated OTP login for existing accounts + 2-of-3 conversational verification for guests).
  - Made the final call on temporal behavior (real `UTC-4` wall-clock default with explicit demo override), non-destructive data enrichment, read-only operational DB with protocol tickets, and continuous Git push discipline.
- **AI Coding Assistant (Antigravity):**
  - Wrote and ran the automated data-exploration script (`scripts/explore_data.py`) to surface all CSV/PDF edge cases and cross-table inconsistencies.
  - Compiled the SOTA literature review (ReAct, $\tau$-bench, CAG, BIRD/CAREFUL, G-Eval/Anthropic Evals) with citations and architectural trade-off matrices.
  - Facilitated the structured `/grill-me` design tree walkthrough, checked local hardware specs (`nvidia-smi` / `lscpu`), and synthesized decisions into [PLAN.md](file:///home/augusto/Desktop/Desafio_tecnico/PLAN.md).

---

## 4. Draft Section in `pt-BR` for the Final `README.md`

*(The section below is ready to be included and expanded in the final `README.md` deliverable.)*

### Uso de Assistentes de Código (Workflow com IA)

Durante o desenvolvimento deste desafio, utilizei o **Antigravity** (ambiente agêntico de desenvolvimento) guiado por um arquivo de contexto de repositório ([`CLAUDE.md`](CLAUDE.md)) seguindo uma metodologia **Spec-First e Human-in-the-Loop** (Engenharia Orientada a Especificação e Revisão Socrática), em vez de geração automática de código sem supervisão:

1. **Auditoria Forense de Dados antes do Código (`scripts/explore_data.py`):** Antes de escolher o framework ou escrever prompts, direcionei o assistente para inspecionar programaticamente os 6 arquivos CSV e o manual `políticas_da_loja.pdf`. Essa etapa revelou armadilhas críticas de negócio (como a promoção expirada `is_active=0` no *Takamine GD20*, os violões indisponíveis/descontinuados abaixo de R\$ 1.000, o desconto de PIX levando o *Giannini GNF-3 CEQ* para R\$ 996,55, as contradições sintéticas de marca/especificação nos SKUs `135–144`, a colisão de e-mail em `bruno.martins@jmail.com` e as divergências internas do PDF).
2. **Revisão de Literatura (SOTA) Aplicada à Arquitetura (`PLAN.md`):** Utilizei o assistente para contrastar abordagens da literatura recente ($\tau$-bench, ReAct, *Cache-Augmented Generation* [CAG], benchmarks de segurança em Text-to-SQL e avaliação com *LLM-as-a-Judge*), fundamentando tecnicamente por que funções determinísticas superam Text-to-SQL aberto em segurança/LGPD e por que indexação estruturada por seção + SQLite FTS5 (`bm25`) evita a quebra de tabelas de parcelamento que ocorre no chunking vetorial ingênuo.
3. **Direcionamento Arquitetural e Sobrescrita Humana (`/grill-me`):** Todas as decisões de arquitetura foram tomadas de forma interativa, onde revisei e redirecionei recomendações iniciais da IA com base em restrições reais de negócio e hardware:
   - **Escolha do LangGraph:** Optei pelo **LangGraph** (`StateGraph` com `InjectedState`, `Command` e `SqliteSaver`) no lugar da sugestão inicial de `PydanticAI`, garantindo controle explícito de estado e persistência nativa.
   - **Privacidade e Execução Híbrida de LLM (AWS Bedrock + Ollama Local):** Defini a necessidade de execução local (em GPU NVIDIA RTX 4070 de 8 GB VRAM via Ollama com modelos 8B quantizados) combinada ao **AWS Bedrock** (`ChatBedrockConverse`) para governança corporativa de dados (LGPD) e execução confiável do *LLM-as-a-Judge*.
   - **Experiência do Cliente (UX) e Autenticação Híbrida:** Direcionei o design para uma interface web intuitiva focada no cliente (**FastAPI + Web Chat Empório da Música** com gaveta opcional de inspeção para avaliadores) e propus o fluxo duplo de autenticação: **login simulado via código OTP** (e-mail/telefone, documentando a integração real de envio como limitação do protótipo) aliado à **verificação conversacional 2-de-3** (`ID do pedido`, `E-mail`, `Telefone`) para visitantes não logados.
   - **Relógio Real (`America/Campo_Grande`, UTC-4) com Override Explícito:** Sobrescrevi a sugestão de fixar a data padrão no passado (`2026-03-23`), mantendo o horário real de Mato Grosso do Sul como padrão e expondo `REFERENCE_DATE` como override explícito para simulação de janelas históricas de devolução.
