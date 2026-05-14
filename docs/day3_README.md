# Dia 3 — Agent loop single-step

> Integrar tools, LLM e validador num agente que decide e age.

## Objectivo

Construir o **agent loop**: orquestração que recebe uma query do utilizador, decide qual tool chamar (ou se responde directamente), executa a tool, e gera resposta natural com o resultado. Princípio: a integração é onde os bugs reais vivem — componentes isolados podem estar todos correctos e o sistema integrado estar partido.

## Setup

Estrutura criada:

```
src/agent/
├── __init__.py
├── schemas.py     # JSON schemas das 3 tools para Ollama function calling
├── prompts.py     # System prompt + 9 few-shot examples
├── validator.py   # Validador a jusante (numérico + completude)
└── loop.py        # run_agent() — orquestração

experiments/
├── test_set_day3.json          # 15 queries em 5 categorias
├── eval_day3.py                # script de avaliação
├── day3_sanity_check.py        # smoke tests informais
├── day3_v1/                    # eval baseline
└── day3_v3/                    # eval final (após fix de completude)
```

## Componentes

### Schemas das 3 tools

JSON schemas para Ollama function calling, com descriptions desenhadas para **mútua exclusividade**: cada description diz quando usar **e quando NÃO usar** (referenciando as outras tools). Caso especial documentado: vocabulário diferente entre `calculate_tdee` (5 níveis de atividade) e `calculate_macros` (3 perfis), com warning explícito na description.

### System prompt + few-shot

System prompt restritivo com 8 regras numeradas, incluindo:
- Routing entre as 3 tools (regra 8 cirúrgica)
- Anti-hallucination ("NUNCA inventes valores")
- Anti-incompleteness ("Se TODOS os dados estão presentes, CHAMA a ferramenta")

Few-shot com **9 exemplos** distribuídos: 6 positivos (cobrindo as 3 tools com formulações variadas) + 3 negativos (refusal correcto).

### Validador a jusante (2 camadas)

**Camada 1 — Validação numérica:** detecta args numéricos inventados. Compara cada arg numérico com números literalmente presentes na query do utilizador, considerando conversões comuns (m → cm).

**Camada 2 — Validação de completude:** detecta args required ausentes. Lê schema da tool, verifica que todos os campos `required` estão presentes nos args extraídos.

Filosofia: validador é fail-safe explícito. Quando o LLM tem um momento de fragilidade, o validador apanha antes da execução.

### Agent loop

`run_agent(user_query) → AgentResponse`. AgentResponse é objecto rico (texto + metadados) para suportar tanto uso simples (`response.text`) como observabilidade para eval (`tool_used`, `tool_args`, `validation_failed`, `suspicious_args`).

Fluxo: query → LLM (com tools) → ramos:
- texto → devolver
- tool_call → validador numérico → validador completude → conversão tipos → executar tool → LLM (sem tools) → resposta final

Cada ramo termina com `AgentResponse`. **Total path coverage** — sem fugas silenciosas.

## Arco experimental

### Sanity check (informal, 4 queries × 3 execuções)

Antes de eval formal, 4 queries cobrindo os 4 caminhos do agente.

**Descoberta crítica:** `temperature=0.7` (default Ollama) introduz variabilidade fatal para tool calling — mesma query alternava entre acertar e falhar. Aplicar `temperature=0.0` em ambas as chamadas Ollama (decisão e geração de texto final) tornou o sistema determinístico.

**Lição:** `temperature=0` não torna o modelo "melhor" — torna-o **previsivelmente confuso** em vez de **aleatoriamente ocasionalmente certo**. Amplifica sinal bom (queries claras) e mau (queries ambíguas). É desejável para diagnóstico.

### Eval v1 — Baseline

Test set de 15 queries em 5 categorias (tdee_positive, lookup_positive, macros_positive, refusal, general/edge_case).

Resultados:

| Métrica | v1 |
| --- | --- |
| Routing accuracy | 86.7% (13/15) |
| Args validity | 100% (aparente) |
| Refusal accuracy | 100% |
| Validator save rate | 0% |

2 falhas: **A1** (TDEE com estrutura "Tenho X anos..." → modelo escolheu macros e copiou args do exemplo 5 do few-shot), **B3** ("Quanto de fibra tem o pão integral?" → modelo não chamou tool).

### Eval v3 — Pós fix estrutural

Após investigação do baseline, descobriu-se que C2 estava a "passar" args validity por bug de detecção: LLM omitia `perfil_atividade`, tool dava `TypeError`, agent traduzia para "Ocorreu um erro inesperado". Falha visível ao utilizador mas mascarada na métrica.

Implementada **camada 2 do validador (completude)**: verifica args `required` antes de executar tool. C2 passa a ser apanhado estruturalmente — utilizador recebe pergunta amigável ("Para te ajudar, podes dizer-me perfil de atividade?") em vez de erro genérico.

Adicionalmente, definição de `validator_save_rate` corrigida: contava só queries da categoria refusal; agora conta qualquer bloqueio que proteja o utilizador.

Resultados finais:

| Métrica | v1 | v3 | Comentário |
| --- | --- | --- | --- |
| Routing accuracy | 86.7% | 86.7% | Não muda — limitação do modelo |
| Args validity | 100% (ilusório) | **75%** | Reflecte bug exposto, agora honesto |
| Refusal accuracy | 100% | 100% | Estável |
| Validator save rate | 0% | **100%** | Validador apanha **todas** as falhas defensáveis |

## Análise das falhas finais

### A1 — Sensibilidade a estrutura sintáctica

Query: *"Tenho 30 anos, peso 75kg, meço 1.78m, sou homem e faço exercício moderado..."*

Modelo escolhe `calculate_macros` em vez de `calculate_tdee`. Args inventados copiam literalmente o exemplo 5 do few-shot (tdee=2400, objetivo='manter', perfil_atividade='ativo').

Diagnóstico via experimento controlado: reformulação ("Quantas calorias devo comer? Tenho 30 anos...") resolveu o problema. **Causa: modelos pequenos com `temperature=0` fazem match na forma estrutural superficial, não na semântica.** Estrutura "Tenho X..." colide com estrutura do exemplo 5 ("O meu TDEE é..., peso..., sou...").

**Falha defendida:** validador numérico apanhou `tdee=2400` como inventado. Utilizador recebe pergunta amigável em vez de macros calculados sobre TDEE inventado.

**Tentativas de fix por prompt engineering (4 iterações):** rebalanceamento de few-shot (5 positivos vs 3 negativos), regra 8 sobre routing TDEE/macros, regra anti-hallucination explícita. Nenhuma resolveu A1 — sinal claro de **limite estrutural do modelo 3B**.

### B3 — Não generalização entre nutrientes

Query: *"Quanto de fibra tem o pão integral?"*

Modelo não chama `lookup_food`. Adicionar exemplo few-shot com nutriente diferente ("Quanta proteína tem o frango grelhado?") **não resolveu** — modelo continua a não generalizar para "fibra".

Hipótese refinada: o modelo aprendeu "calorias → lookup" e "proteína → lookup" como patterns isolados, não o conceito "informação nutricional → lookup". Cada nutriente provavelmente requer exemplo dedicado no few-shot.

**Falha indefendida:** validador não pode apanhar tools que não são chamadas. Utilizador recebe resposta evasiva pedindo "nome normalizado".

## Insights principais

### Insight 1 — Temperature 0 é amigo do diagnóstico

Determinismo é pré-requisito para iteração disciplinada. Sem ele, perseguem-se sintomas que se manifestam aleatoriamente. Com ele, falhas tornam-se reproduzíveis e os experimentos comparáveis.

### Insight 2 — Modelos pequenos memorizam patterns superficiais

Qwen 2.5 3B, mesmo com tool calling treinado nativamente, demonstrou:
- Cópia mimética de exemplos do few-shot (caso A1: copiou args inteiros do exemplo 5)
- Não generalização entre nutrientes (caso B3)
- Sensibilidade fina a estrutura sintáctica (não a semântica)

Estes são limites do modelo, não falhas de prompt engineering. Prompt engineering tem teto, e o teto vem do modelo.

### Insight 3 — Defesa em profundidade funciona

3 failure modes descobertos, 2 defendidos automaticamente:
- **Hallucination numérica (A1)** → camada 1 do validador
- **Args incompletos (C2)** → camada 2 do validador (adicionada após eval v1)
- **Não generalização (B3)** → indefendida (validador não vê tools não chamadas)

Custo da defesa: ~80 linhas em `validator.py`. Benefício: 2/3 dos failure modes silenciosos passam a falhar visivelmente.

### Insight 4 — Métricas mal definidas escondem bugs

`args_validity` baseline mostrava 100%. Realmente C2 estava a falhar — apenas a métrica não detectava. **Métrica que baixou após fix (75%) é mais honesta que métrica original (100%)**.

`validator_save_rate` original era 0% por definição enviesada (só contava queries da categoria "refusal"). Definição corrigida: 100%. **Verificar definições é mais importante que verificar números.**

## Decisões fechadas

| Decisão | Escolha | Justificação |
| --- | --- | --- |
| Temperature em ambas as chamadas | `0.0` | Reprodutibilidade > variedade durante desenvolvimento |
| Granularidade da AgentResponse | Dataclass rica (texto + metadados) | Suporta tanto uso simples como observabilidade |
| Validador estratégia | 2 camadas (numérico + completude) | Cobre 2 categorias de falhas com APIs distintas |
| Localização da fix de completude | `validator.py` | Coesão por responsabilidade |
| Order de validação | Numérico → completude → conversão tipos → execução | Bloqueia cedo, gasta recursos só quando vale |
| Fail mode `lookup_food → None` | Mensagem específica via `TOOL_REGISTRY[name]["no_result_message"]` | Estrutura escala para futuras tools |

## Falhas conhecidas e dívidas técnicas

### Bloqueante para Semana 3+
- **A1 (sensibilidade estrutural):** modelo 3B copia patterns. Tentativa de mitigação: experimentar Qwen 2.5 7B na Semana 3.
- **B3 (não generalização):** few-shot finito não cobre todas as estruturas linguísticas. Mitigação possível: query rewriting layer ou modelo maior.

### Documentadas mas não bloqueantes
- **`temperature=0` pode dar respostas robóticas** em produção. Considerar `temp=0.3` na 2ª chamada (geração de texto final) quando houver feedback de utilizadores reais.
- **Single-step:** queries compostas ("calcula o TDEE e depois macros") não funcionam num turno. Multi-step fica para Semana 3.
- **Validador numérico não detecta paráfrases** ("setenta quilos" → 70). Cobertura: 90% dos casos canónicos.

## Próximos passos (Dia 4)

- RAG como tool: `search_nutrition_principles` — procurar nas 592 chunks de conhecimento INSA quando utilizador faz perguntas gerais (ex: "devo comer hidratos à noite?")
- O agent passa a ter 4 caminhos: 3 tools determinísticas + RAG como 4ª tool
- Eval com queries factual/principles para medir retrieval-relevance accuracy