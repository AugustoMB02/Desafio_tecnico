# Empório da Música — agente de atendimento

> *Sua música começa aqui.*

Protótipo de um agente de atendimento por mensagens de texto para a Empório da Música, loja fictícia de instrumentos musicais em Campo Grande/MS (desafio técnico de AI Engineer da Artefact).

> 🚧 Em construção. Este README cresce junto com o código.

## Como rodar

Pré-requisitos: [uv](https://docs.astral.sh/uv/) (instala o Python 3.12 sozinho).

```bash
git clone https://github.com/AugustoMB02/Desafio_tecnico && cd Desafio_tecnico
uv sync                 # cria o .venv e instala as dependências travadas em uv.lock
uv run pytest           # testes
uv run ruff check .     # lint
```

## Estrutura

```text
data/                  # entradas originais do desafio (CSVs + PDFs), sem alterações
src/emporio_agent/     # código do agente
tests/                 # testes automatizados
scripts/               # análise exploratória e checagens do plano (só biblioteca padrão)
PLAN.md                # plano original
Plan_Review.md         # revisão crítica do plano
```
