"""
Sanity check formal do agent loop COM RAG (Dia 4).

5 queries cobrindo os caminhos do agente após adição de
search_nutrition_principles e pre-router rule-based.

Diferente do day3_sanity_check.py: adiciona casos específicos de RAG
(factual via pre-router) sem repetir tudo do dia anterior.
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.agent.loop import run_agent


SANITY_QUERIES = [
    {
        "label": "RAG — pergunta factual conversacional",
        "query": "É verdade que comer hidratos à noite faz mal?",
        "expected_tool": "search_nutrition_principles",
    },
    {
        "label": "RAG — benefícios de nutriente",
        "query": "Quais são os benefícios da fibra alimentar?",
        "expected_tool": "search_nutrition_principles",
    },
    {
        "label": "Routing — não confundir lookup com RAG",
        "query": "Quantas calorias tem a banana?",
        "expected_tool": "lookup_food",
    },
    {
        "label": "Routing — não confundir TDEE com RAG",
        "query": "Quantas calorias devo comer? Tenho 30 anos, sou homem, 75kg, 178cm, treino moderado.",
        "expected_tool": "calculate_tdee",
    },
    {
        "label": "RAG — query sem chunks relevantes",
        "query": "Os ETs gostam de chocolate amargo?",
        "expected_tool": "search_nutrition_principles",
        "expected_no_chunks": True,  # esperamos chamada mas sem chunks
    },
]


def run_sanity_check():
    passed = 0
    total = len(SANITY_QUERIES)

    for i, case in enumerate(SANITY_QUERIES, 1):
        print(f"\n{'='*70}")
        print(f"[{i}/{total}] {case['label']}")
        print(f"{'='*70}")
        print(f"Query: {case['query']}")
        print(f"Esperado: {case['expected_tool']}")

        response = run_agent(case["query"])

        # Routing check
        routing_ok = response.tool_used == case["expected_tool"]
        status = "✅" if routing_ok else "❌"
        print(f"\nTool usada: {response.tool_used} {status}")

        # Args (se RAG, mostrar reformulação)
        if response.tool_args:
            if "original_query" in response.tool_args:
                print(f"Query reformulada: {response.tool_args.get('query')}")
            else:
                print(f"Args: {response.tool_args}")

        # Sources (se RAG retornou chunks)
        if response.tool_result and isinstance(response.tool_result, dict):
            sources = response.tool_result.get("sources")
            scores = response.tool_result.get("scores")
            if sources:
                print(f"Sources: {sources}")
                print(f"Scores: {scores}")

        # Caso especial: esperávamos no chunks
        if case.get("expected_no_chunks"):
            no_chunks = response.tool_result is None
            print(f"No chunks esperado: {'✅' if no_chunks else '❌'}")
            if not no_chunks:
                routing_ok = False  # falha se devolveu chunks quando não devia

        if response.validation_failed:
            print(f"⚠️ Validação falhou — {response.suspicious_args}")
        if response.error:
            print(f"⚠️ Erro: {response.error}")

        print(f"\nResposta final (300 chars):")
        print(f"  {response.text[:300]}")

        if routing_ok:
            passed += 1

    print(f"\n{'='*70}")
    print(f"RESULTADO: {passed}/{total} passaram")
    print(f"{'='*70}")


if __name__ == "__main__":
    run_sanity_check()