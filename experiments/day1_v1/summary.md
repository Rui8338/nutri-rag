# day1_v1 — Gate de tool calling

**Data:** 2026-05-05 23:40
**Modelo:** llama3.2:3b
**Hipótese:** Llama 3.2 3B faz tool calling fiável com prompt minimalista

## TL;DR

Gate **NÃO passou**.

## Resultados

| Métrica | Valor | Gate | Status |
|---|---|---|---|
| Selection | 56% | >85% | ❌ |
| Extraction | 100% | >85% | ✅ |
| Refusal | 0% | >70% | ❌ |

## Por categoria

| Categoria | Selection | n |
|---|---|---|
| A | 100% | 8 |
| B | 100% | 6 |
| C | 12% | 8 |
| D | 0% | 5 |

## Failure modes

| Tipo | Contagem |
|---|---|
| `null_args_call` | 5 |
| `argument_hallucination` | 4 |
| `spurious_tool_use` | 3 |