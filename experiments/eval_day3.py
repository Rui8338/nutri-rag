"""
Eval formal do agent loop (Dia 3 single-step).

Corre o test_set_day3.json contra o agent, mede:
- Routing accuracy (tool certa?)
- Args validity (args extraídos correctamente?)
- Refusal accuracy (absteve-se quando devia?)
- Validator save rate (quando LLM falhou, validador apanhou?)

Output: experiments/day3_v1/{config.json, raw_results.json, metrics.json, summary.md}
"""

import json
import time
from datetime import datetime
from pathlib import Path

from src.agent.loop import run_agent


# ═══════════════════════════════════════════════════════════════════════════
# Configuração
# ═══════════════════════════════════════════════════════════════════════════

EXPERIMENT_VERSION = "day3_v3"
TEST_SET_PATH = Path("experiments/test_set_day3.json")
OUTPUT_DIR = Path(f"experiments/{EXPERIMENT_VERSION}")


# ═══════════════════════════════════════════════════════════════════════════
# Avaliação por query
# ═══════════════════════════════════════════════════════════════════════════

def evaluate_query(query_def: dict, response) -> dict:
    """
    Avalia uma resposta do agent contra a expectativa do test set.

    Returns dict com flags por métrica:
    - routing_correct
    - args_valid (None se não aplicável)
    - refused_correctly (None se não aplicável)
    - validator_saved (True se validador apanhou hallucination)
    """
    expected = query_def["expected"]
    tests = query_def["tests"]

    # Routing — tool chamada é a esperada?
    expected_tool = expected.get("tool")
    actual_tool = response.tool_used
    routing_correct = (expected_tool == actual_tool)

    # Args validity — só relevante quando routing está correcto e há expectativa
    args_valid = None
    if "args_validity" in tests and routing_correct:
        args_valid = check_args_match(
            response.tool_args or {},
            expected.get("args_must_match", {}),
        )

    # Refusal — só relevante para queries de refusal
    refused_correctly = None
    if "refusal" in tests:
        # Refusal correcto: não chamou tool OU validador bloqueou
        refused_correctly = (
            actual_tool is None or response.validation_failed
        )

    # Validator save — apanhou hallucination?
    validator_saved = response.validation_failed

    return {
        "routing_correct": routing_correct,
        "args_valid": args_valid,
        "refused_correctly": refused_correctly,
        "validator_saved": validator_saved,
        "expected_tool": expected_tool,
        "actual_tool": actual_tool,
        "tool_args": response.tool_args,
        "validation_failed": response.validation_failed,
        "suspicious_args": response.suspicious_args,
        "response_text": response.text[:200] if response.text else "",
        "error": response.error,
    }


def check_args_match(actual: dict, expected: dict) -> bool:
    """Verifica se os args extraídos correspondem ao esperado."""
    for key, expected_value in expected.items():
        # Caso especial: query_contains (substring match para lookup_food)
        if key == "query_contains":
            actual_query = str(actual.get("query", "")).lower()
            if expected_value.lower() not in actual_query:
                return False
            continue

        # Caso geral: comparação directa (com tolerância para floats)
        if key not in actual:
            return False
        actual_value = actual[key]

        if isinstance(expected_value, (int, float)):
            try:
                if abs(float(actual_value) - float(expected_value)) > 0.5:
                    return False
            except (TypeError, ValueError):
                return False
        else:
            if str(actual_value).lower() != str(expected_value).lower():
                return False

    return True


# ═══════════════════════════════════════════════════════════════════════════
# Cálculo de métricas agregadas
# ═══════════════════════════════════════════════════════════════════════════

def compute_metrics(results: list[dict]) -> dict:
    """Calcula métricas agregadas a partir dos resultados por query."""
    total = len(results)

    # M1 — Routing accuracy (todas as queries)
    routing_correct = sum(1 for r in results if r["evaluation"]["routing_correct"])
    routing_acc = routing_correct / total if total else 0

    # M2 — Args validity (só queries com expectativa de args)
    args_results = [
        r["evaluation"]["args_valid"]
        for r in results
        if r["evaluation"]["args_valid"] is not None
    ]
    args_acc = (sum(args_results) / len(args_results)) if args_results else None

    # M3 — Refusal accuracy
    refusal_results = [
        r["evaluation"]["refused_correctly"]
        for r in results
        if r["evaluation"]["refused_correctly"] is not None
    ]
    refusal_acc = (sum(refusal_results) / len(refusal_results)) if refusal_results else None

    # M4 — Validator save rate
    saved_count = sum(1 for r in results if r["evaluation"]["validator_saved"])
    failed_routing = sum(1 for r in results if not r["evaluation"]["routing_correct"])
    save_rate = (saved_count / failed_routing) if failed_routing > 0 else None

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
        "args_validity": round(args_acc, 3) if args_acc is not None else None,
        "refusal_accuracy": round(refusal_acc, 3) if refusal_acc is not None else None,
        "validator_save_rate": round(save_rate, 3) if save_rate is not None else None,
        "by_category": by_category,
    }


# ═══════════════════════════════════════════════════════════════════════════
# Geração do summary em markdown
# ═══════════════════════════════════════════════════════════════════════════

def generate_summary(metrics: dict, results: list[dict]) -> str:
    """Gera relatório markdown do eval."""
    lines = [
        f"# Eval {EXPERIMENT_VERSION}",
        "",
        f"**Data:** {datetime.now().strftime('%Y-%m-%d %H:%M')}",
        f"**Test set:** {TEST_SET_PATH.name} ({metrics['total_queries']} queries)",
        "",
        "## Métricas globais",
        "",
        f"| Métrica | Valor |",
        f"| --- | --- |",
        f"| Routing accuracy | {metrics['routing_accuracy']*100:.1f}% |",
        f"| Args validity | {metrics['args_validity']*100:.1f}% |" if metrics['args_validity'] is not None else "| Args validity | N/A |",
        f"| Refusal accuracy | {metrics['refusal_accuracy']*100:.1f}% |" if metrics['refusal_accuracy'] is not None else "| Refusal accuracy | N/A |",
        f"| Validator save rate | {metrics['validator_save_rate']*100:.1f}% |" if metrics['validator_save_rate'] is not None else "| Validator save rate | N/A (sem falhas) |",
        "",
        "## Por categoria",
        "",
        f"| Categoria | Acertos | Total | Accuracy |",
        f"| --- | --- | --- | --- |",
    ]
    for cat, stats in metrics["by_category"].items():
        lines.append(
            f"| {cat} | {stats['routing_correct']} | {stats['total']} | "
            f"{stats['accuracy']*100:.1f}% |"
        )

    lines.extend(["", "## Falhas detalhadas", ""])
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
            if ev['tool_args']:
                lines.append(f"**Args extraídos:** {ev['tool_args']}")
            if ev['validation_failed']:
                lines.append(f"**Validador bloqueou:** {ev['suspicious_args']}")
            lines.append("")

    return "\n".join(lines)


# ═══════════════════════════════════════════════════════════════════════════
# Main
# ═══════════════════════════════════════════════════════════════════════════

def run_eval():
    # Carregar test set
    with open(TEST_SET_PATH, encoding="utf-8") as f:
        test_set = json.load(f)
    queries = test_set["queries"]

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    # Correr cada query
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
            if not evaluation["routing_correct"]:
                print(f"     esperado: {evaluation['expected_tool']}")

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

    # Calcular métricas
    metrics = compute_metrics(results)

    # Gravar artefactos
    config = {
        "version": EXPERIMENT_VERSION,
        "timestamp": datetime.now().isoformat(),
        "test_set": str(TEST_SET_PATH),
        "model": "qwen2.5:3b-instruct",
        "temperature": 0.0,
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

    # Print final
    print("\n" + "="*70)
    print(f"Eval {EXPERIMENT_VERSION} completo")
    print("="*70)
    print(f"Routing accuracy:     {metrics['routing_accuracy']*100:.1f}%")
    if metrics['args_validity'] is not None:
        print(f"Args validity:        {metrics['args_validity']*100:.1f}%")
    if metrics['refusal_accuracy'] is not None:
        print(f"Refusal accuracy:     {metrics['refusal_accuracy']*100:.1f}%")
    if metrics['validator_save_rate'] is not None:
        print(f"Validator save rate:  {metrics['validator_save_rate']*100:.1f}%")
    print(f"\nArtefactos em: {OUTPUT_DIR}/")


if __name__ == "__main__":
    run_eval()