# day1_v3 — Gate de tool calling

**Data:** 2026-05-05 23:55
**Modelo:** llama3.2:3b
**Hipótese:** Few-shot com 4 exemplos cirúrgicos (1 por failure mode + caso correcto) ensina o modelo a abster-se quando deve, complementando o prompt restritivo.

## TL;DR

Gate **NÃO passou**.

## Resultados

| Métrica | Valor | Gate | Status |
|---|---|---|---|
| Selection | 67% | >85% | ❌ |
| Extraction | 100% | >85% | ✅ |
| Refusal | 0% | >70% | ❌ |

## Por categoria

| Categoria | Selection | n |
|---|---|---|
| A | 100% | 8 |
| B | 100% | 6 |
| C | 50% | 8 |
| D | 0% | 5 |

## Failure modes

| Tipo | Contagem |
|---|---|
| `argument_hallucination` | 5 |
| `spurious_tool_use` | 3 |
| `null_args_call` | 1 |