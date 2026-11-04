# Empório da Música — agente de atendimento

> *Sua música começa aqui.*

Protótipo em Python de um agente de atendimento por mensagens de texto para a **Empório da Música**, loja fictícia de instrumentos musicais em Campo Grande/MS (desafio técnico de AI Engineer da Artefact).

O agente conversa em português no tom da loja ("um amigo que entende de música"), decide quando consultar **dados da operação** (catálogo, preços, promoções, estoque, pedidos) e quando consultar **políticas** (horários, pagamento, trocas, frete, garantia, LGPD), verifica a identidade do cliente antes de mostrar pedidos, calcula prazos de devolução e registra chamados para a equipe. Pedidos fora do escopo (acessórios, assuntos sem relação com a loja) são recusados com gentileza.

**Avaliação rápida:** as [5 conversas em `examples/`](#exemplos-de-conversa) foram geradas pelo agente real e mostram, em cada resposta, as ferramentas consultadas com entrada e saída; `uv run pytest` roda os testes sem chave de API; com uma chave, `uv run emporio-agent --trace` abre o chat mostrando as chamadas de ferramenta, e [`evals/report.md`](evals/report.md) e [`evals/report_dificeis.md`](evals/report_dificeis.md) trazem as últimas rodadas dos 54 cenários roteirizados (24 de regressão e 30 difíceis). Uma auditoria externa feita por outra IA e a resposta a cada achado estão em [`reports/`](reports/).

- [Como rodar](#como-rodar)
- [Exemplos de conversa](#exemplos-de-conversa)
- [Arquitetura](#arquitetura)
- [Decisões técnicas e justificativas](#decisões-técnicas-e-justificativas)
- [Suposições](#suposições)
- [Testes e avaliação](#testes-e-avaliação)
- [Limitações e próximos passos](#limitações-e-próximos-passos)
- [O que mudaria em produção](#o-que-mudaria-em-produção)
- [Uso de assistentes de código](#uso-de-assistentes-de-código)

---

## Como rodar

**Pré-requisitos:** [uv](https://docs.astral.sh/uv/) (ele baixa o Python 3.12 sozinho) e uma chave de API de um provedor de LLM.

```bash
git clone https://github.com/AugustoMB02/Desafio_tecnico && cd Desafio_tecnico
uv sync                       # cria o .venv e instala as dependências travadas em uv.lock

cp .env.example .env          # e preencha UMA das opções (formato provider:modelo):
#   MODEL=google_genai:gemini-3.5-flash  +  GOOGLE_API_KEY=...     (usado nos exemplos)
#   MODEL=anthropic:claude-sonnet-5-5    +  ANTHROPIC_API_KEY=...
#   MODEL_EFFORT=low                     (opcional, só Claude: menos "pensamento", mais rápido)

uv run emporio-agent          # conversa no terminal ("sair" encerra)
```

Opções do CLI:

| Opção | O que faz |
|---|---|
| `--trace` | mostra cada chamada de ferramenta, com argumentos e resultado |
| `--now 2026-02-20T10:00` | congela o relógio (horário de Campo Grande); registros posteriores à data somem |
| `--script arquivo.yaml` | roda falas do cliente roteirizadas, sem digitar |
| `--export conversa.md` | salva a conversa em Markdown, incluindo as ferramentas consultadas |
| `--model provider:modelo` | sobrescreve `MODEL` |

**Outros provedores.** O modelo é carregado com `init_chat_model` do LangChain, então basta trocar `MODEL` e instalar o pacote do provedor, por exemplo `uv add langchain-openai` e `MODEL=openai:<modelo>`, ou `uv add langchain-ollama` e `MODEL=ollama:qwen3:8b` para rodar local. Os pacotes do Gemini (`langchain-google-genai`) e do Claude (`langchain-anthropic`) já vêm instalados; os exemplos e os cenários foram rodados com o Gemini.

Sem `MODEL` configurado o CLI para com uma mensagem clara (não existe modelo padrão escondido no código).

**Comandos de desenvolvimento:**

```bash
uv run pytest                             # 221 testes, nenhum chama LLM
uv run ruff check . && uv run ruff format --check .
uv run emporio-evals --report evals/report.md   # cenários com o modelo real (gasta API)
```

## Exemplos de conversa

Os roteiros ficam em [`examples/scripts/`](examples/scripts) e as conversas são **geradas rodando o agente real**:

```bash
for f in examples/scripts/*.yaml; do
  uv run emporio-agent --script "$f" --export "examples/$(basename "${f%.yaml}").md"
done
```

| Conversa | Quando | Cenário | O que demonstra |
|---|---|---|---|
| [`01_violoes_ate_1000`](examples/01_violoes_ate_1000.md) | terça, 10h30 (loja aberta) | "Quais opções de violões disponíveis custando até R$1000?" | busca só entre itens disponíveis (o sem estoque e o descontinuado ficam de fora), item que só cabe no orçamento no PIX, refinamento por corda, parcelamento pela seção 3.1, frete grátis em Campo Grande |
| [`02_takamine_promocao_acessorios`](examples/02_takamine_promocao_acessorios.md) | sábado, 15h (loja fechada) | "Quanto custa o Takamine GD20?" | preço, PIX e parcelas; promoção de 12% encerrada tratada com transparência (7.3); recusa de cordas e amplificador sem indicar outra loja; com a loja fechada, o agente atende e avisa quando a equipe volta (7.1) |
| [`03_arrependimento_devolucao`](examples/03_arrependimento_devolucao.md) | sexta, 10h (loja aberta) | "Me arrependi da minha compra, posso devolver meu pedido?" | verificação de identidade, prazo de arrependimento calculado (pedido recebido três dias antes), condições da 4.1, confirmação da data de recebimento e chamado de devolução |
| [`04_status_pedido_email_compartilhado`](examples/04_status_pedido_email_compartilhado.md) | segunda, 14h30 (loja aberta) | status de pedido com e-mail usado por dois clientes | verificação pela combinação de dados (o e-mail sozinho não basta), pedido confirmado há cinco dias e ainda sem envio, sem inventar data de entrega |
| [`05_endereco_horario_saxofone`](examples/05_endereco_horario_saxofone.md) | terça, 10h (loja aberta) | **três perguntas numa só mensagem:** endereço, feriado de 20/11 e saxofone | uma fonte para cada pergunta (manual, calendário e catálogo) consultadas juntas e respondidas na ordem; categoria sem itens tratada como interesse, não como fora do escopo; chamado aberto depois da confirmação |

Cada arquivo registra no cabeçalho o modelo, a data, o commit e o relógio usado, e mostra as ferramentas consultadas em cada resposta (blocos recolhíveis com a entrada e a saída de cada chamada).

**Datas e horários dos exemplos:** cada roteiro fixa a data e a hora da conversa (campo `now`, o mesmo `--now` do CLI), e registros posteriores a essa data ficam ocultos. Quatro conversas acontecem com a loja aberta e uma num sábado à tarde, com a loja fechada, para mostrar o aviso de quando a equipe volta. Os exemplos com pedidos ficam em fevereiro e março de 2026, quando os pedidos da base ainda são recentes; com o relógio real, todos estariam atrasados e todo prazo de devolução vencido — o agente também lida com isso (o cenário `arrependimento_prazo_vencido` em `evals/` cobre esse caso).

## Arquitetura

```text
            ┌──────────── LangGraph StateGraph ────────────┐
 cliente ──▶│ agent (LLM + prompt da persona)               │──▶ resposta
            │   │  tool calls?                              │
            │   ▼                                           │
            │ ToolNode ──▶ ferramentas tipadas (Python puro)│
            └───────────────────┬───────────────────────────┘
                                │ estado: mensagens, cliente verificado, falhas de verificação
                                ▼
   data/*.csv (lidos 1x, somente leitura)   data/policies.md   .state/tickets.jsonl
```

| Ferramenta | Fonte | Para quê |
|---|---|---|
| `search_catalog` | CSVs | instrumentos **disponíveis** por categoria, faixa de preço, corda, eletroacústico |
| `get_product` | CSVs | um produto em qualquer situação, com alternativas, alertas de cadastro e promoções encerradas |
| `quote` | CSVs + regras | orçamento por **id de produto**: promoção, PIX, parcelas, frete |
| `consult_policy` | `policies.md` | seções inteiras do manual por tópico (8 tópicos fixos) |
| `check_store_hours` | relógio + feriados | aberto agora? e num dia específico (domingos e feriados nacionais/MS) |
| `verify_customer` | CSVs | identidade com 2 de 3 dados; devolve os pedidos se der certo |
| `get_my_orders` | CSVs + estado | pedidos do cliente verificado, com alertas de atraso |
| `check_return` | CSVs + regras | elegibilidade de devolução/troca/garantia hoje |
| `open_ticket` | `.state/` | chamado com protocolo para a equipe humana |

Código em [`src/emporio_agent/`](src/emporio_agent): `data.py` (carga tipada), `rules.py` (regras de negócio), `catalog.py`, `orders.py`, `returns.py`, `policy.py`, `clock.py`, `tickets.py`, `tools.py`, `prompts.py`, `graph.py`, `llm.py`, `cli.py`, `evals.py`.

**Organização do repositório**

| Caminho | Conteúdo |
|---|---|
| [`src/emporio_agent/`](src/emporio_agent), [`tests/`](tests) | o agente e os testes unitários |
| [`examples/`](examples) | as 5 conversas de exemplo e os roteiros que as geram |
| [`evals/`](evals) | os cenários roteirizados (regressão e difíceis) e os relatórios das rodadas |
| [`data/`](data) | as entradas do desafio (CSVs, manual, enunciado) e o `policies.md` curado |
| [`AI_USAGE.md`](AI_USAGE.md) | como usei os assistentes de código, fase a fase |
| [`reports/`](reports) | a auditoria externa (00–03) e a resposta a cada achado (04) |
| [`docs/`](docs) | o plano original, a revisão do plano e o documento de passagem entre sessões |
| [`scripts/`](scripts) | a EDA e os scripts que reproduzem os números citados na documentação |
| [`CLAUDE.md`](CLAUDE.md) | contexto do repositório para o Claude Code |

## Decisões técnicas e justificativas

### Abordagem: function calling com ferramentas de domínio (não text-to-SQL, não RAG vetorial)

O agente é um laço ReAct simples: o modelo decide chamar ferramentas, o código executa e o modelo redige a resposta. Toda conta (desconto, PIX, parcelas, frete, prazos) é feita em Python determinístico; o modelo só escolhe **qual** ferramenta e com **quais ids**.

- **Por que não text-to-SQL:** os clientes são externos e a base tem dados pessoais. Com ferramentas fechadas não existe consulta que liste clientes, e regras implícitas (só promoção com `is_active = 1`, disponível = `active` **e** estoque > 0) ficam no código em vez de depender do modelo lembrar delas.
- **Ferramentas recebem ids, nunca valores digitados pelo modelo.** O `quote` busca o preço sozinho; isso fecha o canal mais comum de alucinação (um preço inventado entrando na conta) e permite carrinhos mistos (item em promoção + item sem promoção no PIX).
- **Saídas pré-formatadas** (`R$ 1.967,18`, `17/02/2026`): o modelo copia, não formata nem arredonda.

### Framework: LangGraph

Um `StateGraph` com um nó de modelo e um `ToolNode`. O LangGraph dá o laço de ferramentas pronto, chamadas paralelas, checkpoint de conversa e — o motivo principal — **estado do servidor fora do alcance do modelo**: o cliente verificado é gravado só pela ferramenta de verificação (`Command(update=...)`) e lido pelas ferramentas de pedido via `InjectedState`. O modelo nunca recebe um parâmetro `customer_id` para preencher.

Antes de depender disso, um *spike* na versão instalada (`langgraph 1.2.19`) confirmou dois comportamentos que mudaram o desenho:
1. uma ferramenta que devolve `Command` precisa incluir o `ToolMessage`, senão o grafo levanta erro;
2. chamadas paralelas no mesmo passo veem o estado **anterior** ao passo — então "verificar + listar pedidos" em paralelo falharia. Por isso `verify_customer` já devolve os pedidos quando a verificação dá certo, e só a primeira verificação de cada passo é processada (chutes paralelos não furam o limite de tentativas).

### Modelo e provedor

O provedor é configurado por uma variável (`MODEL=provider:modelo`) via `init_chat_model` do LangChain; trocar de provedor é configuração, não código, e não existe modelo padrão escondido (os IDs mudam: os do plano original, Haiku 3.5 e Sonnet 4, já foram aposentados).

Os exemplos e os cenários deste repositório rodaram com o **Gemini 3.5 Flash** (`google_genai:gemini-3.5-flash`, chave do Google AI Studio) **porque era a chave que eu tinha à mão no prazo — não é a escolha de produção.** Em produção eu usaria **AWS Bedrock ou um modelo local**, pela privacidade dos dados dos clientes; isso e o que mais mudaria estão em [O que mudaria em produção](#o-que-mudaria-em-produção). Para o protótipo:
- um modelo da linha "Flash" basta: toda conta é feita no código, então o modelo só precisa escolher ferramentas, preencher argumentos e redigir em português — e responde rápido e barato, o que importa num atendimento por mensagem;
- uso uma versão **datada e estável**, não um alias `-latest` (que muda sem aviso e tornaria os exemplos irreproduzíveis). Na hora de gerar os exemplos, os Flash mais novos (3.7 e 3.8) respondiam 503 por alta demanda;
- trocar de modelo é trocar a variável: o Claude (`anthropic:claude-sonnet-5-5`, ou `claude-haiku-5-5` para custo menor) já vem instalado e o formato da requisição foi validado offline, mas os exemplos não foram gerados com ele.

Detalhes que importam com os modelos atuais: **não envio `temperature`** (os Claude 5.x rejeitam valores diferentes do padrão e o Google recomenda manter o padrão nos Gemini 3; o wrapper do Gemini não envia temperatura para Gemini 3+ quando ela não é definida) nem `tool_choice` forçado; `MODEL_EFFORT` controla o "pensamento" padrão dos Claude 5.x (para chat, `low` costuma bastar); com Claude, o prompt estático é marcado para **prompt caching**.

### Políticas: arquivo curado + consulta por tópico (sem embeddings, sem BM25)

O manual tem 8 páginas. Testei a ideia do plano original (SQLite FTS5/BM25 por seção) e ela **não devolve nada** para a pergunta do próprio enunciado — "Me arrependi da minha compra, posso devolver meu pedido?" —, porque o manual só usa "devolução" e "arrependimento" e o FTS5 não tem *stemming* em português ([`scripts/review_checks/fts5_policy_probe.py`](scripts/review_checks/fts5_policy_probe.py) reproduz).

Então:
- [`data/policies.md`](data/policies.md) tem o texto do manual **literal**, dividido em 8 tópicos, mais um bloco separado de **notas de interpretação** (as contradições do manual e como resolvi). Um teste com `pypdf` confere linha a linha que o texto curado está no PDF.
- `consult_policy(topics=[...])` recebe tópicos de uma lista fixa (`pagamento`, `trocas_devolucoes`...) e devolve as seções inteiras. O índice dos tópicos está no prompt.
- As seções 7 (diretrizes de atendimento) e 10 (consultar a gerência em caso de dúvida) são instruções para quem atende, então foram para o **prompt de sistema**, não para a ferramenta.

Alternativa considerada: colocar o manual inteiro no prompt (cabe folgado e ficaria em cache). Preferi a ferramenta porque o enunciado avalia justamente *saber quando consultar políticas*, e assim essa decisão aparece no trace e pode ser testada. Com um corpus grande, o próximo passo seria busca híbrida; aqui seria complexidade sem ganho.

### Estratégia de prompt

- Prompt de sistema em português, com a persona (seção 7.1), o fluxo de atendimento (7.2), as situações especiais (7.3) e regras explícitas: nunca afirmar preço/estoque/prazo sem ferramenta, copiar valores das ferramentas, não negociar preço, não citar loja parceira (o manual não lista nenhuma e o modelo inventaria), vocabulário (*guitarra* é elétrica, *violão* é acústico, *contrabaixo* é ambíguo), estilo WhatsApp (curto, sem tabelas, 3–5 opções e uma pergunta para afunilar).
- **Várias perguntas na mesma mensagem:** responder cada uma, na ordem; numa reclamação com várias queixas, todas entram no resumo do chamado. **Fora do expediente,** o agente continua ajudando e avisa uma vez quando a equipe humana volta (seção 7.1).
- **Estático primeiro, dinâmico por último:** data/hora, se a loja está aberta, feriado e status da verificação entram no fim, para não invalidar o cache a cada mensagem.
- As ferramentas carregam instruções nos próprios dados quando isso é mais confiável que o prompt: `promocoes_encerradas` vem com "só mencione se o cliente perguntar", `alerta_dados` diz para não afirmar a marca da descrição, `categoria_sem_itens` diz que não é fora do escopo.

### Interface: CLI

O enunciado diz que o foco é o agente funcionando. O CLI tem `--trace` (mostra as ferramentas), `--now` (relógio congelado para demonstrações) e exporta a conversa em Markdown **com as chamadas de ferramenta**, que é o que gera os exemplos. Uma UI web ficou para depois (ver próximos passos).

### Persistência do histórico

`InMemorySaver` do LangGraph: o histórico vale durante a sessão do CLI, que é o que a experiência de chat precisa. Persistir em disco (`SqliteSaver`) é uma linha, mas grava dados pessoais depois da verificação — então só faz sentido com uma política de retenção (LGPD). Os chamados são gravados em `.state/tickets.jsonl`, fora do git.

### Tratamento dos dados

Os CSVs ficam **intactos** em `data/` e são carregados uma vez, na inicialização, em objetos tipados e imutáveis (65 produtos e 20 pedidos cabem em memória; não precisa banco nem passo de build). Regras aplicadas na leitura/consulta:
- dinheiro em `Decimal`, arredondamento **comercial (ROUND_HALF_UP) por linha** — com `float`, 8 preços no PIX sairiam um centavo abaixo (ex.: Yamaha C40: R$ 569,91, não R$ 569,90); BRL formatado à mão, sem `locale`;
- disponibilidade como enum: `disponível` só se `active` e estoque > 0; `discontinued` vence o estoque (o Ibanez Bass 2X tem 13 unidades mas saiu de linha); `coming_soon` é "em breve", nunca pré-venda;
- **alertas de cadastro por regra**: 7 produtos (135, 136, 137, 139, 140, 142, 144) têm descrição citando outra marca/modelo ou especificação diferente da ficha técnica; o agente não afirma esses dados e oferece confirmar com um especialista;
- alternativas calculadas (mesma categoria, mesmo tipo de corda, preço mais próximo) — escolhidas à mão, o plano original indicou um violão de aço como alternativa a um de nylon;
- `customers.csv` só é usado para verificação; o agente vê apenas o primeiro nome.

### Relógio

Um único `now()` injetável em `America/Campo_Grande`, com tempo real por padrão. Hoje todos os pedidos têm 7 a 13 meses, então os prazos de devolução estão vencidos — e o agente lida com isso (pedido atrasado: desculpas, rastreio e chamado; pedido parado: chamado sem prometer prazo). Para demonstrar um prazo ainda aberto, `--now` congela o relógio **e esconde registros posteriores** (o plano original sugeria voltar para 22/02/2026, o que exibiria 8 pedidos "do futuro"). Feriados nacionais e de MS vêm do pacote `holidays`.

### Verificação de identidade (LGPD)

Dois de três dados (número do pedido, e-mail, telefone), conferidos **como combinação**: o e-mail `bruno.martins@jmail.com` pertence a dois clientes (11 e 43), e uma implementação ingênua ("acha o cliente pelo e-mail, depois compara o resto") ligaria a pessoa errada. Mensagens de falha são genéricas (não dizem qual dado errou), há limite de 3 tentativas por conversa e nome nunca é usado como fator. Em produção, o número do WhatsApp do remetente seria o fator natural de posse.

### Atendimento humano: chamados

O manual manda encaminhar para pessoas em vários casos — reclamação (retorno em até 24 horas úteis), dúvida sobre como aplicar uma política (gerência), exclusão de dados. Por isso o agente tem uma ferramenta própria, `open_ticket`, que registra devolução, troca, garantia, cancelamento, reclamação, interesse em produto sem estoque, pedido de LGPD ou pedido de atendente e devolve um protocolo. Ela só é chamada depois que o cliente confirma o resumo; vincular um pedido ou pedir exclusão de dados exige cliente verificado; e só a reclamação vem com prazo, porque é o único prazo que o manual dá. No protótipo os chamados vão para `.state/tickets.jsonl` (fora do git); em produção, para o sistema de atendimento da loja.

### Avaliação: checagens em código antes de um LLM juiz

Para um agente que fala de preço e prazo, os erros que importam são objetivos: um valor errado, uma ferramenta que não foi consultada, um dado pessoal exposto. Por isso a avaliação é feita por código — testes unitários com modelo falso para as regras e o grafo, e cenários roteirizados contra o modelo real, que conferem as ferramentas chamadas, termos proibidos ou obrigatórios e a origem de todo valor em R$. Um LLM juiz ficou de fora: os modelos atuais rejeitam `temperature`, e um juiz precisaria primeiro ser validado contra conversas rotuladas à mão. Em compensação, todas as transcrições foram lidas — foi assim que apareceram problemas que nenhuma checagem pegava. Resultados em [Testes e avaliação](#testes-e-avaliação).

## Suposições

Onde o enunciado, o manual ou os dados são ambíguos, assumi uma interpretação razoável e segui em frente, como o enunciado pede. O código cita a suposição onde ela é aplicada.

**Sobre o enunciado**

- **A. Quem o agente atende:** o enunciado fala em um agente que vai "auxiliar a equipe". Interpretei como um assistente que conversa direto com o cliente pelo canal de mensagens (o WhatsApp da seção 7 do manual) e passa para a equipe, por chamados, o que precisa de uma pessoa — não como uma ferramenta interna para os atendentes.
- **B. Identificação do cliente:** o enunciado não diz como o cliente se identifica. Como um canal de mensagens não tem login, a conversa começa anônima e dados de pedido só aparecem depois da verificação por dois dados (número do pedido, e-mail, telefone).
- **C. Idioma:** respostas sempre em português do Brasil, mesmo quando o cliente escreve em outra língua — a loja e o canal são brasileiros.
- **D. Data de "hoje":** os pedidos vão de outubro/2025 a março/2026 e o agente usa a data real, então os prazos de devolução estão todos vencidos. Os exemplos usam datas e horários fixos, declarados no cabeçalho de cada um, para mostrar a loja aberta e fechada e pedidos ainda dentro do prazo.
- **E. Equipe e chamados:** os materiais não incluem um sistema de atendimento. O que precisa de pessoa vira um chamado com protocolo num arquivo local, e o agente não promete prazos que o manual não dá.
- **F. Uso dos dados:** o enunciado permite não usar todos os dados. Clientes e pedidos só servem para verificação e consulta de pedidos, e a descrição dos produtos com cadastro inconsistente não é usada (suposição 15).

**Sobre o manual e os dados**

1. **E-mail da loja:** o manual escreve `contato@emporiodamusica.com.br` (capa) e `contato@empóriodamusica.com.br` (1.2); uso a versão sem acento.
2. **Dois telefones:** (67) 3341-4444 é o telefone da loja e (67) 3321-4500 é o WhatsApp de atendimento (seção 7).
3. **Parcelamento:** valem as faixas da seção 3.1 (até 3x: parcela ≥ R$ 50; 4–6x: ≥ R$ 80; 7–12x: ≥ R$ 100), não o "parcela mínima R$ 100" da tabela da seção 3. Isso muda a resposta para **15 dos 61 itens à venda** (todos abaixo de R$ 600), então precisa de confirmação da loja. O primeiro item da 3.1 é ambíguo, mas dá o mesmo resultado para todo o catálogo atual.
4. **Frete grátis** considera o valor efetivamente pago (depois de promoção e PIX), e exatamente R$ 500,00 é grátis. Só Campo Grande conta como região metropolitana até a loja confirmar a lista; outras cidades: "calculado pelo CEP", nunca um valor inventado.
5. **Frete especial (5.2):** baterias acústicas e o piano de palco; "contrabaixos" de grande porte são os acústicos, baixos elétricos seguem o frete normal.
6. **PIX em pagamento combinado** (acima de R$ 2.000): o manual não diz se a parte em PIX tem desconto; o agente não calcula e encaminha.
7. **Promoções:** só linhas com `is_active = 1` valem. As campanhas da 6.1 (Black Friday etc.) são calendário, não desconto vigente.
8. **Pedidos do sistema são compras online**, então vale o arrependimento da 4.1. A **data de recebimento** é a previsão de entrega registrada, salvo se o cliente informar outra. O dia do recebimento é o dia 0.
9. A **troca por preferência** (4.3, "7 dias") conta a partir do recebimento.
10. **Defeito:** até 30 dias da compra, troca direta (4.2); depois, garantia legal de 90 dias do recebimento (8.1) e garantia do fabricante (8.2), com intermediação da loja.
11. **Não existe política de cancelamento:** pedido ainda não recebido que o cliente quer desistir vira chamado de cancelamento, sem promessa de resultado.
12. **Prazos de retorno:** só reclamações têm prazo no manual (24 horas úteis); os demais chamados não prometem prazo.
13. **Lojas parceiras:** o manual não lista nenhuma, então o agente não indica nenhuma.
14. **`coming_soon`** = "em breve, sem pronta entrega"; não existe pré-venda.
15. **Cadastro inconsistente** (produtos 135–144): nome e preço valem; marca/especificação da descrição não são afirmadas.
16. **`customers.city` pode não ser o endereço de entrega** (pedidos de Campo Grande têm prazos e rastreio de Correios); para pedidos existentes, rastreio e previsão são informados como registrados.
17. **Totais de pedidos antigos** são informados como registrados, sem recalcular com as regras atuais (alguns pedidos antigos violam a 3.1 ou têm totais menores que o preço de tabela).
18. **Relógio:** tempo real em `America/Campo_Grande`, com feriados nacionais e de MS (nomes sempre em português, independentemente do idioma do sistema).
19. **Dias incertos:** Carnaval, Quarta-feira de Cinzas, Corpus Christi, vésperas de Natal e Ano-Novo e os feriados municipais de Campo Grande (13/06, Santo Antônio, e 26/08, aniversário da cidade) são informados com o horário normal e o aviso de que a loja confirma.
20. **Data de recebimento informada pelo cliente:** se ficar mais de 10 dias depois da previsão registrada, a equipe confirma a entrega pelo rastreio antes de qualquer prazo ser aplicado (uma data digitada não reabre um pedido antigo).
21. **Exceções da seção 4.4** (personalização, "venda final", boquilhas) valem para trocas; o direito de arrependimento da compra online (4.1) não tem essas exceções.
22. **Pedido de exclusão de dados (LGPD)** só é registrado para o próprio titular, depois da verificação de identidade.

## Testes e avaliação

- **221 testes unitários** (`uv run pytest`, ~2 s, sem LLM, também com o sistema em inglês): preços e promoções fixados nos valores conferidos à mão (Takamine GD20: R$ 2.199,00 / PIX R$ 2.089,05 / 12x R$ 183,25; os 12 violões até R$ 1.000; os 8 casos de meio centavo), parcelas, frete, disponibilidade, alertas de cadastro, fidelidade do `policies.md` ao PDF, feriados, verificação (colisão de e-mail, bloqueio após 3 tentativas, chutes paralelos), prazos de devolução nas bordas, chamados. O grafo do LangGraph é testado de ponta a ponta com um **modelo falso roteirizado**.
- **Cenários roteirizados** (`uv run emporio-evals`, [`evals/scenarios.yaml`](evals/scenarios.yaml)): 24 conversas com o modelo real — as 4 do enunciado e casos difíceis (guitarra × violão, contrabaixo acústico, saxofone, acessórios, pedido de desconto, Black Friday, cadastro inconsistente, injeção de prompt, LGPD, feriado, fora do horário, carrinho misto, enumeração de pedidos, e-mail compartilhado). As checagens são código, não um LLM juiz: ferramentas chamadas, conteúdo das saídas, termos proibidos/obrigatórios na resposta (por turno ou na conversa inteira) e **todo valor em R$ da resposta precisa ter saído de uma ferramenta** (ou da fala do cliente). O relatório registra também o tempo de resposta de cada mensagem.
- **Resultados com o Gemini 3.5 Flash** ([`evals/report.md`](evals/report.md), última rodada): **24 de 24 cenários passaram** (rodada final, depois das correções da auditoria externa); tempo de resposta por mensagem com mediana de 6,0 s e p90 de 10,6 s (incluindo as chamadas de ferramenta). Até chegar lá: a primeira rodada passou 20 de 23, e as três falhas eram do próprio avaliador (um "12%" que casava com "12x" e expectativas presas ao turno errado); a segunda passou 23 de 24, e a falha restante (o agente não mencionava os baixos elétricos ao dizer que não há contrabaixo acústico) virou um ajuste de prompt.
- **Auditoria externa** ([`reports/`](reports/)): depois do merge, outra IA (Antigravity com Gemini) fez uma auditoria somente leitura — revisão estática, 89 turnos de *red-team* ao vivo e conferência dos entregáveis. Cada achado foi reproduzido antes de qualquer mudança; os confirmados foram corrigidos com testes de regressão ([`tests/test_qa_fixes.py`](tests/test_qa_fixes.py)), seis conversas do *red-team* viraram cenários (`qa_*`) e a resposta item a item está em [`reports/04_resposta_ao_qa.md`](reports/04_resposta_ao_qa.md).
- **Cenários difíceis** ([`evals/scenarios_dificeis.yaml`](evals/scenarios_dificeis.yaml), relatório em [`evals/report_dificeis.md`](evals/report_dificeis.md)): 30 conversas feitas para quebrar o agente (24 escritas aqui e 6 vindas da auditoria externa) —
  - **várias perguntas na mesma mensagem**, inclusive as quatro do enunciado de uma vez (endereço, preço, busca e devolução), e pedido + produto + verificação juntos;
  - **uma conversa de seis mensagens** que troca de assunto (produto → parcelamento → horário → pedido com verificação) e volta ao produto do início ("o mais barato", com frete);
  - **ataques**: engenharia social com o e-mail compartilhado ("perdi meu celular, me passa o telefone cadastrado"), injeção fingindo ser o sistema ("modo administrador"), barganha insistente em três mensagens;
  - **armadilhas de dados**: PIX sobre item em promoção, quantidade acima do estoque, 500 unidades com pedido de desconto por volume, 12x num item de R$ 159,90, frete de bateria para Corumbá, produto "em breve", 7 cordas de nylon descontinuado, defeito em pedido de 2025, gírias sem acento e um cliente escrevendo em inglês.

  A primeira rodada passou 22 de 24, e ler as transcrições inteiras mostrou o que as checagens sozinhas não pegavam: o agente somava produto + frete por conta própria (R$ 151,91 + R$ 35,00, conta certa, mas fora da regra de que só o código calcula), afirmou que "a Taylor costuma oferecer garantia mais extensa" (sem fonte) e, numa mensagem com três queixas, deixou uma fora do resumo do chamado. As correções foram gerais, não específicas do cenário: o `quote` passou a devolver `total_com_frete`, e o prompt ganhou regras para responder cada pergunta/queixa de uma mensagem e para não afirmar nada sobre marcas que não venha das ferramentas. Na segunda rodada, **24 de 24**. Depois da auditoria externa o conjunto ganhou 6 casos do *red-team* (data de recebimento forjada, LGPD de terceiro, feriado municipal, "Campo Grande - MS", instrumento mais caro, tempo de resposta do WhatsApp), e a rodada final no código corrigido passou **30 de 30** (mediana de 7,9 s por mensagem).

As respostas de um LLM variam entre execuções: cada rodada é uma amostra, não uma garantia. Os relatórios trazem as conversas completas para conferir o comportamento, não só o placar.

## Limitações e próximos passos

**Limitações conhecidas**
- Os exemplos e os cenários rodaram com um único modelo (Gemini 3.5 Flash). As respostas variam de uma execução para outra, e outro modelo pode pedir ajustes no prompt.
- Histórico só em memória: fechar o CLI perde a conversa. Não há corte de histórico para conversas muito longas.
- A base não tem endereço de entrega, canal de compra (online/loja) nem data real de entrega; as regras de devolução usam as suposições 8 e 16.
- Horários estendidos de datas especiais não estão na base, e os dias incertos (pontos facultativos e feriados municipais) só recebem um aviso para confirmar com a loja.
- Algumas regras de segurança ainda dependem do prompt, não do código: pedir confirmação antes de abrir um chamado e não trocar de cliente verificado no meio da conversa. Outros pontos conhecidos (pagamento combinado PIX + cartão, crescimento do histórico, trava do arquivo de chamados entre processos, limites do verificador de valores) estão listados em [`reports/04_resposta_ao_qa.md`](reports/04_resposta_ao_qa.md).
- A busca por nome é por correspondência de texto (tolera acento, hífen e espaço, ex. "takamine gd 20"), não semântica: "violão bom para fingerstyle" depende do modelo traduzir para filtros.
- Os chamados vão para um arquivo local; não há integração com um sistema de atendimento real.
- A verificação conversacional é fraca por natureza (e-mail e número de pedido são semi-públicos); o limite de tentativas reduz, não elimina, o risco.

**Com mais tempo**
1. Rodar os cenários várias vezes e com outros modelos (Claude Haiku/Sonnet, Gemini Pro) para medir taxa de acerto (pass^k) e latência, e ajustar o prompt pelos erros.
2. Levar para produção o que está na seção seguinte (modelo na AWS ou local, WhatsApp, banco de dados, sistema de chamados, segurança e observabilidade).
3. Uma interface web: há um protótipo com Gradio e um com conversas que persistem entre sessões em ramos opcionais (`feat/web-ui-gradio`, `feat/persistencia-sqlite`), que precisam dos ajustes apontados na auditoria antes de entrar.
4. LLM como juiz só para tom/empatia, validado contra conversas rotuladas à mão, com um modelo diferente do agente.
5. Confirmar com a loja as suposições 3, 4, 8 e 11 (são as que mudam respostas).

## O que mudaria em produção

Este repositório é um protótipo para o desafio. Algumas escolhas foram feitas pelo prazo ou pelo que eu tinha à mão; num ambiente de produção elas seriam diferentes:

| Tema | No protótipo | Em produção |
|---|---|---|
| **Modelo e provedor** | Gemini 3.5 Flash pela API do Google AI Studio — era a chave disponível no prazo | **AWS Bedrock** (Claude ou outro modelo do catálogo, com IAM, rede privada e logs na conta da empresa) **ou um modelo local** (Ollama/vLLM em servidor próprio, com os dados sem sair da infraestrutura da loja) — a direção do plano original, por privacidade e LGPD. Na AWS, a região importa: se a inferência acontecer fora do Brasil, a transferência internacional de dados precisa de base legal (LGPD, art. 33). No código, é trocar `MODEL` e instalar o pacote do provedor (`langchain-aws` ou `langchain-ollama`); antes, os dois conjuntos de cenários rodariam no modelo escolhido, já que modelos locais menores tendem a errar mais chamadas de ferramenta em português |
| **Canal** | CLI no terminal | WhatsApp Business (API oficial, via *webhook*); o número do remetente vira o identificador da conversa e um fator de posse na verificação |
| **Dados** | CSVs carregados em memória | Consultas somente leitura ao ERP/banco da loja, com credencial de serviço de privilégio mínimo; preço e estoque em tempo real |
| **Histórico e verificação** | Em memória, durante a sessão | Conversas em banco (ex.: Postgres) por número de telefone, verificação que expira, política de retenção e exclusão (LGPD) e resumo de conversas longas |
| **Chamados** | Arquivo `.state/tickets.jsonl` | Integração com o sistema de atendimento (helpdesk/CRM), com fila, notificação da equipe e prazos de retorno reais |
| **Segurança** | Chave em `.env`; algumas regras só no prompt | Segredos num cofre (ex.: AWS Secrets Manager); limite de mensagens por número; as regras que hoje dependem do prompt (confirmar antes de abrir chamado, não trocar de cliente verificado) passam para o código; código de verificação real por SMS/e-mail para operações sensíveis |
| **Operação** | Logs no terminal (`--trace`) | Rastreamento de cada chamada de ferramenta, latência e custo por conversa (ex.: OpenTelemetry/LangSmith), *timeouts*, modelo de reserva se o provedor cair e *cache* de prompt |
| **Qualidade** | Cenários rodados à mão, uma vez por mudança | Cenários no CI a cada mudança de prompt ou de modelo, várias execuções por cenário (*pass^k*), e uma amostra de conversas reais revisada por pessoas |
| **Informação da loja** | Avisos genéricos para feriados municipais, horários especiais e frete fora de Campo Grande | Calendário da loja e cotação de frete por CEP (Correios/Jadlog) vindos das fontes reais |

## Uso de assistentes de código

Usei dois assistentes em fases alternadas — usando um para auditar o trabalho do outro — e mantive comigo as decisões de escopo, arquitetura e *merge*. O registro detalhado e cronológico (em inglês) está em [`AI_USAGE.md`](AI_USAGE.md). O [`CLAUDE.md`](CLAUDE.md), gerado com o `/init` do Claude Code, serviu de contexto comum para os dois assistentes (restrições do enunciado, esquema dos dados, armadilhas conhecidas).

1. **Planejamento com o Antigravity** (ambiente agêntico do Google DeepMind):
   - **dados antes de código:** uma EDA forense ([`scripts/explore_data.py`](scripts/explore_data.py)) cruzou os 6 CSVs com o manual e encontrou as armadilhas da base — a promoção expirada do Takamine GD20, o violão ativo sem estoque, o baixo descontinuado com estoque, o item que só cabe em R$ 1.000 no PIX, o e-mail compartilhado por dois clientes e as contradições internas do PDF;
   - **plano discutido decisão por decisão** (`/grill-me`; [`PLAN.md`](docs/PLAN.md), com revisão de literatura), em que troquei várias sugestões iniciais da IA por decisões minhas: LangGraph no lugar de PydanticAI; privacidade dos dados com modelo local (Ollama na GPU) + AWS Bedrock no lugar de APIs públicas; uma interface web pensada para o cliente; login com código (OTP simulado) além da verificação 2-de-3; relógio real com *override* explícito no lugar de uma data fixa no passado. Parte dessas decisões mudou depois da revisão do passo 2, por motivos que estão na tabela abaixo.
2. **Revisão adversarial com o Claude Code** (CLI, local): pedi que ele tentasse **derrubar o meu plano com scripts reproduzíveis** em vez de só comentá-lo ([`Plan_Review.md`](docs/Plan_Review.md), [`scripts/review_checks/`](scripts/review_checks)). Ele confirmou a EDA e encontrou problemas reais: a busca FTS5 planejada não achava a pergunta do próprio enunciado, os IDs de modelo do plano estavam aposentados e `temperature=0` é rejeitado pelos modelos atuais, `float` e `Decimal` divergiam em um centavo em 8 preços no PIX, a data de referência sugerida exporia 8 pedidos "do futuro", uma sétima inconsistência de cadastro (ID 136) e uma alternativa de corda de nylon trocada por aço. Também conferiu as citações do plano na web: uma estava com o ano e o tema errados, e outras sustentavam afirmações que as fontes não fazem. Em seguida preparou um documento de passagem ([`HANDOFF.md`](docs/HANDOFF.md)) com decisões padrão — reversíveis e sinalizadas — onde plano e revisão discordavam.
3. **Implementação com o Claude Code** (sessão na nuvem), seguindo o `HANDOFF.md` em commits pequenos: cada regra veio com testes fixados em valores conferidos à mão, e os comportamentos do LangGraph que o desenho usa foram confirmados num *spike* na versão instalada antes de o código depender deles. As decisões continuaram comigo: o ritmo (parar depois da estrutura, depois seguir), o provedor dos testes reais (Gemini, a chave disponível no prazo), o que fica no ramo de entrega e o que fica em ramos opcionais (persistência e chat web) e o pedido de cenários mais difíceis, com várias perguntas na mesma mensagem.
4. **Conversas reais e correções:** as primeiras transcrições com o Gemini mostraram problemas que os testes com modelo falso não pegam — o modelo inventava detalhes de produto (ex.: "tarraxas douradas" num violão cuja descrição não diz isso), afirmava a previsão de entrega como data de recebimento e, depois de um feriado, dizia vagamente que a loja "volta ao normal no dia seguinte". A correção foi nas ferramentas e no prompt (commit `2d65a27`): a busca passou a trazer a descrição do catálogo, o prompt limita afirmações de produto ao que as ferramentas devolvem e exige confirmar a data de recebimento, e o horário de um dia fechado passou a informar a próxima abertura. Os exemplos foram gerados de novo. Depois, os 24 cenários difíceis acharam mais três problemas — o modelo somava produto + frete por conta própria, afirmou sem fonte que uma marca "costuma oferecer garantia mais extensa" e esqueceu uma queixa num chamado — também corrigidos (commit `16da6fe`); os cenários revelaram ainda alguns erros no próprio avaliador, que foram corrigidos.
5. **Auditoria independente e *red-teaming* multiagente com o Antigravity ([`reports/`](reports/)):** como o mesmo assistente (Claude Code) havia escrito o código e os 48 cenários de avaliação, voltei ao **Antigravity** depois do *merge* no `main` com a instrução explícita de **testar o sistema inteiro, usar múltiplos agentes e não corrigir nada antes de documentar os achados**. Três subagentes rodaram em paralelo sobre a árvore em modo somente leitura (auditoria estática das 16 unidades de código e do PDF, 89 turnos ao vivo de *red-teaming* adversarial e consistência `pass^3` no Gemini 3.5 Flash, e auditoria dos entregáveis e ramos opcionais). Essa verificação cruzada pegou o que o ambiente do primeiro assistente escondia: a dependência implícita de *locale* em `holidays.Brazil` (que quebrava 4 testes em máquinas `en_US.UTF-8`), datas `dd/mm/aa` lidas como ano `0026 d.C.`, *spoofing* de `received_on` aprovando devoluções de pedidos antigos, abertura de chamado LGPD de terceiros sem verificação no 1º turno, a omissão do SLA de 5 minutos (§7.1) do manual, descrições inconsistentes indexadas na busca e uma resposta a pergunta não feita em `examples/03_arrependimento_devolucao.md` — tudo consolidado em [`reports/00_executive_qa_summary.md`](reports/00_executive_qa_summary.md) para triagem humana antes das correções.
6. **Correções a partir da auditoria, com o Claude Code:** pedi que cada achado fosse reproduzido antes de qualquer mudança — os principais se confirmaram todos. Os confirmados foram corrigidos com testes de regressão ([`tests/test_qa_fixes.py`](tests/test_qa_fixes.py)), seis conversas do *red-team* viraram cenários (`qa_*` em [`evals/scenarios_dificeis.yaml`](evals/scenarios_dificeis.yaml)), os exemplos foram gerados de novo, e a resposta item a item — inclusive o que ficou de fora e por quê — está em [`reports/04_resposta_ao_qa.md`](reports/04_resposta_ao_qa.md). Na rodada final, os 221 testes passam (também com o sistema em inglês) e os cenários passam 24 de 24 e 30 de 30.

**O que mudou do plano para a implementação, e por quê** (detalhes nas seções acima e no `Plan_Review.md`):

| No plano | Na implementação | Motivo |
|---|---|---|
| SQLite FTS5/BM25 para as políticas | consulta por tópico sobre um `policies.md` curado | o FTS5 não devolvia nada para "Me arrependi da minha compra..." (sem *stemming* em português) |
| Bedrock como principal + Ollama + fábrica de 4 provedores | provedor configurável por `MODEL` (`init_chat_model`); testes com o Gemini 3.5 Flash | os IDs do plano estavam aposentados, e a chave que eu tinha à mão no prazo era a do Gemini. **Em produção, AWS Bedrock ou um modelo local continuam sendo o alvo** ([O que mudaria em produção](#o-que-mudaria-em-produção)) |
| Web chat FastAPI com gaveta de avaliação + CLI | CLI com `--trace`, `--now` e exportação em Markdown | o enunciado aceita CLI; o tempo foi para o agente e para os testes |
| Login por OTP simulado + verificação 2-de-3 | só a verificação 2-de-3, com limite de tentativas | um código mostrado na tela não protege nada |
| LLM juiz com `temperature=0` | cenários roteirizados com checagens em código | `temperature` é rejeitado; checagens determinísticas são reproduzíveis |
| relógio real + `REFERENCE_DATE` (sugestão: 22/02/2026) | relógio real + `--now`, que esconde os registros posteriores à data | na data sugerida, 8 pedidos apareceriam "do futuro" |

**O que ficou igual:** LangGraph com estado do servidor (`InjectedState`/`Command`), ferramentas tipadas em vez de text-to-SQL, dados somente leitura com chamados à parte, relógio real em `America/Campo_Grande` por padrão.

**Em resumo:** o uso mais valioso da IA foi pedir que ela provasse ou derrubasse as minhas próprias decisões com código — e todo número citado nos documentos tem um script ou teste que o reproduz. Escrever mais plano teria ajudado menos. O escopo, o que aceitar da revisão e quando juntar no `main` ficaram comigo.
