# Rubrica de fidelidade ao contexto — Semana 3

> Critério de classificação manual para queries RAG do `eval_day4`.
> Pré-registada antes de qualquer corrida do 7B.

## O que esta rubrica mede

Para cada resposta gerada pelo agente após retrieval RAG, responder a:
**"o LLM foi fiel aos chunks que recebeu?"**

Esta pergunta é distinta de "a resposta é correta em absoluto":
- Resposta correta + chunks corretos + LLM ignora chunks = INFIEL (R3).
- Resposta correta + chunks errados + LLM usa conhecimento próprio = não captura
  o failure mode que nos interessa.

A fidelidade isola o comportamento do LLM dado o contexto recebido — é o que
o harness automático não vê.

## Os três níveis

### FIEL
A resposta só afirma coisas rastreáveis aos chunks. Paráfrase, condensação,
reorganização são permitidas. Para cada afirmação substantiva da resposta,
existe suporte explícito em pelo menos um chunk.

### PARCIAL
Algumas afirmações são suportadas pelos chunks; outras não. Não inventou
tudo, mas misturou conhecimento próprio com o contexto. Caso típico: o LLM
puxa um conceito correcto dos chunks mas atribui-o ao alimento ou tópico
errado (failure mode N1).

### INFIEL
A resposta é sobre tópico diferente do dos chunks, contradiz os chunks, ou
afirma coisas que os chunks não suportam de todo. Caso típico: chunks
recuperados sobre proteína, resposta gerada sobre fibra (failure mode R3).

## Aplicação

**Universo:** queries da categoria `rag_positive` e `rag_no_match` no
`test_set_day4.json`. Confirmar inclusão de:
- R1, R2, R3, R4 (rag_positive)
- N1 (rag_no_match)

**Não classificadas:** X1, X2 (cross_tool — não chamam RAG), S1 (subjective
— sem chunks por design).

**Granularidade:** uma classificação por **corrida**, não por query. Cada eval
corre 5 repetições por query. Cada repetição produz uma resposta e um conjunto
de chunks. Cada par (resposta, chunks) é classificado independentemente.

**Total por configuração:** 5 queries × 5 corridas = 25 classificações.
**Total na semana:** 25 × 3 configurações (3B-baseline, 7B-com-andaime,
7B-sem-pre-router) = 75 classificações.

## Procedimento de classificação

Para cada corrida:

1. Abrir `raw_results.json` da configuração em causa.
2. Localizar a entrada da query e repetição (ex: R3, repetition=2).
3. Ler o `evaluation.response_text` (resposta truncada a 300 chars; se a
   truncagem cortar informação crítica, ler o `raw_results.json` integral).
4. Ler os `evaluation.sources` e `evaluation.scores` (que chunks chegaram
   ao LLM).
5. Se necessário, consultar os chunks completos via query directa à BD
   ou ao retrieval (não automático nesta rubrica).
6. Classificar: FIEL, PARCIAL, ou INFIEL.
7. Registar na tabela de classificações da configuração (ver formato abaixo).

## Formato de registo

Por configuração, ficheiro `docs/week3_fidelidade_{config_name}.md`:

| Query | Repetição | Classificação | Nota breve |
|---|---|---|---|
| R1 | 1 | FIEL | — |
| R1 | 2 | PARCIAL | atribui benefício a tópico tangencial |
| R3 | 1 | INFIEL | chunks sobre proteína, resposta sobre fibra |
| ... | ... | ... | ... |

A "nota breve" é obrigatória apenas para PARCIAL e INFIEL — para FIEL pode
ficar vazia.

## Cuidados para evitar viés

- **Classificar antes de ler classificações anteriores da mesma query** — não
  deixar uma classificação enviesar a seguinte da mesma repetição noutra config.
- **Classificar uma configuração de cada vez**, completa, antes de passar à
  seguinte. Não comparar resultados entre configurações durante a classificação.
- **Não conhecer a configuração ao classificar** seria ideal mas impraticável
  aqui (são 75 classificações, não dá para mascarar). Mitigação: classificar
  por ordem aleatória das corridas dentro de cada configuração.

## O que esta rubrica não resolve

- Casos limítrofes entre FIEL e PARCIAL: se a resposta acrescenta uma
  recomendação genérica não suportada pelos chunks mas trivialmente verdadeira
  (ex: "consulte um nutricionista"), classifica-se como FIEL. Recomendações
  genéricas não constituem afirmação substantiva.
- Casos limítrofes entre PARCIAL e INFIEL: se >50% das afirmações
  substantivas são infiéis, classifica como INFIEL.
- Estas decisões marginais devem ser registadas na nota breve para auditoria.

## Versionamento

Esta rubrica é pré-registada. Alterações depois de qualquer corrida do 7B
ter sido classificada invalidam as classificações anteriores e devem ser
documentadas explicitamente neste ficheiro.