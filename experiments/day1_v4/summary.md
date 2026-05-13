# day1_v4 — Gate de tool calling

**Data:** 2026-05-06 11:15
**Modelo:** qwen2.5:3b-instruct
**Hipótese:** Mudar de Llama 3.2 3B para Qwen 2.5 3B (mesmo tamanho mas function calling treinado nativamente) resolve o limite estrutural observado em v1-v3, especialmente em categoria D (refusal).

## TL;DR

Gate **NÃO passou**.

## Resultados

| Métrica | Valor | Gate | Status |
|---|---|---|---|
| Selection | 89% | >85% | ✅ |
| Extraction | 86% | >85% | ✅ |
| Refusal | 40% | >70% | ❌ |

## Por categoria

| Categoria | Selection | n |
|---|---|---|
| A | 100% | 8 |
| B | 100% | 6 |
| C | 100% | 8 |
| D | 40% | 5 |

## Failure modes

| Tipo | Contagem |
|---|---|
| `argument_hallucination` | 3 |
| `wrong_arguments` | 2 |