# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project status

This repo holds a take-home challenge (Artefact, AI Engineer). Right now it contains only the inputs: CSVs, two PDFs and a stub README. No code, dependencies, build, lint or test setup exists yet. When you add tooling, put its commands in this file.

The full brief is in `desafio_tecnico_ai_eng_artefact.pdf`. Read it with `pdftotext -layout <file> -`. Everything in the brief and the data is in Portuguese (pt-BR), and the agent must answer customers in Portuguese.

## The task

Prototype a text-message customer-service agent for **Empório da Música**, a fictional musical-instrument store in Campo Grande/MS. The agent must:
- Take on a persona that fits the store's identity and tone (slogan: "Sua música começa aqui.").
- Decide when to query **operational data** (prices, stock, order status) and when to consult **policies** (returns/exchanges, opening hours, payment methods).
- Handle out-of-scope questions gracefully. The store sells **only instruments**: no strings, picks, cables, cases, pedals or amplifiers (policies §1).

Hard constraint: **Python** must be the main language. Framework, LLM provider, interface (CLI/notebook/API/UI), history persistence and data cleaning are free choices, but each must be justified in the README.

## Required deliverables (they shape the repo)

- A public GitHub repo with a **real, incremental commit history**. Never squash or force-push. Nothing may change after the deadline.
- A `README.md` (pt-BR) covering:
  - setup and run instructions (environment, model provider, commands)
  - the reasoning behind each technical decision (framework, LLM, retrieval architecture, prompt strategy)
  - known limitations and what would come next with more time
  - a section on how AI coding assistants were used (this includes Claude Code)
- **3–5 example conversations** (`.md`/`.txt`/images) committed to the repo. At least one must be non-trivial: a live data lookup or a policy rule being applied. Suggested scenarios from the brief:
  - "Quais opções de violões disponíveis custando até R$1000?"
  - "Qual o endereço da loja?"
  - "Quanto custa o Takamine GD20?"
  - "Me arrependi da minha compra, posso devolver meu pedido?"
- Where the brief is ambiguous, pick a reasonable interpretation and document it in the README as an assumption.

## Data layout and quirks

The brief places the files under `data/`, but they currently sit at the repo root. Each CSV filename has a `desafio_tecnico_ai_eng - ` prefix with spaces (e.g. `desafio_tecnico_ai_eng - products.csv`), so always quote these paths.

Relational schema (join keys):
- `products` (`product_id`, `price_brl`, `name`, `category_id`, `description`, `stock_quantity`, `status`, `specs`, `created_at`): `specs` holds a JSON object stored as a CSV-quoted string.
- `categories` (`category_id`, `name`, `description`)
- `customers` (`customer_id`, `name`, `phone`, `email`, `city`): contains PII. Decide how the agent identifies a customer before it reveals any order data.
- `orders` (`order_id`, `customer_id`, `order_date`, `status`, `total_brl`, `payment_method`, `tracking_code`, `estimated_delivery`, `notes`)
  - `status` values: `pending`, `confirmed`, `shipped`, `delivered`, `cancelled`
  - `payment_method` values look like `pix` or `credit_6x`
- `order_items` (`order_id`, `quantity`, `product_id`): bridges orders and products.
- `promotions` (`promotion_id`, `product_id`, `discount_percent`, `description`, `is_active` as 0/1): only rows with `is_active=1` should change a quoted price.

`políticas_da_loja.pdf` is the internal policy manual (v2.1, June 2025). It covers store info, hours, payment, returns and exchanges, and service procedures, and it is the source for RAG or policy lookups. It has inconsistencies, such as the e-mail written both as `contato@emporiodamusica.com.br` and `contato@empóriodamusica.com.br`. Check its facts against the source rather than assuming they are clean.
