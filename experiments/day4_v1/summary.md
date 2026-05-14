# Eval day4_v1

**Data:** 2026-05-13 11:45
**Test set:** test_set_day4.json (8 queries)

## Métricas globais

| Métrica | Valor |
| --- | --- |
| Routing accuracy | 87.5% |
| Retrieval relevance | 100.0% |
| Source diversity | 50.0% |
| No-match handling | 0.0% |

## Por categoria

| Categoria | Acertos | Total | Accuracy |
| --- | --- | --- | --- |
| rag_positive | 4 | 4 | 100.0% |
| cross_tool | 1 | 2 | 50.0% |
| rag_no_match | 1 | 1 | 100.0% |
| subjective | 1 | 1 | 100.0% |

## Detalhes por query (RAG)

### R1 (rag_positive)
**Query:** É verdade que comer hidratos à noite faz mal?
**Tool:** search_nutrition_principles (esperado: search_nutrition_principles)
**Query reformulada:** hidratos de carbono consumo noturno impacto saude
**Sources:** ['Distribuicao_Alim, p.22', 'Distribuicao_Alim, p.21', 'Distribuicao_Alim, p.8']
**Scores:** [0.593, 0.567, 0.522]
**Resposta (300 chars):** De acordo com a literatura científica, comer hidratos de carbono à noite não é considerado prejudicial para a saúde, desde que o teu consumo total seja adequado às tuas necessidades energéticas diárias e ao teu estilo de vida. A distribuição dos macronutrientes (hidratos de carbono, proteínas e gord

### R2 (rag_positive)
**Query:** Quais são os benefícios da fibra alimentar?
**Tool:** search_nutrition_principles (esperado: search_nutrition_principles)
**Query reformulada:** fibra alimentar benefícios saúde intestina
**Sources:** ['Distribuicao_Alim, p.21', 'ISSN_Protein, p.11', 'Distribuicao_Alim, p.8']
**Scores:** [0.711, 0.535, 0.513]
**Resposta (300 chars):** A fibra alimentar oferece vários benefícios para a saúde e o desempenho. Ela pode ajudar a melhorar a composição corporal, contribuindo para um aumento de massa muscular e hipertrofia após treino resistente, especialmente quando comparada com proteínas vegetais que geralmente contêm menos ácidos gra

### R3 (rag_positive)
**Query:** Como é metabolizada a proteína no organismo?
**Tool:** search_nutrition_principles (esperado: search_nutrition_principles)
**Query reformulada:** metabolismo proteínas organismo funcionamento
**Sources:** ['ISSN_Protein, p.25', 'ISSN_Protein, p.17', 'ISSN_Protein, p.16']
**Scores:** [0.622, 0.62, 0.616]
**Resposta (300 chars):** A fibra alimentar é importante para a saúde porque tem vários benefícios:

1. **Promove o funcionamento saudável do trato gastrointestinal**: A fibra ajuda a manter a função intestinal regular e pode ajudar a prevenir ou controlar doenças como a obstrução intestinal, constipação e cólicas.

2. **Aju

### R4 (rag_positive)
**Query:** Quanto sódio devo consumir por dia?
**Tool:** search_nutrition_principles (esperado: search_nutrition_principles)
**Query reformulada:** sódio consumo diário recomendado saúde
**Sources:** ['DGS_Roda, p.3', 'Distribuicao_Alim, p.20', 'Distribuicao_Alim, p.54']
**Scores:** [0.758, 0.598, 0.578]
**Resposta (300 chars):** De acordo com as recomendações da DGS (Direção-Geral de Saúde) e outras fontes citadas, a quantidade de sal (sódio) que devemos consumir por dia deve ser inferior a 5g. Além disso, para a distribuição dos macronutrientes (hidratos de carbono, lipídicos e proteínas), as recomendações da OMS (Organiza

### N1 (rag_no_match)
**Query:** Quais são os benefícios do cogumelo shiitake?
**Tool:** search_nutrition_principles (esperado: search_nutrition_principles)
**Query reformulada:** shiitake benefícios saúde nutrientes
**Sources:** ['Distribuicao_Alim, p.21', 'Distribuicao_Alim, p.42', 'Distribuicao_Alim, p.51']
**Scores:** [0.707, 0.687, 0.682]
**Resposta (300 chars):** Os benefícios do cogumelo shiitake incluem:

- **Fibra**: Este é um dos nutrientes mais notáveis no shiitake. A fibra pode ajudar a melhorar o funcionamento intestinal e reduzir os níveis de colesterol.
  
- **Antioxidantes**: O shiitake contém antioxidantes que podem ajudar a combater os radicais l


## Falhas de routing

### X1 (cross_tool)
**Query:** Quantas calorias tem o salmão?
**Esperado:** lookup_food
**Obtido:** None
