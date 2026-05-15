# Limiares de decisão — Semana 3

> Pré-registados antes de qualquer corrida do 7B.
> Alterar estes limiares depois de ver resultados invalida o pré-registo.

## Decisão 1 — Pre-router rule-based

**Pergunta:** o 7B generaliza para a 4ª tool ao ponto de o pre-router
poder ser removido?

**Removo o pre-router se TODAS as condições se verificarem:**

1. Routing das queries factuais (categorias `rag_positive` e `rag_no_match`
   no `test_set_day4`) com `--pre-router off` ≥ **90%** agregado.
2. Nenhuma query factual individual com taxa de routing abaixo de **3/5**.
3. Zero regressão no routing das 3 tools determinísticas (test set do
   `eval_day3`) ao desligar o pre-router.

**Caso contrário:** mantém-se o pre-router. A configuração-padrão da
Semana 3 continua a ser `pre_router_enabled=True`.

Justificação dos números:
- 90% reconhece que exigir 100% do LLM é exigir perfeição. O pre-router
  rule-based é ~100% pela construção — mas o 7B não tem de o igualar
  exactamente, só ficar suficientemente perto.
- 3/5 individual impede que uma média boa esconda uma query
  estruturalmente partida (0/5 numa query crítica pode dar 90% global).
- Zero regressão nas determinísticas: o pre-router não tem efeito sobre
  elas hoje, logo desligá-lo não deveria mexer. Se mexer, há acoplamento
  escondido que requer investigação antes de qualquer decisão.

## Decisão 2 — Latência

**Pergunta:** o 7B é viável como default ou só como configuração opcional?

**Limite de latência:** mediana por query factual ≤ **15 segundos** com
7B-em-todo-o-lado (modelo + rewriter no 7B).

- Acima de 15s: 7B fica como configuração opcional, não default. Os
  defaults do `AgentConfig` continuam 3B.
- Abaixo de 15s: a viabilidade do 7B como default é decidida pelos
  outros critérios (qualidade), não bloqueada por latência.

Justificação: estás nos 6-10s com o 3B (Dia 4 da Semana 2). 15s é o
teto do tolerável para um humano à espera num chat. Mediana, não média
— a variabilidade do Ollama envenena a média.

## Decisão 3 — Rewriter (localização, não remoção)

O rewriter não é candidato a remoção (a necessidade dele depende do
embedding model, não do LLM — ver `docs/week3_day1_README.md`).

**Pergunta:** mover o rewriter para o 7B compensa?

**Movo o rewriter para o 7B se:** a reformulação produzir queries cujos
scores de retrieval movam ≥ 1 query do conjunto RAG do `eval_day4` de
abaixo do threshold (0.5) para acima.

**Caso contrário:** fica no 3B. Reformulação é chamada barata e
isolada; trocar por trocar adiciona latência sem ganho observável.

## Aplicação

Estes limiares são consultados no Dia 5, depois de todos os evals
correrem. Cada decisão é avaliada contra o critério escrito aqui, sem
revisão. Se o resultado for marginal (ex: 89%), a decisão é a do critério
(mantém pre-router), não a interpretação favorável.