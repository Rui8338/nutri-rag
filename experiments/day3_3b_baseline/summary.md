# Eval day3_3b_baseline

**Data:** 2026-05-15 17:20
**Test set:** test_set_day3.json (15 queries)

## Métricas globais

| Métrica | Valor |
| --- | --- |
| Routing accuracy | 66.7% |
| Args validity | 100.0% |
| Refusal accuracy | 100.0% |
| Validator save rate | 20.0% |

## Por categoria

| Categoria | Acertos | Total | Accuracy |
| --- | --- | --- | --- |
| tdee_positive | 10 | 15 | 66.7% |
| lookup_positive | 10 | 15 | 66.7% |
| macros_positive | 5 | 10 | 50.0% |
| refusal | 15 | 15 | 100.0% |
| general | 5 | 10 | 50.0% |
| edge_case | 5 | 10 | 50.0% |

## Taxa de routing por query

| Query | Categoria | Routing |
| --- | --- | --- |
| A1 | tdee_positive | 0/5 ❌ |
| A2 | tdee_positive | 5/5 |
| A3 | tdee_positive | 5/5 |
| B1 | lookup_positive | 5/5 |
| B2 | lookup_positive | 5/5 |
| B3 | lookup_positive | 0/5 ❌ |
| C1 | macros_positive | 0/5 ❌ |
| C2 | macros_positive | 5/5 |
| D1 | refusal | 5/5 |
| D2 | refusal | 5/5 |
| D3 | refusal | 5/5 |
| E1 | general | 5/5 |
| E2 | general | 0/5 ❌ |
| E3 | edge_case | 0/5 ❌ |
| E4 | edge_case | 5/5 |

## Queries instáveis

Nenhuma query instável — todas 0/N ou N/N.