import json
import logging
from src.rag.chain import run_rag
from pathlib import Path

logging.basicConfig(level=logging.WARNING)  # Suprime logs durante evals

def run_evals():
    """
    Corre o eval set completo e retorna relatório com score.

    Scoring por query:
    - 60% — keywords match (informação correta na resposta)
    - 40% — source match (fonte correta citada)
    """
    eval_path = Path(__file__).parent / "eval_set.json"
    with open(eval_path) as f:
        evals = json.load(f)["evals"]

    results = []

    print("\n" + "="*60)
    print("NUTRIHUB RAG — EVAL REPORT")
    print("="*60)

    for eval_case in evals:
        # Corre o RAG
        rag_result = run_rag(eval_case["query"])
        answer = rag_result["answer"].lower()
        citations = " ".join(rag_result["citations"]).lower()

        # 1. Keywords score — quantas keywords esperadas aparecem na resposta
        keywords_found = [
            kw for kw in eval_case["expected_keywords"]
            if kw.lower() in answer
        ]
        keywords_score = len(keywords_found) / len(eval_case["expected_keywords"])

        # 2. Source score — a fonte esperada foi citada?
        source_match = eval_case["expected_source"].lower() in citations
        source_score = 1.0 if source_match else 0.0

        # 3. Score final ponderado
        final_score = (keywords_score * 0.6) + (source_score * 0.4)

        # Status visual
        if final_score >= 0.7:
            status = "PASS"
        elif final_score >= 0.5:
            status = "PARTIAL"
        else:
            status = "FAIL"

        print(f"\n[{eval_case['id']}] {eval_case['query'][:50]}...")
        print(f"  {status} | Score: {final_score:.0%}")
        print(f"  Keywords: {len(keywords_found)}/{len(eval_case['expected_keywords'])} {keywords_found}")
        print(f"  Source: {'✅' if source_match else '❌'} (esperado: {eval_case['expected_source']})")
        print(f"  Citações: {rag_result['citations']}")

        results.append({
            "id": eval_case["id"],
            "query": eval_case["query"],
            "category": eval_case["category"],
            "keywords_score": keywords_score,
            "source_score": source_score,
            "final_score": final_score,
            "status": status,
            "citations": rag_result["citations"]
        })

    # Relatório final
    print("\n" + "="*60)
    print("SUMÁRIO")
    print("="*60)

    avg_score = sum(r["final_score"] for r in results) / len(results)
    pass_count = sum(1 for r in results if r["final_score"] >= 0.7)
    partial_count = sum(1 for r in results if 0.5 <= r["final_score"] < 0.7)
    fail_count = sum(1 for r in results if r["final_score"] < 0.5)

    print(f"Score global:  {avg_score:.0%}")
    print(f"PASS:       {pass_count}/{len(results)}")
    print(f"PARTIAL:    {partial_count}/{len(results)}")
    print(f"FAIL:       {fail_count}/{len(results)}")

    # Score por categoria
    print("\nScore por categoria:")
    categories = set(r["category"] for r in results)
    for cat in categories:
        cat_results = [r for r in results if r["category"] == cat]
        cat_score = sum(r["final_score"] for r in cat_results) / len(cat_results)
        print(f"  {cat}: {cat_score:.0%}")

    # Guarda resultados
    results_path = Path(__file__).parent / "eval_results.json"
    with open(results_path, "w", encoding="utf-8") as f:
        json.dump({
            "summary": {
                "score": avg_score,
                "pass": pass_count,
                "partial": partial_count,
                "fail": fail_count,
                "total": len(results)
            },
            "results": results
        }, f, indent=2, ensure_ascii=False)

    print(f"\nResultados guardados em tests/eval_results.json")
    return avg_score

if __name__ == "__main__":
    run_evals()