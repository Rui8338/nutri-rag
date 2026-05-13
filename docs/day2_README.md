# Dia 2 — Tools de produção como Python puro

> Implementar e validar a lógica determinística antes de envolver o LLM no Dia 3.

## Objectivo

Construir as 3 tools que o agent loop vai usar (`calculate_tdee`, `calculate_macros`, `lookup_food`) como funções Python puras, com unit tests rigorosos. Princípio: separar lógica de negócio (determinística) de lógica de LLM (probabilística). Quando o agent falhar no Dia 3, queremos saber **com certeza** que não é nas tools.

## Setup

Estrutura criada:

```
src/tools/
├── __init__.py
├── nutrition_calc.py    # calculate_tdee, calculate_macros
└── food_lookup.py       # FoodLookup class + lookup_food wrapper

tests/
├── test_tools.py                          # 44 unit tests para nutrition_calc
├── test_food_lookup.py                    # 23 unit tests com mock
└── test_food_lookup_integration.py        # 3 smoke tests contra DB real
```

## Tools implementadas

### `calculate_tdee(idade, peso_kg, altura_cm, sexo, fator_atividade)`

Mifflin-St Jeor + multiplicador de atividade. **26 testes** cobrindo:
- Valores canónicos verificados externamente (3 testes)
- Propriedades estruturais (homem > mulher, mais atividade > menos, etc.) (5)
- Edge cases (limites de idade, tipo de retorno) (3)
- Inputs inválidos (13 raises distintos)
- Sanity checks às constantes (2)

### `calculate_macros(tdee, peso_kg, objetivo, perfil_atividade)`

Distribuição calórica baseada em ISSN (proteína g/kg) + DGS (gorduras 25%). Hidratos como resto. **18 testes** cobrindo:
- Valores canónicos para 3 perfis distintos (3)
- Invariantes de domínio (proteína×4 + hidratos×4 + gorduras×9 ≈ alvo) (5)
- Edge cases (combinações inviáveis levantam erro) (2)
- Inputs inválidos (5)
- Sanity às constantes (3)

### `FoodLookup(session_factory)` + `lookup_food(query)`

Fuzzy matching com rapidfuzz contra `nutrition.foods` (1376 alimentos INSA). Cache em memória, classe injectável. **26 testes total** (23 unit + 3 integration).

## Decisões fechadas

| Decisão | Escolha | Justificação |
|---|---|---|
| Tipos para enums | Strings em português | Optimiza para extracção pelo LLM, não para type-safety entre programadores |
| Tratamento de erros | Raise loud (`ValueError`) | Tools são camada baixa; agent loop captura e traduz para utilizador |
| Threshold fuzzy | 70 (escala 0-100) | Acima: matches úteis. Abaixo: lixo |
| Formato de retorno `lookup_food` | Dict com 8 campos (incl. `nome` real e `score`) | Score serve para validação a jusante (Dia 3) |
| Estratégia de testes | Híbrida (mock para unit, DB real para integration) | Velocidade + isolamento + uma camada de integração real |
| Mock pattern | Classes estritas, não MagicMock | Mocks permissivos escondem bugs; estritos falham alto |
| Loading de `lookup_food` | Cache lazy via classe injectável | Testabilidade + performance |

## O que se aprendeu

### Bug do `food_importer` (whitespace nos headers Excel)

O `food_importer` da Semana 1 estava a importar **colunas a 0 silenciosamente** para 3 dos 5 macros essenciais (proteína, hidratos, fibra). Diagnóstico via query de cobertura:

```
Antes:  protein_g >0: 0/1376    carbs_g >0: 0/1376    fiber_g >0: 0/1376
Depois: protein_g >0: 1315/1376 carbs_g >0: 1040/1376 fiber_g >0: 759/1376
```

Causa: headers do Excel INSA têm `\n` e múltiplos espaços (`'Hidratos de carbono \n[g]'`). O código substituía `\n` por espaço, criando `'hidratos de carbono  [g]'` (2 espaços) que nunca batia com `'hidratos de carbono [g]'` (1 espaço) no `row.get()`. `row.get()` devolvia `None` silenciosamente, `clean_float(None)` devolvia `0.0`. Falha graceful em cascata escondeu o bug.

**Lição:** defesa em profundidade pode esconder bugs. Em mapeamento de schemas conhecidos, **fail loud** quando coluna esperada não existe é melhor que `dict.get()` defensivo.

Fix aplicado: `re.sub(r'\s+', ' ', col)` colapsa qualquer whitespace múltiplo + `get_column()` que faz `raise KeyError` se mismatch.

### Arredondamento acumula erro em valores derivados

Em `calculate_macros`, arredondar proteína/hidratos/gorduras independentemente faz com que a soma das suas calorias possa divergir do alvo até ~10 kcal. Detectado por teste de invariante (`proteína×4 + hidratos×4 + gorduras×9 ≈ alvo`). Decisão: aceitar tolerância e documentar; alternativas (recalcular um macro como "absorvedor") introduziam complexidade sem ganho real.

**Lição:** sempre que o domínio tem uma equação ou conservação (calorias, massa, percentagem que soma 100%), escreve-a como teste. Apanha bugs que testes de valor específico nunca apanham.

### Mocks devem ser estritos

Em `test_food_lookup.py`, criámos `MockSession` e `MockQuery` à mão com **só** os métodos que `FoodLookup` usa. Se o código real chamasse `session.commit()` por engano, o teste falharia imediatamente com `AttributeError`. Com `MagicMock`, o bug ficaria mudo (qualquer chamada devolve algo).

## Resultados

- **70 testes total** (44 nutrition_calc + 23 food_lookup unit + 3 food_lookup integration)
- **Todos PASSED**
- **Tempo:** ~31s (dominado pelo arranque do pytest, não pelos testes em si)

## Failure mode conhecido (a mitigar no Dia 3)

Herdado do Dia 1: o agent loop precisa de **validador a jusante** que compara args produzidos pelo LLM com valores literalmente presentes na query. Quando há discrepância (ex: altura inventada quando não foi mencionada), agent transforma tool call em pedido de esclarecimento.

Para o Dia 2, a fundação determinística está pronta para suportar isto.

## Estrutura de ficheiros (Dia 2)

```
src/
├── ingestion/
│   └── food_importer.py        # corrigido (normalização whitespace + fail-loud)
└── tools/
    ├── __init__.py
    ├── nutrition_calc.py       # calculate_tdee + calculate_macros
    └── food_lookup.py          # FoodLookup class + lookup_food wrapper

tests/
├── test_tools.py                          # 44 testes
├── test_food_lookup.py                    # 23 testes (com mock)
└── test_food_lookup_integration.py        # 3 testes (DB real)
```

## Próximos passos (Dia 3)

- Implementar agent loop single-step com Qwen 2.5 3B (config validada no Dia 1)
- Wrappar as 3 tools com JSON schemas para Ollama function calling
- Implementar **validador a jusante** (failure mode conhecido)
- Sub-eval com queries focadas em cálculo (TDEE, macros, lookup)
- Gate: tool selection >85%, refusal correcto em queries com dados em falta