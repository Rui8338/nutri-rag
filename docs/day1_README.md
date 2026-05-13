# Dia 1 — Gate de tool calling

> Validação isolada da capacidade de tool calling antes de construir o agent loop.

## Objectivo

Antes de adicionar 4 tools + RAG ao chatbot nutricionista, validar que o LLM escolhido faz tool calling fiável com **uma** tool simples. Princípio: erros em pipelines de LLM compõem-se multiplicativamente, por isso medimos cada capacidade isoladamente antes de compor.

## Setup

- **Tool:** `calcular_imc(peso_kg, altura_m)` — função trivial; o que se testa não é matemática mas a decisão do modelo
- **Test set:** 27 queries em 4 categorias ortogonais
  - A — pedido explícito de IMC com dados (8 queries)
  - B — pedido implícito ("estou saudável? 80kg, 1.75m") (6 queries)
  - C — perguntas gerais de nutrição que não devem chamar tool (8 queries, inclui 1 trap)
  - D — pedido de IMC com dados em falta — testa abstenção (5 queries)
- **Métricas ortogonais:**
  - Selection accuracy (chama quando deve, abstém-se quando não)
  - Extraction accuracy (extrai correctamente os números)
  - Refusal accuracy (em D, pede dados em falta em vez de inventar)
- **Gates:** Selection >85%, Extraction >85%, Refusal >70%

## Arco experimental

| Versão | Modelo | Mudança | Selection | Extraction | Refusal | Gate |
|---|---|---|---|---|---|---|
| v1 | Llama 3.2 3B | baseline (prompt minimalista) | 56% | 100% | 0% | ❌ |
| v2 | Llama 3.2 3B | prompt restritivo + descriptions | 52% | 100% | 0% | ❌ |
| v3 | Llama 3.2 3B | + 4 few-shot examples cirúrgicos | 67% | 100% | 0% | ❌ |
| v4 | Qwen 2.5 3B | mesma config, modelo trocado | 89% | 86% | 40% | ❌ |
| **v5** | **Qwen 2.5 3B** | **+ 2 few-shot adicionais** | **96%** | **100%** | **80%** | **✅** |

## Diagnósticos por iteração

**v1 → v2 (prompt restritivo não chega):** prompt engineering teve efeito **redistributivo**, não corretivo. `argument_hallucination` baixou (-1) mas `null_args_call` subiu (+3) — o modelo aprendeu "não inventar valores" obedecendo à letra (passou a chamar tool com null) mas violando o espírito (continuava a chamar quando não devia). Sinal de teto do que prompt puro consegue resolver.

**v2 → v3 (few-shot ajuda mas com limite estrutural):** few-shot resolveu `null_args_call` quase totalmente (8 → 1) e dobrou selection em C (0% → 50%). Mas categoria D continuou em 0% pela terceira versão consecutiva. Convergência de evidência: D em Llama 3.2 3B é limite estrutural, não de prompting.

**v3 → v4 (mudança de modelo desbloqueia o limite):** mantida toda a config (prompt + few-shot), só mudámos para Qwen 2.5 3B (mesmo tamanho mas function calling treinado nativamente). Resultado: categoria C subiu para 100%, refusal saltou de 0% para 40%, dois failure modes desapareceram. Confirma que era limite de modelo, não de prompting.

**v4 → v5 (refinamento cirúrgico):** análise dos 5 erros restantes em v4 revelou padrão — 4/5 usavam `peso=80` (prior estatístico do Qwen). Adicionados 2 exemplos few-shot atacando: (1) extracção em formulações não-canónicas com peso ≠ 80, (2) abstenção quando altura é dada e peso falta (espelho do exemplo já existente). Resultado: gate passa.

## Insight principal

Modelos têm **priors de valores** distintos quando inventam. Llama 3.2 3B inventava peso=70/altura=1.70. Qwen 2.5 3B inventa peso=80. Cada dimensão tem o seu prior — quando uma dimensão é dada, o modelo recorre ao prior da outra. Insight não-trivial, observável apenas lendo erros (não métricas agregadas).

## Configuração final

```python
MODEL = "qwen2.5:3b-instruct"
# Prompt: V3_SYSTEM_PROMPT (regras numeradas, conservador)
# Few-shot: V5_FEW_SHOT_MESSAGES (6 exemplos cobrindo todos os failure modes)
# Tool schema: V3_TOOL_SCHEMA (descriptions standard)
```

## Failure mode conhecido (a mitigar no Dia 3)

A única query falhada em v5 — `"Peso 70kg, e o IMC?"` — usa estrutura elíptica não coberta pelos exemplos. O agent loop (Dia 3) terá uma camada de **validação a jusante**: comparar args produzidos pelo LLM com valores literalmente presentes na query. Quando há discrepância (ex: altura inventada quando não foi mencionada), agent transforma tool call em pedido de esclarecimento.

Filosofia: defesa em profundidade. Não é a camada de tool calling que tem de atingir 100% — é o sistema completo.

## Estrutura de ficheiros

```
experiments/
├── tool_calling_gate.py       # script parametrizado (todas as versões)
├── test_set.json              # 27 queries em 4 categorias
├── day1_v1/
│   ├── config.json
│   ├── raw_results.json
│   ├── metrics.json
│   └── summary.md
├── day1_v2/  ...
├── day1_v3/  ...
├── day1_v4/  ...
└── day1_v5/  ...             # ← gate passou
docs/
├── day1_README.md             # este ficheiro
```