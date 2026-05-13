# day1_v2 — Gate de tool calling

**Data:** 2026-05-05 23:47
**Modelo:** llama3.2:3b
**Hipótese:** Prompt restritivo com regras numeradas + descriptions reforçadas elimina null_args_call, argument_hallucination, spurious_tool_use

## TL;DR

Gate **NÃO passou**.

## Resultados

| Métrica | Valor | Gate | Status |
|---|---|---|---|
| Selection | 52% | >85% | ❌ |
| Extraction | 100% | >85% | ✅ |
| Refusal | 0% | >70% | ❌ |

## Por categoria

| Categoria | Selection | n |
|---|---|---|
| A | 100% | 8 |
| B | 100% | 6 |
| C | 0% | 8 |
| D | 0% | 5 |

## Failure modes

| Tipo | Contagem |
|---|---|
| `null_args_call` | 8 |
| `argument_hallucination` | 3 |
| `spurious_tool_use` | 2 |