"""
Eval formal do agent loop com RAG (Dia 4 single-step).

Métricas:
- Routing accuracy (tool chamada == esperada?)
- Retrieval relevance (queries RAG têm chunks com score adequado?)
  Condicional ao routing ter acertado — só conta corridas onde a tool RAG correu.
- Source diversity (queries RAG retornam de fontes diversas?)
  Também condicional ao routing.
- No-match handling (queries fora do corpus tratadas correctamente?)

Output: experiments/{version}/{config.json, raw_results.json, metrics.json, summary.md}
"""

import json
import time
import argparse
from datetime import datetime
from pathlib import Path

from src.agent.loop import run_agent
from src.agent.config import AgentConfig


TEST_SET_PATH = Path("experiments/test_set_day4.json")


def parse_args() -> argparse.Namespace:
    """Argumentos da experiência (ver eval_day3 para a filosofia)."""
    parser = argparse.ArgumentParser(description="Eval do agent loop com RAG (Dia 4).")
    parser.add_argument(
        "--version", required=True,
        help="Nome da experiência. Define a pasta de output "
             "(ex: day4_3b_baseline, day4_7b_no_router).",
    )
    parser.add_argument("--model", default="qwen2.5:3b-instruct")
    parser.add_argument("--rewriter-model", default="qwen2.5:3b-instruct")
    parser.add_argument("--pre-router", choices=["on", "off"], default="on")
    parser.add_argument("--repeats", type=int, default=5)
    return parser.parse_args()


def evaluate_query(query_def: dict, response) -> dict:
    """Avalia resposta do agent contra expectativa. (inalterado)"""
    expected = query_def["expected"]
    tests = query_def["tests"]

    expected_tool = expected.get("tool")
    actual_tool = response.tool_used
    routing_correct = (expected_tool == actual_tool)

    retrieval_relevant = None
    if "retrieval_relevance" in tests:
        if response.tool_result and isinstance(response.tool_result, dict):
            scores = response.tool_result.get("scores", [])
            min_score = expected.get("min_top_score", 0.5)
            retrieval_relevant = (len(scores) > 0 and scores[0] >= min_score)
        else:
            retrieval_relevant = False

    source_diverse = None
    if "source_diversity" in tests:
        if response.tool_result and isinstance(response.tool_result, dict):
            sources = response.tool_result.get("sources", [])
            unique_docs = set()
            for s in sources:
                doc = s.split(",")[0].strip()
                unique_docs.add(doc)
            source_diverse = len(unique_docs) > 1
        else:
            source_diverse = False

    no_match_handled = None
    if "no_match_handling" in tests:
        if expected.get("tool_result_expected") == "none_or_low_score":
            no_match_handled = (
                actual_tool == expected_tool and response.tool_result is None
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


# ═══════════════════════════════════════════════════════════════════════════
# Agregação — camada 1: juntar as N corridas de UMA query.
# ═══════════════════════════════════════════════════════════════════════════

def aggregate_query(query_def: dict, evaluations: list[dict]) -> dict:
    """
    Agrega as N corridas de uma query em taxas por métrica.

    Decisões de denominador, por métrica:
    - routing: conta todas as N corridas (sempre aplicável).
    - retrieval_relevant e source_diverse: SÓ corridas onde routing acertou.
      Senão misturávamos "tool não foi exercida" com "tool foi má".
    - no_match_handled: aplicável quando o test set o pede, todas as corridas.
    """
    n = len(evaluations)

    routing_hits = sum(1 for e in evaluations if e["routing_correct"])

    # Retrieval relevance — só onde routing acertou E a métrica é aplicável
    retrieval_evals = [
        e["retrieval_relevant"]
        for e in evaluations
        if e["routing_correct"] and e["retrieval_relevant"] is not None
    ]
    retrieval_hits = sum(1 for v in retrieval_evals if v)

    # Source diversity — mesma condicionalidade
    diversity_evals = [
        e["source_diverse"]
        for e in evaluations
        if e["routing_correct"] and e["source_diverse"] is not None
    ]
    diversity_hits = sum(1 for v in diversity_evals if v)

    # No-match — todas as corridas onde a métrica é aplicável
    no_match_evals = [
        e["no_match_handled"]
        for e in evaluations
        if e["no_match_handled"] is not None
    ]
    no_match_hits = sum(1 for v in no_match_evals if v)

    return {
        "id": query_def["id"],
        "category": query_def["category"],
        "repeats": n,
        "routing": {"hits": routing_hits, "total": n},
        "retrieval_relevance": (
            {"hits": retrieval_hits, "total": len(retrieval_evals)}
            if retrieval_evals else None
        ),
        "source_diversity": (
            {"hits": diversity_hits, "total": len(diversity_evals)}
            if diversity_evals else None
        ),
        "no_match_handling": (
            {"hits": no_match_hits, "total": len(no_match_evals)}
            if no_match_evals else None
        ),
    }


# ═══════════════════════════════════════════════════════════════════════════
# Agregação — camada 2: queries agregadas → métrica global.
# ═══════════════════════════════════════════════════════════════════════════

def compute_metrics(aggregated: list[dict]) -> dict:
    """Soma de hits / soma de totals, por métrica (ver eval_day3)."""
    total_queries = len(aggregated)

    def _global(key: str) -> float | None:
        hits = sum(q[key]["hits"] for q in aggregated if q[key])
        total = sum(q[key]["total"] for q in aggregated if q[key])
        return (hits / total) if total else None

    routing_hits = sum(q["routing"]["hits"] for q in aggregated)
    routing_total = sum(q["routing"]["total"] for q in aggregated)
    routing_acc = routing_hits / routing_total if routing_total else 0

    by_category = {}
    for q in aggregated:
        cat = q["category"]
        by_category.setdefault(cat, {"routing_hits": 0, "routing_total": 0})
        by_category[cat]["routing_hits"] += q["routing"]["hits"]
        by_category[cat]["routing_total"] += q["routing"]["total"]
    for cat in by_category:
        b = by_category[cat]
        b["accuracy"] = b["routing_hits"] / b["routing_total"] if b["routing_total"] else 0

    def _round(v):
        return round(v, 3) if v is not None else None

    return {
        "total_queries": total_queries,
        "routing_accuracy": round(routing_acc, 3),
        "retrieval_relevance": _round(_global("retrieval_relevance")),
        "source_diversity": _round(_global("source_diversity")),
        "no_match_handling": _round(_global("no_match_handling")),
        "by_category": by_category,
    }


def generate_summary(version: str, metrics: dict, aggregated: list[dict], raw_results: list[dict]) -> str:
    """Gera relatório markdown."""
    lines = [
        f"# Eval {version}",
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
            f"| {cat} | {stats['routing_hits']} | {stats['routing_total']} | "
            f"{stats['accuracy']*100:.1f}% |"
        )

    # Taxa por query — onde a instabilidade aparece
    lines.extend(["", "## Taxa por query", ""])
    lines.append("| Query | Categoria | Routing | Retrieval | Diversity |")
    lines.append("| --- | --- | --- | --- | --- |")
    for q in aggregated:
        r = q["routing"]
        rel = q["retrieval_relevance"]
        div = q["source_diversity"]
        rel_s = f"{rel['hits']}/{rel['total']}" if rel else "—"
        div_s = f"{div['hits']}/{div['total']}" if div else "—"
        flag = "" if r["hits"] == r["total"] else " ⚠️" if r["hits"] > 0 else " ❌"
        lines.append(f"| {q['id']} | {q['category']} | {r['hits']}/{r['total']}{flag} | {rel_s} | {div_s} |")

    unstable = [q for q in aggregated
                if 0 < q["routing"]["hits"] < q["routing"]["total"]]
    lines.extend(["", "## Queries instáveis (routing)", ""])
    if not unstable:
        lines.append("Nenhuma — todas 0/N ou N/N.")
    else:
        lines.append("Estas oscilaram entre corridas:")
        lines.append("")
        for q in unstable:
            r = q["routing"]
            lines.append(f"- **{q['id']}** ({q['category']}): {r['hits']}/{r['total']}")

    # Detalhes RAG — mostra UMA corrida representativa por query (a primeira)
    # As outras corridas estão no raw_results.json.
    lines.extend(["", "## Detalhes por query RAG (corrida 1)", ""])
    first_run_by_query = {}
    for r in raw_results:
        qid = r["query_def"]["id"]
        if qid not in first_run_by_query:
            first_run_by_query[qid] = r

    for qid, r in first_run_by_query.items():
        qd = r["query_def"]
        ev = r["evaluation"]
        if qd["category"] in ("rag_positive", "rag_no_match"):
            lines.append(f"### {qd['id']} ({qd['category']})")
            lines.append(f"**Query:** {qd['query']}")
            lines.append(f"**Tool:** {ev.get('actual_tool')} (esperado: {ev.get('expected_tool')})")
            if ev.get('tool_args'):
                rag_query = ev['tool_args'].get('query')
                if rag_query:
                    lines.append(f"**Query reformulada:** {rag_query}")
            if ev.get('sources'):
                lines.append(f"**Sources:** {ev['sources']}")
                lines.append(f"**Scores:** {ev['scores']}")
            if ev.get('response_text'):
                lines.append(f"**Resposta (300 chars):** {ev['response_text']}")
            lines.append("")

    return "\n".join(lines)


def run_eval(version: str, config: AgentConfig, repeats: int):
    output_dir = Path(f"experiments/{version}")
    output_dir.mkdir(parents=True, exist_ok=True)

    with open(TEST_SET_PATH, encoding="utf-8") as f:
        test_set = json.load(f)
    queries = test_set["queries"]

    raw_results = []
    aggregated = []

    for i, query_def in enumerate(queries, 1):
        print(f"[{i}/{len(queries)}] {query_def['id']} — {query_def['category']}")
        print(f"  Query: {query_def['query'][:80]}...")

        query_evaluations = []

        for rep in range(1, repeats + 1):
            start = time.time()
            try:
                response = run_agent(query_def["query"], config)
                elapsed = time.time() - start
                evaluation = evaluate_query(query_def, response)

                status = "✅" if evaluation["routing_correct"] else "❌"
                scores_str = ""
                if evaluation.get('scores'):
                    scores_str = f" scores={evaluation['scores']}"
                print(f"  rep {rep}/{repeats}: {status} tool={evaluation['actual_tool']} ({elapsed:.1f}s){scores_str}")

                query_evaluations.append(evaluation)
                raw_results.append({
                    "query_def": query_def,
                    "repetition": rep,
                    "evaluation": evaluation,
                    "elapsed_seconds": round(elapsed, 2),
                })
            except Exception as e:
                print(f"  rep {rep}/{repeats}: ⚠️ ERRO: {e}")
                failed_eval = {
                    "routing_correct": False,
                    "retrieval_relevant": None,
                    "source_diverse": None,
                    "no_match_handled": None,
                    "error": str(e),
                }
                query_evaluations.append(failed_eval)
                raw_results.append({
                    "query_def": query_def,
                    "repetition": rep,
                    "evaluation": failed_eval,
                    "elapsed_seconds": 0,
                })

        agg = aggregate_query(query_def, query_evaluations)
        aggregated.append(agg)
        print(f"  → routing {agg['routing']['hits']}/{agg['routing']['total']}")

    metrics = compute_metrics(aggregated)

    config_record = {
        "version": version,
        "timestamp": datetime.now().isoformat(),
        "test_set": str(TEST_SET_PATH),
        "agent_config": config.to_dict(),
        "repeats": repeats,
        "temperature": 0.0,
        "rag_threshold": 0.5,
        "rag_top_k": 3,
    }

    (output_dir / "config.json").write_text(
        json.dumps(config_record, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    (output_dir / "raw_results.json").write_text(
        json.dumps(raw_results, indent=2, ensure_ascii=False, default=str), encoding="utf-8"
    )
    (output_dir / "metrics.json").write_text(
        json.dumps({"global": metrics, "by_query": aggregated}, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    (output_dir / "summary.md").write_text(
        generate_summary(version, metrics, aggregated, raw_results), encoding="utf-8"
    )

    print("\n" + "="*70)
    print(f"Eval {version} completo — {repeats} repetições por query")
    print("="*70)
    print(f"Routing accuracy:    {metrics['routing_accuracy']*100:.1f}%")
    if metrics['retrieval_relevance'] is not None:
        print(f"Retrieval relevance: {metrics['retrieval_relevance']*100:.1f}%")
    if metrics['source_diversity'] is not None:
        print(f"Source diversity:    {metrics['source_diversity']*100:.1f}%")
    if metrics['no_match_handling'] is not None:
        print(f"No-match handling:   {metrics['no_match_handling']*100:.1f}%")
    print(f"\nArtefactos em: {output_dir}/")


if __name__ == "__main__":
    args = parse_args()
    config = AgentConfig(
        model=args.model,
        rewriter_model=args.rewriter_model,
        pre_router_enabled=(args.pre_router == "on"),
    )
    run_eval(version=args.version, config=config, repeats=args.repeats)