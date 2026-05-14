# Dia 4 — RAG como tool

> Integrar pesquisa em literatura nutricional como 4ª capacidade do agente.

## Objectivo

Adicionar uma 4ª "tool" ao agent — RAG sobre os 592 chunks de literatura nutricional (INSA, DGS, ISSN). O agente passa a poder responder a perguntas factuais ("benefícios da fibra?", "hidratos à noite?") com base em corpus indexado, em vez de inventar resposta de memória própria.

Filosofia: **RAG-first para perguntas factuais.** Auditabilidade e citação de fontes valem mais que fluidez de resposta para um assistente nutricional.

## Setup

Estrutura criada:

```
src/tools/
└── rag_search.py        # Wrapper sobre NutritionRetriever da Semana 1

src/agent/
├── schemas.py            # +SEARCH_NUTRITION_PRINCIPLES_SCHEMA
├── prompts.py            # +regra 9, exemplos RAG no few-shot
├── router.py             # NOVO — pre-router rule-based + LLM query rewriter
└── loop.py               # +branch RAG, integra pre-router

experiments/
├── test_set_day4.json    # 8 queries focadas em RAG
├── eval_day4.py          # script de avaliação
├── day4_sanity_check.py  # smoke tests informais
├── day4_v1/              # eval inicial
└── day4_v2/              # eval final (após reformulação de X1)
```

## Componentes

### Tool 4: `search_nutrition_principles`

Wrapper sobre `NutritionRetriever` (Semana 1, LangChain-compatible). Diferente das tools determinísticas:
- Cache lazy do modelo de embeddings (`paraphrase-multilingual-MiniLM-L12-v2`)
- Threshold de similaridade calibrado a 0.5 (empírico)
- Retorna top-K chunks com score, ou `None` se nada acima do threshold
- Filtra chunks abaixo do threshold para evitar lixo no contexto do LLM

### Pre-router rule-based

**Necessidade descoberta empiricamente.** Qwen 2.5 3B **não generaliza** para escolher a 4ª tool, mesmo com:
- Description detalhada no schema
- 2 exemplos few-shot dedicados
- 4 tentativas de prompt engineering (regra 9 reformulada várias vezes)

Decisão: **router rule-based força routing para RAG** quando query contém keywords factuais ("benefícios", "é verdade", "como é metabolizada"). LLM mantém autonomia para escolher entre as 3 tools determinísticas em queries não-factuais.

Filosofia: **constrangimento do modelo > pureza arquitectural.** Padrão da indústria (LLM-only routing) requer modelos maiores. Para 3B local, hybrid routing é proporcional.

### Query rewriter (LLM-based)

Pre-router decide **se** chamar RAG. Query rewriter decide **o quê** procurar.

Razão: queries conversacionais ("É verdade que comer hidratos à noite faz mal?") produzem embeddings desalinhados com chunks técnicos do corpus. Calibração empírica:
- Query crua: scores 0.34-0.47 (abaixo do threshold)
- Query reformulada via LLM: scores 0.50-0.76 (passa threshold)

Implementação: 1 chamada Ollama com prompt + 3 few-shot examples. Output validado (length 2-15 palavras, sem prefixos suspeitos como "Query:"). Fallback rule-based em caso de falha.

Trade-off vs rule-based puro:
- ✅ LLM expande "hidratos" → "hidratos de carbono", adiciona termos técnicos relacionados
- ❌ +2-3s de latência por query factual
- ❌ Risco de output mau (mitigado por validação + fallback)

### Defesa em profundidade — 3 camadas

| Camada | Mecanismo | Failure mode coberto |
|---|---|---|
| Pre-router | Rule-based keywords | LLM não escolhe RAG quando devia |
| Query rewriter | LLM com fallback rule-based | Query crua não alinha com corpus |
| Threshold 0.5 | Score filter pós-retrieval | Chunks marginais contaminam contexto |

## Arco experimental

### Sanity check informal (4 queries × 3 execuções) — Fase 3

Antes do eval formal, validação dos 4 caminhos do agente após integração.

**Descoberta crítica:** mesmo com `temperature=0` aplicado no Dia 3, a integração inicial via prompt engineering puro **falhou em 100% das queries factuais**. O LLM respondia de memória, ignorando o RAG.

Sequência de fixes tentadas (todas falharam):
1. Description do schema com exemplos de uso
2. Regra 9 explícita no system prompt
3. 2 exemplos few-shot dedicados a RAG
4. Reformulação da regra 9 (mais curta, anti-pattern)

Diagnóstico final: **Qwen 2.5 3B não generaliza para 4ª tool** mesmo com few-shot literal. Verificado com chamada Ollama directa (bypass do agent loop) — confirmou que o limite é do modelo, não do código.

**Decisão:** abandonar approach LLM-only para routing. Implementar pre-router rule-based (Caminho B do plano).

### Eval v1 — Baseline pós-integração

Test set de 8 queries: 4 RAG positive + 2 cross-tool + 1 RAG no-match + 1 subjective.

Resultados:

| Métrica | v1 |
| --- | --- |
| Routing accuracy | 87.5% (7/8) |
| Retrieval relevance | 100% |
| Source diversity | 50% |
| No-match handling | 0% |

Falha em X1: "Quantas calorias tem o salmão?" → tool=None (modelo pediu clarificação).

### Diagnóstico de X1 — descoberta de domínio

Antes de aplicar fix automática, investigação manual do output revelou:

> "preciso do nome específico do alimento. Podes dizer qual é o salmão que te interessa? Por exemplo, 'salmão grelhado' ou 'salmão assado'"

Verificação na tabela INSA:

```sql
SELECT name, calories FROM nutrition.foods WHERE name ILIKE '%salmão%';
-- Salmão cru: 262 kcal
-- Salmão cozido: 273 kcal
-- Salmão grelhado: 309 kcal
```

**O modelo estava correcto.** Salmão tem 3 variantes na INSA com diferença de 47 kcal entre extremos (18%). Forçar lookup com `query="salmão"` faria `rapidfuzz` devolver entrada arbitrária — resposta tecnicamente errada.

Decisão: **teste estava mal calibrado**, não o sistema. X1 reformulado para "Quantas calorias tem o salmão grelhado?" — query sem ambiguidade no domínio.

### Eval v2 — Pós-reformulação de X1

Mesmas 8 queries com X1 reformulado:

| Métrica | v1 | v2 |
| --- | --- | --- |
| Routing accuracy | 87.5% | 87.5% |
| Retrieval relevance | 100% | 100% |
| Source diversity | 50% | 50% |
| No-match handling | 0% | 0% |

**X1 continuou a falhar** — mas standalone (`python -c "..."` directo) **funciona**. Investigação confirmou variabilidade do Qwen 3B mesmo com `temperature=0`:
- Standalone: `Tool: lookup_food`, resposta correcta com 309 kcal
- Mesmo comando depois de outras queries: `Tool: None`, pede "versão normalizada"

Diagnóstico: **estado interno do Ollama afecta decisões em queries de fronteira** mesmo com determinismo nominal. Floating point em GPU + cache parcial causam variabilidade residual.

**Decisão:** aceitar 87.5% como número honesto. Não calibrar test set à medida do modelo (anti-pattern); não optimizar para estado ideal do Ollama (condição que não existe em produção).

## Análise dos failure modes finais

### X1 — Variabilidade residual em queries de fronteira

Comportamento standalone difere de comportamento em batch. Queries de fronteira (ex: lookup vs clarificação) oscilam entre execuções. **Não é bug** — é característica operacional do modelo 3B local.

**Falha defendida:** quando o LLM pede clarificação em vez de chamar tool, o utilizador recebe pergunta razoável. Não há resposta errada — há resposta incompleta.

**Mitigação para Semana 3+:** modelo maior (Qwen 2.5 7B) tem menos sensibilidade a estado residual.

### N1 — Chunks tangenciais atribuídos ao alimento

Query: "Quais são os benefícios do cogumelo shiitake?"
- Routing: ✅ chamou RAG
- Retrieval: chunks com scores 0.68-0.71 (acima do threshold)
- **Mas** chunks são sobre fibra e antioxidantes em geral, não sobre shiitake
- Resposta: LLM atribui propriedades dos chunks ao shiitake ("O shiitake contém antioxidantes...")

**Failure mode crítico:** corpus não cobre o alimento mas retrieval encontra chunks tematicamente próximos com scores enganadoramente altos. LLM gera resposta inventada baseada em chunks tangencialmente relevantes.

**Mitigação:** modelo final maior reconheceria mismatch e diria "não tenho informação específica sobre shiitake". Para Qwen 3B, requer prompt mais agressivo ou re-ranking de chunks. Trade-off de tempo no Dia 4 levou a aceitar como dívida técnica.

### R3 — LLM ignora chunks e responde off-topic

Query: "Como é metabolizada a proteína no organismo?"
- Routing: ✅ chamou RAG
- Retrieval: chunks de ISSN_Protein, scores 0.62 (relevantes)
- Resposta: "**A fibra alimentar** é importante para a saúde..." (sobre fibra, não proteína)

Hipótese: o LLM "saltou" para tópico que conhece melhor. Pode ter sido influenciado por chunks de queries RAG anteriores no contexto da sessão (R2 era sobre fibra).

**Failure mode crítico:** o LLM não está a basear-se nos chunks fornecidos. Inverte completamente a relação retrieval → resposta.

**Mitigação:** mesma que N1 — modelo maior ou prompt engineering agressivo de "If chunks don't directly cover the question, say so".

## Insights principais

### Insight 1 — Limites de generalização do Qwen 3B

Demonstrado empiricamente:
- **Não generaliza para 4ª tool** (RAG) mesmo com few-shot literal
- **Sensibilidade estrutural a queries** (Dia 3 — "Tenho X..." vs "Quantas calorias?")
- **Variabilidade residual** mesmo com `temperature=0` (Dia 4 — query do salmão)
- **Pode ignorar chunks no contexto** ao gerar resposta final (R3)

Prompt engineering tem teto. O teto vem do modelo. Modelos 3B locais têm teto baixo para tarefas que requerem:
- Generalização entre múltiplas tools (>3)
- Manutenção de fidelidade a contexto fornecido
- Determinismo estrito

### Insight 2 — Query rewriting é necessário para RAG com queries conversacionais

Mismatch entre linguagem do utilizador e linguagem do corpus é fundamental em RAG. Calibração empírica:
- Queries conversacionais → scores ~0.40 (lixo)
- Queries técnicas reformuladas → scores ~0.65 (relevante)

Padrão da indústria (HyDE, multi-query, LLM rewriting) é resposta a este problema. Implementação local com Qwen 3B funcionou — o modelo é competente em reformulação mesmo com limites em routing.

### Insight 3 — Test set como reflexo da realidade

A query X1 inicial ("Quantas calorias tem o salmão?") parecia razoável. Investigação revelou que o domínio INSA tem 3 variantes de salmão com diferença real de 47 kcal. O comportamento "correto" do sistema é pedir clarificação, não devolver entrada arbitrária.

**Lição:** test set deve reflectir o domínio real, não suposições sobre como utilizadores fazem queries. Calibrar test set ao sistema é anti-pattern; calibrar test set ao domínio é design correcto.

### Insight 4 — Defesa em profundidade aplicada a RAG

3 camadas funcionando juntas:
- Pre-router rule-based (cobre não-generalização)
- LLM rewriter (cobre query/corpus mismatch)
- Threshold 0.5 (cobre chunks marginais)

Cada camada cobre um failure mode específico. Sistema final tem mais camadas defensivas do que decisões puras. Custo: ~250 linhas adicionais. Benefício: queries factuais agora dão respostas baseadas em corpus indexado.

## Decisões fechadas

| Decisão | Escolha | Justificação |
| --- | --- | --- |
| Routing para RAG | Rule-based pre-router | Qwen 3B não generaliza para 4ª tool empiricamente |
| Query rewriting | LLM-based com fallback rule-based | Padrão da indústria; queries conversacionais requerem expansão técnica |
| Threshold de retrieval | 0.5 | Calibração empírica: separa cirurgicamente queries legítimas (>0.5) de lixo (<0.5) |
| Top-K chunks | 3 | Equilibra contexto vs ruído |
| Aceitar X1 a 87.5% | Documentar variabilidade | Honestidade > inflação; baseline para comparar com modelo maior |
| RAG-first para perguntas factuais | Filosofia A | Auditabilidade > fluidez em contexto profissional |

## Falhas conhecidas e dívidas técnicas

### Bloqueantes para Semana 3+
- **Não generalização para 4ª tool:** mitigado por pre-router, mas constrangimento real. Modelo maior eliminaria necessidade do router rule-based.
- **Variabilidade residual com `temperature=0`:** queries de fronteira oscilam entre runs. Não é bug, é característica do 3B.
- **Chunks tangenciais (N1):** sistema não detecta quando retrieval é "tematicamente próximo mas não cobre a pergunta".
- **LLM ignora chunks (R3):** falha de fidelidade ao contexto fornecido.

### Documentadas mas não bloqueantes
- **Citações genéricas:** modelo cita "literatura científica" em vez de "Distribuicao_Alim, p.21". Aceitável para Dia 4; modelo maior citaria especificamente.
- **Source diversity 50%:** corpus concentrado em poucos documentos; queries específicas tendem a vir do mesmo doc. Limite do corpus, não do retrieval.
- **Latência de queries factuais:** ~6-10s (3 chamadas Ollama). Aceitável para chat; problemático para tempo-real.

## Próximos passos (Dia 5)

- README final do projeto (público-alvo: portfolio)
- Eval consolidado dos Dias 1-4
- Análise honesta de trade-offs do sistema completo
- Caminhos de evolução documentados (modelo maior, multi-step, deployment)