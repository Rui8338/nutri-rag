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
import argparse
from datetime import datetime
from pathlib import Path

from src.agent.loop import run_agent
from src.agent.config import AgentConfig


# ═══════════════════════════════════════════════════════════════════════════
# Configuração — vem da linha de comando, não é constante de módulo.
# A experiência (que modelo, pre-router on/off, quantas repetições) é um
# PARÂMETRO, não uma edição de código. O parse_args devolve tudo o que o
# run_eval precisa para ser reproduzível.
# ═══════════════════════════════════════════════════════════════════════════

TEST_SET_PATH = Path("experiments/test_set_day3.json")


def parse_args() -> argparse.Namespace:
    """
    Argumentos da experiência. O comando que lanças É o registo da
    experiência — fica no histórico do shell, cola-se no README.
    """
    parser = argparse.ArgumentParser(description="Eval do agent loop (Dia 3).")
    parser.add_argument(
        "--version", required=True,
        help="Nome da experiência. Define a pasta de output "
             "(ex: day3_3b_baseline, day3_7b_no_router).",
    )
    parser.add_argument(
        "--model", default="qwen2.5:3b-instruct",
        help="Modelo Ollama para o loop do agente.",
    )
    parser.add_argument(
        "--rewriter-model", default="qwen2.5:3b-instruct",
        help="Modelo Ollama para o query rewriter do RAG.",
    )
    parser.add_argument(
        "--pre-router", choices=["on", "off"], default="on",
        help="Liga ou desliga o pre-router rule-based.",
    )
    parser.add_argument(
        "--repeats", type=int, default=5,
        help="Quantas vezes correr cada query (variabilidade do 3B).",
    )
    return parser.parse_args()


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
# Agregação — camada 1: juntar as N corridas de UMA query.
# ═══════════════════════════════════════════════════════════════════════════

def aggregate_query(query_def: dict, evaluations: list[dict]) -> dict:
    """
    Agrega as N corridas de uma única query numa taxa de acerto por métrica.

    Recebe a lista de N dicts produzidos por evaluate_query (um por repetição)
    e devolve, para cada métrica, "acertou X de N". Preserva a granularidade
    que a média esconde: 5/5 e 3/5 são coisas diferentes — uma é fiável, a
    outra é instável — e é essa diferença que a Semana 3 foi medir.

    Decisão "simples": aqui guardam-se só os NÚMEROS. O conteúdo de cada
    corrida (tool_args, response_text) vive no raw_results.json, individual.
    """
    n = len(evaluations)

    # Routing — aplicável a todas as corridas
    routing_hits = sum(1 for e in evaluations if e["routing_correct"])

    # Args validity — só conta corridas onde args_valid não é None
    args_evals = [e["args_valid"] for e in evaluations if e["args_valid"] is not None]
    args_hits = sum(1 for v in args_evals if v)

    # Refusal — só conta corridas onde refused_correctly não é None
    refusal_evals = [e["refused_correctly"] for e in evaluations if e["refused_correctly"] is not None]
    refusal_hits = sum(1 for v in refusal_evals if v)

    # Validator save — quantas corridas o validador bloqueou
    validator_saves = sum(1 for e in evaluations if e["validator_saved"])

    return {
        "id": query_def["id"],
        "category": query_def["category"],
        "repeats": n,
        "routing": {"hits": routing_hits, "total": n},
        "args_validity": (
            {"hits": args_hits, "total": len(args_evals)} if args_evals else None
        ),
        "refusal": (
            {"hits": refusal_hits, "total": len(refusal_evals)} if refusal_evals else None
        ),
        "validator_saves": validator_saves,
    }

# ═══════════════════════════════════════════════════════════════════════════
# Agregação — camada 2: juntar as queries agregadas numa métrica global.
# ═══════════════════════════════════════════════════════════════════════════

def compute_metrics(aggregated: list[dict]) -> dict:
    """
    Agrega as queries (já agregadas por aggregate_query) em métricas globais.

    Camada 2 de 2. A camada 1 (aggregate_query) juntou N corridas → 1 query.
    Esta junta N queries → 1 número global. Duas camadas separadas: quando
    uma métrica global parecer estranha, sabes em qual olhar.

    A métrica global é a soma dos hits a dividir pela soma dos totals —
    ou seja, "no total, quantas corridas acertaram". Uma query instável
    (3/5) puxa o global para baixo proporcionalmente, como deve.
    """
    total_queries = len(aggregated)

    # M1 — Routing accuracy: soma de hits / soma de totals, sobre todas as queries
    routing_hits = sum(q["routing"]["hits"] for q in aggregated)
    routing_total = sum(q["routing"]["total"] for q in aggregated)
    routing_acc = routing_hits / routing_total if routing_total else 0

    # M2 — Args validity: só queries onde a métrica é aplicável
    args_hits = sum(q["args_validity"]["hits"] for q in aggregated if q["args_validity"])
    args_total = sum(q["args_validity"]["total"] for q in aggregated if q["args_validity"])
    args_acc = args_hits / args_total if args_total else None

    # M3 — Refusal accuracy
    refusal_hits = sum(q["refusal"]["hits"] for q in aggregated if q["refusal"])
    refusal_total = sum(q["refusal"]["total"] for q in aggregated if q["refusal"])
    refusal_acc = refusal_hits / refusal_total if refusal_total else None

    # M4 — Validator save rate: total de saves / total de corridas que falharam routing
    validator_saves = sum(q["validator_saves"] for q in aggregated)
    routing_misses = routing_total - routing_hits
    save_rate = (validator_saves / routing_misses) if routing_misses > 0 else None

    # Por categoria — agora em taxas, não contagens de uma corrida
    by_category = {}
    for q in aggregated:
        cat = q["category"]
        by_category.setdefault(cat, {"routing_hits": 0, "routing_total": 0})
        by_category[cat]["routing_hits"] += q["routing"]["hits"]
        by_category[cat]["routing_total"] += q["routing"]["total"]

    for cat in by_category:
        b = by_category[cat]
        b["accuracy"] = b["routing_hits"] / b["routing_total"] if b["routing_total"] else 0

    return {
        "total_queries": total_queries,
        "routing_accuracy": round(routing_acc, 3),
        "args_validity": round(args_acc, 3) if args_acc is not None else None,
        "refusal_accuracy": round(refusal_acc, 3) if refusal_acc is not None else None,
        "validator_save_rate": round(save_rate, 3) if save_rate is not None else None,
        "by_category": by_category,
    }

# ═══════════════════════════════════════════════════════════════════════════
# Geração do summary em markdown
# ═══════════════════════════════════════════════════════════════════════════

def generate_summary(version: str, metrics: dict, aggregated: list[dict]) -> str:
    """Gera relatório markdown do eval."""
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
        f"| Args validity | {metrics['args_validity']*100:.1f}% |" if metrics['args_validity'] is not None else "| Args validity | N/A |",
        f"| Refusal accuracy | {metrics['refusal_accuracy']*100:.1f}% |" if metrics['refusal_accuracy'] is not None else "| Refusal accuracy | N/A |",
        f"| Validator save rate | {metrics['validator_save_rate']*100:.1f}% |" if metrics['validator_save_rate'] is not None else "| Validator save rate | N/A (sem falhas) |",
        "",
        "## Por categoria",
        "",
        "| Categoria | Acertos | Total | Accuracy |",
        "| --- | --- | --- | --- |",
    ]
    for cat, stats in metrics["by_category"].items():
        lines.append(
            f"| {cat} | {stats['routing_hits']} | {stats['routing_total']} | "
            f"{stats['accuracy']*100:.1f}% |"
        )

    # Taxa por query — onde a instabilidade fica visível.
    # Uma query a 3/5 não é "quase boa" — é instável, e isto mostra-o.
    lines.extend(["", "## Taxa de routing por query", ""])
    lines.append("| Query | Categoria | Routing |")
    lines.append("| --- | --- | --- |")
    for q in aggregated:
        r = q["routing"]
        flag = "" if r["hits"] == r["total"] else " ⚠️" if r["hits"] > 0 else " ❌"
        lines.append(f"| {q['id']} | {q['category']} | {r['hits']}/{r['total']}{flag} |")

    # Queries instáveis em destaque — nem perfeitas nem totalmente falhadas
    unstable = [q for q in aggregated
                if 0 < q["routing"]["hits"] < q["routing"]["total"]]
    lines.extend(["", "## Queries instáveis", ""])
    if not unstable:
        lines.append("Nenhuma query instável — todas 0/N ou N/N.")
    else:
        lines.append("Estas oscilaram entre corridas (nem sempre acertaram, nem sempre falharam):")
        lines.append("")
        for q in unstable:
            r = q["routing"]
            lines.append(f"- **{q['id']}** ({q['category']}): routing {r['hits']}/{r['total']}")

    return "\n".join(lines)

# ═══════════════════════════════════════════════════════════════════════════
# Main
# ═══════════════════════════════════════════════════════════════════════════

def run_eval(version: str, config: AgentConfig, repeats: int):

    output_dir = Path(f"experiments/{version}")
    output_dir.mkdir(parents=True, exist_ok=True)

    # Carregar test set
    with open(TEST_SET_PATH, encoding="utf-8") as f:
        test_set = json.load(f)
    queries = test_set["queries"]

    # raw_results: TODAS as corridas individuais (decisão "completo").
    # aggregated:  uma entrada por query, já com as taxas (camada 1).
    raw_results = []
    aggregated = []
    for i, query_def in enumerate(queries, 1):
        print(f"[{i}/{len(queries)}] {query_def['id']} — {query_def['category']}")
        print(f"  Query: {query_def['query'][:80]}...")

        query_evaluations = []  # as N evaluations desta query

        for rep in range(1, repeats + 1):
            start = time.time()
            try:
                response = run_agent(query_def["query"], config)
                elapsed = time.time() - start
                evaluation = evaluate_query(query_def, response)

                status = "✅" if evaluation["routing_correct"] else "❌"
                print(f"  {status} tool={evaluation['actual_tool']} ({elapsed:.1f}s)")

                query_evaluations.append(evaluation)
                raw_results.append({
                    "query_def": query_def,
                    "repetition": rep,
                    "evaluation": evaluation,
                    "elapsed_seconds": round(elapsed, 2),
                })
            except Exception as e:
                print(f"  ⚠️ ERRO: {e}")
                # Uma corrida que rebenta conta como falha de routing — não
                # se descarta, senão a taxa mente por omissão.
                failed_eval = {
                    "routing_correct": False, "args_valid": None,
                    "refused_correctly": None, "validator_saved": False,
                    "error": str(e),
                }
                query_evaluations.append(failed_eval)
                raw_results.append({
                    "query_def": query_def,
                    "repetition": rep,
                    "evaluation": failed_eval,
                    "elapsed_seconds": 0,
                })

        # Camada 1: as N corridas desta query → taxa por query
        agg = aggregate_query(query_def, query_evaluations)
        aggregated.append(agg)
        print(f"  → routing {agg['routing']['hits']}/{agg['routing']['total']}")            

    # Calcular métricas
    metrics = compute_metrics(aggregated)

    # Gravar artefactos
    config_record  = {
        "version": version,
        "timestamp": datetime.now().isoformat(),
        "test_set": str(TEST_SET_PATH),
        "agent_config": config.to_dict(),
        "repeats": repeats,
        "temperature": 0.0,
    }

    (output_dir / "config.json").write_text(
        json.dumps(config_record , indent=2, ensure_ascii=False), encoding="utf-8"
    )
    (output_dir / "raw_results.json").write_text(
        json.dumps(raw_results, indent=2, ensure_ascii=False, default=str), encoding="utf-8"
    )
    (output_dir / "metrics.json").write_text(
        json.dumps({"global": metrics, "by_query": aggregated}, indent=2, ensure_ascii=False), encoding="utf-8",
    )
    (output_dir / "summary.md").write_text(
        generate_summary(version, metrics, aggregated), encoding="utf-8"
    )

    # Print final
    print("\n" + "="*70)
    print(f"Eval {version} completo")
    print("="*70)
    print(f"Routing accuracy:     {metrics['routing_accuracy']*100:.1f}%")
    if metrics['args_validity'] is not None:
        print(f"Args validity:        {metrics['args_validity']*100:.1f}%")
    if metrics['refusal_accuracy'] is not None:
        print(f"Refusal accuracy:     {metrics['refusal_accuracy']*100:.1f}%")
    if metrics['validator_save_rate'] is not None:
        print(f"Validator save rate:  {metrics['validator_save_rate']*100:.1f}%")
    print(f"\nArtefactos em: {output_dir}/")


if __name__ == "__main__":
    args = parse_args()
    config = AgentConfig(
        model=args.model,
        rewriter_model=args.rewriter_model,
        pre_router_enabled=(args.pre_router == "on"),
    )
    run_eval(version=args.version, config=config, repeats=args.repeats)