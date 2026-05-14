"""
Eval formal do agent loop com RAG (Dia 4 single-step).

Métricas:
- Routing accuracy (tool chamada == esperada?)
- Retrieval relevance (queries RAG têm chunks com score adequado?)
- Source diversity (queries RAG retornam de fontes diversas?)
- No-match handling (queries fora do corpus tratadas correctamente?)

Output: experiments/day4_v1/{config.json, raw_results.json, metrics.json, summary.md}
"""

import json
import time
from datetime import datetime
from pathlib import Path

from src.agent.loop import run_agent


EXPERIMENT_VERSION = "day4_v2"
TEST_SET_PATH = Path("experiments/test_set_day4.json")
OUTPUT_DIR = Path(f"experiments/{EXPERIMENT_VERSION}")


def evaluate_query(query_def: dict, response) -> dict:
    """Avalia resposta do agent contra expectativa."""
    expected = query_def["expected"]
    tests = query_def["tests"]

    expected_tool = expected.get("tool")
    actual_tool = response.tool_used
    routing_correct = (expected_tool == actual_tool)

    # Retrieval relevance (só queries RAG positivas)
    retrieval_relevant = None
    if "retrieval_relevance" in tests:
        if response.tool_result and isinstance(response.tool_result, dict):
            scores = response.tool_result.get("scores", [])
            min_score = expected.get("min_top_score", 0.5)
            retrieval_relevant = (
                len(scores) > 0 and scores[0] >= min_score
            )
        else:
            retrieval_relevant = False

    # Source diversity
    source_diverse = None
    if "source_diversity" in tests:
        if response.tool_result and isinstance(response.tool_result, dict):
            sources = response.tool_result.get("sources", [])
            # Extrair "documento" da fonte (antes da vírgula)
            unique_docs = set()
            for s in sources:
                doc = s.split(",")[0].strip()
                unique_docs.add(doc)
            source_diverse = len(unique_docs) > 1
        else:
            source_diverse = False

    # No-match handling
    no_match_handled = None
    if "no_match_handling" in tests:
        # Esperamos: tool foi chamada, mas resultado é None
        if expected.get("tool_result_expected") == "none_or_low_score":
            no_match_handled = (
                actual_tool == expected_tool
                and response.tool_result is None
            )

    return {
        "routing_correct": routing_correct,
        "retrieval_relevant": retrieval_relevant,
        "source_diverse": source_diverse,
        "no_match_handled": no_match_handled,
        "expected_tool": expected_tool,
        "actual_tool": actual_tool,
        "tool_args": response.tool_args,
        "sources": (
            response.tool_result.get("sources")
            if response.tool_result and isinstance(response.tool_result, dict)
            else None
        ),
        "scores": (
            response.tool_result.get("scores")
            if response.tool_result and isinstance(response.tool_result, dict)
            else None
        ),
        "response_text": response.text[:300] if response.text else "",
    }


def compute_metrics(results: list[dict]) -> dict:
    """Calcula métricas agregadas."""
    total = len(results)

    # M1 — Routing accuracy
    routing_correct = sum(1 for r in results if r["evaluation"]["routing_correct"])
    routing_acc = routing_correct / total if total else 0

    # M2 — Retrieval relevance
    retrieval_results = [
        r["evaluation"]["retrieval_relevant"]
        for r in results
        if r["evaluation"]["retrieval_relevant"] is not None
    ]
    retrieval_acc = (
        sum(retrieval_results) / len(retrieval_results)
        if retrieval_results else None
    )

    # M3 — Source diversity
    diversity_results = [
        r["evaluation"]["source_diverse"]
        for r in results
        if r["evaluation"]["source_diverse"] is not None
    ]
    diversity_acc = (
        sum(diversity_results) / len(diversity_results)
        if diversity_results else None
    )

    # M4 — No-match handling
    no_match_results = [
        r["evaluation"]["no_match_handled"]
        for r in results
        if r["evaluation"]["no_match_handled"] is not None
    ]
    no_match_acc = (
        sum(no_match_results) / len(no_match_results)
        if no_match_results else None
    )

    # Por categoria
    by_category = {}
    for r in results:
        cat = r["query_def"]["category"]
        by_category.setdefault(cat, {"total": 0, "routing_correct": 0})
        by_category[cat]["total"] += 1
        if r["evaluation"]["routing_correct"]:
            by_category[cat]["routing_correct"] += 1

    for cat in by_category:
        b = by_category[cat]
        b["accuracy"] = b["routing_correct"] / b["total"] if b["total"] else 0

    return {
        "total_queries": total,
        "routing_accuracy": round(routing_acc, 3),
        "retrieval_relevance": round(retrieval_acc, 3) if retrieval_acc is not None else None,
        "source_diversity": round(diversity_acc, 3) if diversity_acc is not None else None,
        "no_match_handling": round(no_match_acc, 3) if no_match_acc is not None else None,
        "by_category": by_category,
    }


def generate_summary(metrics: dict, results: list[dict]) -> str:
    """Gera relatório markdown."""
    lines = [
        f"# Eval {EXPERIMENT_VERSION}",
        "",
        f"**Data:** {datetime.now().strftime('%Y-%m-%d %H:%M')}",
        f"**Test set:** {TEST_SET_PATH.name} ({metrics['total_queries']} queries)",
        "",
        "## Métricas globais",
        "",
        "| Métrica | Valor |",
        "| --- | --- |",
        f"| Routing accuracy | {metrics['routing_accuracy']*100:.1f}% |",
    ]
    if metrics['retrieval_relevance'] is not None:
        lines.append(f"| Retrieval relevance | {metrics['retrieval_relevance']*100:.1f}% |")
    if metrics['source_diversity'] is not None:
        lines.append(f"| Source diversity | {metrics['source_diversity']*100:.1f}% |")
    if metrics['no_match_handling'] is not None:
        lines.append(f"| No-match handling | {metrics['no_match_handling']*100:.1f}% |")

    lines.extend(["", "## Por categoria", ""])
    lines.append("| Categoria | Acertos | Total | Accuracy |")
    lines.append("| --- | --- | --- | --- |")
    for cat, stats in metrics["by_category"].items():
        lines.append(
            f"| {cat} | {stats['routing_correct']} | {stats['total']} | "
            f"{stats['accuracy']*100:.1f}% |"
        )

    lines.extend(["", "## Detalhes por query (RAG)", ""])
    for r in results:
        qd = r["query_def"]
        ev = r["evaluation"]
        if qd["category"] in ("rag_positive", "rag_no_match"):
            lines.append(f"### {qd['id']} ({qd['category']})")
            lines.append(f"**Query:** {qd['query']}")
            lines.append(f"**Tool:** {ev['actual_tool']} (esperado: {ev['expected_tool']})")
            if ev.get('tool_args'):
                rag_query = ev['tool_args'].get('query')
                if rag_query:
                    lines.append(f"**Query reformulada:** {rag_query}")
            if ev['sources']:
                lines.append(f"**Sources:** {ev['sources']}")
                lines.append(f"**Scores:** {ev['scores']}")
            lines.append(f"**Resposta (300 chars):** {ev['response_text']}")
            lines.append("")

    lines.extend(["", "## Falhas de routing", ""])
    failures = [r for r in results if not r["evaluation"]["routing_correct"]]
    if not failures:
        lines.append("Nenhuma falha de routing.")
    else:
        for r in failures:
            qd = r["query_def"]
            ev = r["evaluation"]
            lines.append(f"### {qd['id']} ({qd['category']})")
            lines.append(f"**Query:** {qd['query']}")
            lines.append(f"**Esperado:** {ev['expected_tool']}")
            lines.append(f"**Obtido:** {ev['actual_tool']}")
            lines.append("")

    return "\n".join(lines)


def run_eval():
    with open(TEST_SET_PATH, encoding="utf-8") as f:
        test_set = json.load(f)
    queries = test_set["queries"]

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    results = []
    for i, query_def in enumerate(queries, 1):
        print(f"[{i}/{len(queries)}] {query_def['id']} — {query_def['category']}")
        print(f"  Query: {query_def['query'][:80]}...")

        start = time.time()
        try:
            response = run_agent(query_def["query"])
            elapsed = time.time() - start
            evaluation = evaluate_query(query_def, response)

            status = "✅" if evaluation["routing_correct"] else "❌"
            print(f"  {status} tool={evaluation['actual_tool']} ({elapsed:.1f}s)")
            if evaluation['scores']:
                print(f"     scores: {evaluation['scores']}")

            results.append({
                "query_def": query_def,
                "evaluation": evaluation,
                "elapsed_seconds": round(elapsed, 2),
            })
        except Exception as e:
            print(f"  ⚠️ ERRO: {e}")
            results.append({
                "query_def": query_def,
                "evaluation": {"routing_correct": False, "error": str(e)},
                "elapsed_seconds": 0,
            })

    metrics = compute_metrics(results)

    config = {
        "version": EXPERIMENT_VERSION,
        "timestamp": datetime.now().isoformat(),
        "test_set": str(TEST_SET_PATH),
        "model": "qwen2.5:3b-instruct",
        "temperature": 0.0,
        "rag_threshold": 0.5,
        "rag_top_k": 3,
    }

    (OUTPUT_DIR / "config.json").write_text(
        json.dumps(config, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    (OUTPUT_DIR / "raw_results.json").write_text(
        json.dumps(results, indent=2, ensure_ascii=False, default=str), encoding="utf-8"
    )
    (OUTPUT_DIR / "metrics.json").write_text(
        json.dumps(metrics, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    (OUTPUT_DIR / "summary.md").write_text(
        generate_summary(metrics, results), encoding="utf-8"
    )

    print("\n" + "="*70)
    print(f"Eval {EXPERIMENT_VERSION} completo")
    print("="*70)
    print(f"Routing accuracy:    {metrics['routing_accuracy']*100:.1f}%")
    if metrics['retrieval_relevance'] is not None:
        print(f"Retrieval relevance: {metrics['retrieval_relevance']*100:.1f}%")
    if metrics['source_diversity'] is not None:
        print(f"Source diversity:    {metrics['source_diversity']*100:.1f}%")
    if metrics['no_match_handling'] is not None:
        print(f"No-match handling:   {metrics['no_match_handling']*100:.1f}%")
    print(f"\nArtefactos em: {OUTPUT_DIR}/")


if __name__ == "__main__":
    run_eval()