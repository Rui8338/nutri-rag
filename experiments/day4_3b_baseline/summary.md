# Eval day4_3b_baseline

**Data:** 2026-05-15 16:54
**Test set:** test_set_day4.json (8 queries)

## Métricas globais

| Métrica | Valor |
| --- | --- |
| Routing accuracy | 100.0% |
| Retrieval relevance | 100.0% |
| Source diversity | 50.0% |
| No-match handling | 0.0% |

## Por categoria

| Categoria | Acertos | Total | Accuracy |
| --- | --- | --- | --- |
| rag_positive | 20 | 20 | 100.0% |
| cross_tool | 10 | 10 | 100.0% |
| rag_no_match | 5 | 5 | 100.0% |
| subjective | 5 | 5 | 100.0% |

## Taxa por query

| Query | Categoria | Routing | Retrieval | Diversity |
| --- | --- | --- | --- | --- |
| R1 | rag_positive | 5/5 | 5/5 | 0/5 |
| R2 | rag_positive | 5/5 | 5/5 | 5/5 |
| R3 | rag_positive | 5/5 | 5/5 | 0/5 |
| R4 | rag_positive | 5/5 | 5/5 | 5/5 |
| X1 | cross_tool | 5/5 | — | — |
| X2 | cross_tool | 5/5 | — | — |
| N1 | rag_no_match | 5/5 | — | — |
| S1 | subjective | 5/5 | — | — |

## Queries instáveis (routing)

Nenhuma — todas 0/N ou N/N.

## Detalhes por query RAG (corrida 1)

### R1 (rag_positive)
**Query:** É verdade que comer hidratos à noite faz mal?
**Tool:** search_nutrition_principles (esperado: search_nutrition_principles)
**Query reformulada:** hidratos de carbono consumo noturno impacto saude
**Sources:** ['Distribuicao_Alim, p.22', 'Distribuicao_Alim, p.21', 'Distribuicao_Alim, p.8']
**Scores:** [0.593, 0.567, 0.522]
**Resposta (300 chars):** De acordo com a literatura científica fornecida, comer hidratos de carbono à noite não é considerado prejudicial para a saúde. No entanto, o percentual recomendado varia dependendo da idade e do sexo:

- Para adultos, os hidratos de carbono devem representar entre 45% e 65% das suas necessidades ene

### R2 (rag_positive)
**Query:** Quais são os benefícios da fibra alimentar?
**Tool:** search_nutrition_principles (esperado: search_nutrition_principles)
**Query reformulada:** fibra alimentar benefícios saúde intestina
**Sources:** ['Distribuicao_Alim, p.21', 'ISSN_Protein, p.11', 'Distribuicao_Alim, p.8']
**Scores:** [0.711, 0.535, 0.513]
**Resposta (300 chars):** A fibra alimentar oferece vários benefícios para a saúde e o desempenho:

- **Benefícios de Saúde:** A fibra ajuda na regulação do trânsito intestinal, contribuindo para uma melhor saúde digestiva. Além disso, pode ajudar a controlar os níveis de açúcar no sangue e reduzir o risco de doenças cardiov

### R3 (rag_positive)
**Query:** Como é metabolizada a proteína no organismo?
**Tool:** search_nutrition_principles (esperado: search_nutrition_principles)
**Query reformulada:** metabolismo proteínas organismo funcionamento
**Sources:** ['ISSN_Protein, p.25', 'ISSN_Protein, p.17', 'ISSN_Protein, p.16']
**Scores:** [0.622, 0.62, 0.616]
**Resposta (300 chars):** A fibra alimentar é metabolizada no intestino e tem vários benefícios para a saúde:

1. **Promove o crescimento intestinal**: A fibra ajuda a manter uma flora intestinal saudável, contribuindo para um intestino funcionando bem.

2. **Ajuda na regulação do estômago**: A fibra aumenta a sensação de sa

### R4 (rag_positive)
**Query:** Quanto sódio devo consumir por dia?
**Tool:** search_nutrition_principles (esperado: search_nutrition_principles)
**Query reformulada:** sódio consumo diário recomendado saúde
**Sources:** ['DGS_Roda, p.3', 'Distribuicao_Alim, p.20', 'Distribuicao_Alim, p.54']
**Scores:** [0.758, 0.598, 0.578]
**Resposta (300 chars):** De acordo com as recomendações da DGS (Direção-Geral de Saúde) e outras fontes citadas, a quantidade de sal que devemos consumir por dia deve ser inferior a 5g. Além disso, para a distribuição dos macronutrientes (hidratos de carbono, lipídicos e proteínas), as recomendações da OMS de 203 preconizam

### N1 (rag_no_match)
**Query:** Quais são os benefícios do cogumelo shiitake?
**Tool:** search_nutrition_principles (esperado: search_nutrition_principles)
**Query reformulada:** shiitake benefícios saúde nutrientes
**Sources:** ['Distribuicao_Alim, p.21', 'Distribuicao_Alim, p.42', 'Distribuicao_Alim, p.51']
**Scores:** [0.707, 0.687, 0.682]
**Resposta (300 chars):** Os benefícios do cogumelo shiitake incluem:

- **Fibra**: Este é um dos nutrientes mais importantes que o cogumelo shiitake oferece. A fibra pode ajudar a melhorar a saúde digestiva e contribuir para uma dieta saudável.
  
- **Micronutrientes**: O estudo menciona que os valores de micronutrientes, c
