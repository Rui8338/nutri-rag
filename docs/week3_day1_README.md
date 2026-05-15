# Semana 3, Dia 1 — Configurabilidade como pré-condição da avaliação

> Tornar a experiência um parâmetro, não uma edição de código.

## Objectivo

A Semana 3 pergunta: **os limites estruturais documentados na Semana 2 (não generalização para a 4ª tool, variabilidade residual mesmo com `temperature=0`, falhas de fidelidade ao contexto) eliminam-se trocando o Qwen 2.5 3B por um modelo maior, ou são propriedades do sistema independentemente do modelo?**

Responder a esta pergunta exige correr os evals dos Dias 3 e 4 sob **múltiplas configurações controladas** — pelo menos 3B-baseline (fresco, para comparar contra), 7B-com-andaime-intacto, e 7B-com-pre-router-desligado (a ablation que decide se o pre-router rule-based pode ser removido). E exige correr cada configuração **com repetição**, porque a variabilidade residual obriga a distinguir capacidade de estabilidade — uma query que acerta 3/5 não é equivalente a uma que acerta 5/5.

Nada disto era possível no estado em que o projecto entrou a Semana 3. O modelo estava codificado em quatro sítios; o `EXPERIMENT_VERSION` era constante de módulo; os eval scripts corriam cada query uma vez; o `config.json` registava strings reescritas à mão que podiam mentir sobre o que tinha realmente corrido.

O Dia 1 não tem arco experimental. Tem **uma frente de refactor**: tornar a experiência um parâmetro externo, eliminar fontes de verdade duplicadas, e dar aos eval scripts a estrutura de medição que a semana exige. É infraestrutura. O seu valor manifesta-se quando a infraestrutura é exercida — nos Dias 2 a 5 desta semana.

## Diagnóstico inicial

Antes de qualquer código, mapa do terreno via `grep`:

```
run_agent      → 4 call sites (eval_day3, eval_day4, day3_sanity, day4_sanity)
                 + 1 não-versionado (python -c "..." no README principal)
qwen2.5        → 7 ocorrências, 3 vivas (loop.py × 2, router.py × 1)
                 4 mortas/históricas (eval_day3/4 reescrevem string à mão,
                 tool_calling_gate e test_ollama_direct são código arquivado)
EXPERIMENT_VERSION → constante de módulo, 5 usos por eval script
```

A inspecção destapou um sintoma adicional: `loop.py` tinha a constante `MODEL` **duplicada em duas linhas consecutivas** (30 e 34) — copy-paste literal. Inofensivo enquanto os valores coincidem, mas exemplar do que acontece quando a configuração se faz por constante em vez de por parâmetro.

## Decisões de arquitectura

### Parâmetro explícito, não estado partilhado

A `run_agent` poderia ler a configuração de um sítio combinado (constante de módulo, variável de ambiente, objecto global). É menos intrusivo: nenhum call site teria de mudar.

Foi rejeitado. A configuração lida implicitamente é exactamente a doença que o refactor estava a tratar. Substituir "constante de módulo" por "estado partilhado" é trocar o nome do problema, não resolvê-lo.

Decisão: `run_agent(query, config=None)`. O `config=None` faz fallback a um `DEFAULT_CONFIG` que reproduz o comportamento pré-refactor — os call sites antigos continuam idênticos sem alteração.

### Knobs mínimos, não exaustivos

A `AgentConfig` tem três campos: `model`, `rewriter_model`, `pre_router_enabled`. Cada um corresponde a uma variável que a Semana 3 vai precisar de manipular. Resistir a adicionar knobs "para o futuro" foi escolha consciente — cada eixo extra duplica células na matriz de experiências e produz combinações que ninguém vai medir.

`rewriter_model` está separado de `model` mesmo tendo o mesmo default, porque é provável que a semana queira manter o rewriter no 3B (chamada barata e isolada) enquanto move a decisão principal para o 7B. Um campo só forçaria movê-los juntos.

### Argumento sem default na função de baixo nível

`rewrite_query_for_rag(user_query, model)` — `model` é obrigatório. Sem default.

Tentação: dar-lhe `model=DEFAULT_MODEL` "por segurança". Rejeitado pelo mesmo princípio. Um default numa função de baixo nível é uma fonte de verdade escondida. Se algum call site esqueça o argumento, o erro deve ser barulhento (`TypeError` imediato), não silencioso (`router.py` a correr o modelo errado enquanto o resto do sistema corre outro). O default vive **só** no `AgentConfig`.

### Rewriter no caminho da tool, não no branch do pre-router

Originalmente, `rewrite_query_for_rag` era chamado dentro do `if is_factual_question(...)`. Funcionava porque, no sistema 3B, o pre-router era a **única porta** para a tool RAG — o Qwen 3B não generaliza para a 4ª tool, logo o LLM nunca a escolhia sozinho.

A Semana 3 vai testar se o 7B generaliza. Se generalizar, há uma **segunda porta**: o LLM escolhe a tool sozinho, e a query chega ao retrieval **crua, sem reformulação**. O Dia 4 da Semana 2 mostrou que queries cruas produzem scores 0.34–0.47 (abaixo do threshold) versus 0.50–0.76 quando reformuladas. Sem refactor, uma ablation com 7B-sem-pre-router teria duas variáveis a mexer ao mesmo tempo: routing e qualidade do retrieval.

Refactor: introduzido `_run_rag_search(user_query, config)` no `loop.py`. Este helper reformula a query e chama `search_nutrition_principles`. Ambos os caminhos que levam à tool RAG (branch do pre-router, branch do LLM via caso especial) chamam-no agora. A reformulação tornou-se propriedade do **caminho da tool**, não do **detector que despachou**.

Removida em paralelo a instrução de reformulação do `description` do parâmetro `query` no `SEARCH_NUTRITION_PRINCIPLES_SCHEMA` — deixá-la lá pediria dupla reformulação no cenário 7B-decide-RAG (LLM reformula no tool call + helper reformula outra vez).

### N repetições com agregação em duas camadas

Decisão: N=5, taxa de acerto por query como agregação primária.

Justificação: a variabilidade residual a `temperature=0` (X1 no Dia 4) significa que uma corrida única não distingue capacidade de estabilidade. A pergunta "o 7B melhora?" decompõe-se em "ganhou capacidade?" (queries que eram 0/5 passam a 5/5) ou "ganhou estabilidade?" (queries que eram 2/5 passam a 5/5). A média colapsa estas duas conclusões; a taxa por query preserva-as.

N=5 e não 10: dá resolução suficiente (0/5 a 5/5) para distinguir estável, instável e partido, sem multiplicar a latência (já significativa com o 7B) para casas decimais que 8–15 queries não suportam.

Duas camadas separadas (`aggregate_query` → `compute_metrics`), e não uma função monolítica: quando uma métrica global parecer estranha, o diagnóstico pode localizar-se na camada certa. Mesmo princípio do validador de 2 camadas do Dia 3 da Semana 2 — responsabilidades separadas, falhas localizáveis.

### Denominador-por-métrica, condicional ao contexto

No `eval_day3`, `args_validity` só conta corridas onde routing acertou. Se uma query oscilar 3/5 no routing, a taxa de args é "X de 3", não "X de 5" — caso contrário a métrica de args parece má por uma razão que não é a sua (routing falhou, args nem chegou a ser avaliado).

No `eval_day4`, `retrieval_relevance` e `source_diversity` são igualmente condicionais ao routing. `no_match_handling` não, porque parte do "saber lidar" inclui *não chamar a tool* quando não há match.

Decisão de design: cada métrica decide o seu próprio denominador. Cada `aggregate_query` guarda `{hits, total}` separados em vez de já dividir, para que o `metrics.json` permita auditar de onde vem cada taxa.

## Mudanças aplicadas

| Componente | Mudança |
|---|---|
| `src/agent/config.py` | Novo. `AgentConfig` dataclass + `DEFAULT_CONFIG`. |
| `src/agent/loop.py` | `run_agent` aceita `config`. Constantes `MODEL` duplicadas eliminadas. Helper `_run_rag_search` introduzido. Caso especial RAG no branch do LLM (preparado para o cenário em que o LLM escolhe a tool sozinho). |
| `src/agent/router.py` | `REWRITER_MODEL` eliminado. `rewrite_query_for_rag` aceita `model` como argumento obrigatório. |
| `src/agent/schemas.py` | Removida instrução de reformulação do `description` do parâmetro `query` em `SEARCH_NUTRITION_PRINCIPLES_SCHEMA`. |
| `experiments/eval_day3.py` | Argumentos CLI (`--version`, `--model`, `--rewriter-model`, `--pre-router`, `--repeats`). Loop de N repetições. Agregação em duas camadas. `config.json` serializa o `AgentConfig` real. |
| `experiments/eval_day4.py` | Mesma transformação. Métricas adaptadas (retrieval, diversity, no-match). `retrieval` e `diversity` condicionais ao routing. |

## Verificação

Verificações executadas com `--repeats 2` e nomes `day3_smoke_test`/`day4_smoke_test` — explicitamente marcados como tal. Os números produzidos **não foram tratados como medição**.

| Verificação | Critério | Resultado |
|---|---|---|
| Default reproduz comportamento pré-refactor | Query factual → `search_nutrition_principles`; query de cálculo → `calculate_tdee` | ✅ |
| Knob `pre_router_enabled=False` funciona | Query factual sem pre-router cai no LLM-decisor; 3B não escolhe RAG (limite documentado) | ✅ (reproduz Dia 4 da Semana 2) |
| Rewriter no caminho da tool | Branch do pre-router reformula via helper; comportamento idêntico ao anterior | ✅ |
| Eval `--help` apresenta interface | Cinco argumentos com descrições | ✅ |
| Eval com `--repeats 2` produz artefactos | `config.json`, `raw_results.json`, `metrics.json`, `summary.md` | ✅ |
| `config.json` contém `AgentConfig` serializado | Não há strings de modelo escritas à mão | ✅ |
| Tabela "Taxa por query" no summary mostra fracções | `2/2`, `0/2` por query | ✅ |
| Tabela do Dia 4 com 5 colunas (routing + retrieval + diversity + queries não-RAG como `—`) | Condicionalidade visível | ✅ |

### O que a verificação destapou — N1 e R3 confirmadas como invisíveis ao harness

O smoke test do Dia 4 reproduziu o failure mode R3 documentado na Semana 2: query "Como é metabolizada a proteína?" → routing ✅, retrieval ✅ (chunks do ISSN_Protein com scores 0.62), resposta sobre **fibra**. Métricas verdes; resposta clamorosamente errada.

Igualmente, N1 (cogumelo shiitake) com chunks de scores 0.68–0.70 sobre fibra e antioxidantes — resposta atribui ao shiitake propriedades dos chunks sem o corpus cobrir o alimento.

Isto não é defeito do harness; é o harness a medir o que mede (estrutura do retrieval), não fidelidade de geração. **Confirma a decisão tomada para a semana: N1 e R3 serão diagnosticadas por leitura manual estruturada com rubrica pré-escrita, não por métrica automática.** A rubrica é trabalho do Dia 2.

## Decisões fechadas

| Decisão | Escolha | Justificação |
|---|---|---|
| Configuração para `run_agent` | Parâmetro explícito (`config=None`), não estado partilhado | Estado partilhado é a doença que o refactor estava a curar |
| Defaults de `AgentConfig` | 3B em ambos os modelos, pre-router ligado | Reproduz comportamento pré-refactor; critério de pronto do refactor |
| Default em `rewrite_query_for_rag` | Sem default no `model` | Erro silencioso é pior que `TypeError` barulhento |
| Localização do rewriter | Helper no caminho da tool RAG, não no branch do pre-router | Reformulação tem de acontecer venha a tool por qualquer porta |
| Modelo de rewriting no schema | Removido do `description` | Evita dupla reformulação no cenário LLM-decide-RAG |
| Lançamento do eval | Argumentos CLI, não ficheiros de config | O comando lançado **é** o registo da experiência |
| `EXPERIMENT_VERSION` | Argumento obrigatório (`--version`), sem default | Correr eval sem nomear é erro, não conveniência |
| N repetições | 5 (default), parametrizável via `--repeats` | Resolução suficiente sem latência excessiva |
| Agregação primária | Taxa por query (`hits/total`), não média | Preserva distinção capacidade vs estabilidade |
| Estrutura de agregação | Duas funções (`aggregate_query` + `compute_metrics`) | Falhas localizáveis por camada |
| Denominador de métricas condicionais | Filtrado pelo routing | "Retrieval foi bom?" só faz sentido se houve retrieval |
| Conteúdo do agregado | Só números (`{hits, total}`); conteúdo das corridas no `raw_results.json` | Decisão "simples" — sem perda, separação clara entre resumo e raw |

## Dívida deliberada

Não tudo o que se viu como melhorável foi tratado. Casos onde foi consciente:

**Duplicação entre `eval_day3.py` e `eval_day4.py`.** Os dois ficheiros partilham estrutura quase idêntica (parse_args, loop de N, gravação de artefactos). A extração de um módulo `eval_common.py` é refactor evidente — mas misturá-lo com o refactor do Dia 1 era mudar duas coisas ao mesmo tempo. Anotado para depois da Semana 3 fechar.

**Duplicação dentro do `loop.py`, no branch do LLM-escolhe-RAG.** O caso especial introduzido para a tool RAG repete o padrão "append messages → ollama.chat → return" que já existia no fim do `run_agent`. Convergência ficou para um segundo momento — primeiro fazer funcionar, verificar, *depois* limpar. Anotado.

**Caso especial RAG no branch do LLM não foi exercido.** O caminho foi escrito e verificado por construção (lê o `config`, chama o helper, monta as mensagens) mas com Qwen 3B não dispara — o 3B não escolhe a 4ª tool. A verificação real desta peça acontece na Semana 3 se o 7B generalizar. É infraestrutura preparada para uma hipótese que ainda não foi testada.

## Estrutura final (Dia 1, Semana 3)

```
src/
└── agent/
    ├── config.py          # NOVO — AgentConfig + DEFAULT_CONFIG
    ├── loop.py            # modificado — run_agent(query, config), _run_rag_search
    ├── router.py          # modificado — rewrite_query_for_rag(query, model)
    ├── schemas.py         # modificado — sem instrução de reformulação no RAG
    ├── prompts.py         # inalterado
    └── validator.py       # inalterado (funções puras, não dependem de modelo)

experiments/
├── eval_day3.py           # modificado — CLI + N repetições + duas camadas
└── eval_day4.py           # modificado — idem, com métricas RAG
```

## Próximos passos (Dia 2)

- **Re-baseline do 3B** em ambos os evals com `--repeats 5` e nomes que reivindicam o que medem (`day3_3b_baseline`, `day4_3b_baseline`). Comparação contra o 7B será feita contra estes números frescos, não contra os documentados na Semana 2 — instrumento mudou.
- **Rubrica de leitura manual** para N1 e R3, pré-escrita antes de qualquer corrida do 7B. Documento versionado.
- **Limiares de decisão pré-registados** para o pre-router: condições sob as quais o knob seria removido (taxa, distribuição por query, latência). Commit datado *antes* dos resultados.
- O 7B só entra no Dia 3.