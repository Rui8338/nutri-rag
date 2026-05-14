# Eval day3_v1

**Data:** 2026-05-09 23:39
**Test set:** test_set_day3.json (15 queries)

## Métricas globais

| Métrica | Valor |
| --- | --- |
| Routing accuracy | 86.7% |
| Args validity | 75.0% |
| Refusal accuracy | 100.0% |
| Validator save rate | 0.0% |

## Por categoria

| Categoria | Acertos | Total | Accuracy |
| --- | --- | --- | --- |
| tdee_positive | 2 | 3 | 66.7% |
| lookup_positive | 2 | 3 | 66.7% |
| macros_positive | 2 | 2 | 100.0% |
| refusal | 3 | 3 | 100.0% |
| general | 2 | 2 | 100.0% |
| edge_case | 2 | 2 | 100.0% |

## Falhas detalhadas

### A1 (tdee_positive)
**Query:** Tenho 30 anos, peso 75kg, meço 1.78m, sou homem e faço exercício moderado 4 vezes por semana. Quantas calorias devo comer?
**Esperado:** calculate_tdee
**Obtido:** calculate_macros
**Args extraídos:** {'objetivo': 'manter', 'perfil_atividade': 'ativo', 'peso_kg': 75, 'tdee': 2400}
**Validador bloqueou:** ['tdee']

### B3 (lookup_positive)
**Query:** Quanto de fibra tem o pão integral?
**Esperado:** lookup_food
**Obtido:** None
