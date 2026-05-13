"""
Gate de tool calling — script parametrizado para múltiplas experiências.
 
Uso:
    python experiments/tool_calling_gate.py v1
    python experiments/tool_calling_gate.py v2
 
Cada run cria experiments/day1_v{N}/ com config, raw_results, metrics, summary.
"""
 
import json
import sys
from pathlib import Path
from datetime import datetime
from collections import Counter
import ollama

# ═══════════════════════════════════════════════════════════════════════════
# Componentes partilhados (referenciados por múltiplas experiências)
# ═══════════════════════════════════════════════════════════════════════════

V3_SYSTEM_PROMPT = (
    "És um assistente nutricionista. Tens acesso à ferramenta calcular_imc.\n\n"
    "Regras:\n"
    "1. Chama calcular_imc apenas quando o utilizador fornece peso E altura na mensagem.\n"
    "2. Se faltar algum valor, pede-o em texto.\n"
    "3. Para perguntas gerais de nutrição, responde em texto.\n"
    "4. Nunca inventes valores. Nunca chames a ferramenta com argumentos null.\n\n"
    "Segue o estilo dos exemplos abaixo."
)

V3_FEW_SHOT_MESSAGES = [
    {"role": "user", "content": "Tenho 78kg e 1.82m, qual o meu IMC?"},
    {"role": "assistant", "content": "", "tool_calls": [{
        "function": {
            "name": "calcular_imc",
            "arguments": {"peso_kg": 78, "altura_m": 1.82}
        }
    }]},
    {"role": "user", "content": "Quantas calorias tem uma banana?"},
    {"role": "assistant", "content": (
        "Não tenho informação sobre o conteúdo calórico de alimentos específicos "
        "disponível neste momento. Posso ajudar-te a calcular o IMC se me deres "
        "o peso e altura."
    )},
    {"role": "user", "content": "Calcula o meu IMC"},
    {"role": "assistant", "content": (
        "Para calcular o IMC preciso do teu peso (em kg) e da tua altura "
        "(em metros). Podes dizer-me esses valores?"
    )},
    {"role": "user", "content": "Peso 80kg, qual é o meu IMC?"},
    {"role": "assistant", "content": (
        "Tenho o peso (80 kg) mas falta-me a altura. Podes dizer-me a tua "
        "altura em metros?"
    )},
]

V3_TOOL_SCHEMA = {
    "type": "function",
    "function": {
        "name": "calcular_imc",
        "description": "Calcula o Índice de Massa Corporal (IMC). Chamar apenas quando peso e altura foram ambos fornecidos.",
        "parameters": {
            "type": "object",
            "properties": {
                "peso_kg": {"type": "number", "description": "Peso em quilogramas"},
                "altura_m": {"type": "number", "description": "Altura em metros"},
            },
            "required": ["peso_kg", "altura_m"],
        },
    },
}

V5_FEW_SHOT_MESSAGES = V3_FEW_SHOT_MESSAGES + [
    # Exemplo 5: anti-prior 80 kg em formulação não-canónica
    {"role": "user", "content": "73 kg e 1.65 m, é bom?"},
    {"role": "assistant", "content": "", "tool_calls": [{
        "function": {
            "name": "calcular_imc",
            "arguments": {"peso_kg": 73, "altura_m": 1.65}
        }
    }]},
    # Exemplo 6: anti-hallucination em D com altura primeiro
    {"role": "user", "content": "Qual é o meu IMC? Meço 1.70m"},
    {"role": "assistant", "content": (
        "Tenho a altura (1.70 m) mas falta-me o peso. "
        "Podes dizer-me o teu peso em quilogramas?"
    )},
]
 
 
# ═══════════════════════════════════════════════════════════════════════════
# CONFIGURAÇÃO POR VERSÃO — editar aqui entre experiências
# ═══════════════════════════════════════════════════════════════════════════
 
EXPERIMENTS = {
    "v1": {
        "hypothesis": "Llama 3.2 3B faz tool calling fiável com prompt minimalista",
        "system_prompt": (
            "És um assistente nutricionista. Tens acesso a uma ferramenta para calcular IMC.\n"
            "Usa a ferramenta apenas quando o utilizador pede explícita ou implicitamente o cálculo do IMC E fornece peso e altura.\n"
            "Se faltarem dados, pede-os em vez de inventar valores.\n"
            "Para perguntas gerais sobre nutrição, responde directamente sem usar ferramentas."
        ),
        "tool_schema": {
            "type": "function",
            "function": {
                "name": "calcular_imc",
                "description": "Calcula o Índice de Massa Corporal (IMC) de uma pessoa.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "peso_kg": {"type": "number", "description": "Peso em quilogramas"},
                        "altura_m": {"type": "number", "description": "Altura em metros"},
                    },
                    "required": ["peso_kg", "altura_m"],
                },
            },
        },
    },
    # v2, v3... vão ser adicionados aqui
    "v2": {
        "hypothesis": (
            "Prompt restritivo com regras numeradas + descriptions reforçadas "
            "elimina null_args_call, argument_hallucination, spurious_tool_use"
        ),
        "system_prompt": (
            "És um assistente nutricionista. Tens UMA ferramenta disponível: calcular_imc.\n\n"
            "REGRAS ESTRITAS — segue exactamente:\n\n"
            "1. CHAMA calcular_imc APENAS quando o utilizador menciona EXPLICITAMENTE "
            "os dois valores (peso E altura) na sua mensagem.\n\n"
            "2. Se o utilizador pede IMC mas falta o peso ou a altura (ou ambos), "
            "NÃO chames a ferramenta. Responde em texto a pedir o(s) valor(es) em falta.\n\n"
            "3. Para perguntas gerais de nutrição (alimentos, dietas, calorias, "
            "hidratação, princípios alimentares), NÃO uses ferramentas. "
            "Responde em texto que não tens essa informação disponível neste momento.\n\n"
            "4. NUNCA inventes valores. NUNCA uses 70 kg, 1.70 m, ou qualquer valor "
            "por defeito. Se o utilizador não disse o número, não o uses.\n\n"
            "5. NUNCA chames a ferramenta com argumentos null, vazios, ou com placeholders.\n\n"
            "Antes de chamar a ferramenta, verifica: \"O utilizador escreveu literalmente "
            "o peso E a altura nesta mensagem?\" Se a resposta é não, NÃO chames."
        ),
        "tool_schema": {
            "type": "function",
            "function": {
                "name": "calcular_imc",
                "description": (
                    "Calcula o IMC. APENAS chamar quando peso E altura foram ambos "
                    "mencionados explicitamente pelo utilizador na mensagem actual. "
                    "NÃO chamar se algum valor estiver em falta ou tiver de ser inventado."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "peso_kg": {
                            "type": "number",
                            "description": (
                                "Peso em quilogramas. Valor exacto mencionado pelo "
                                "utilizador. NUNCA inventar."
                            ),
                        },
                        "altura_m": {
                            "type": "number",
                            "description": (
                                "Altura em metros. Valor exacto mencionado pelo "
                                "utilizador. NUNCA inventar."
                            ),
                        },
                    },
                    "required": ["peso_kg", "altura_m"],
                },
            },
        },
    },
    "v3": {
        "hypothesis": (
            "Few-shot com 4 exemplos cirúrgicos (1 por failure mode + caso correcto) "
            "ensina o modelo a abster-se quando deve, complementando o prompt restritivo."
        ),
        "system_prompt": (
            "És um assistente nutricionista. Tens acesso à ferramenta calcular_imc.\n\n"
            "Regras:\n"
            "1. Chama calcular_imc apenas quando o utilizador fornece peso E altura na mensagem.\n"
            "2. Se faltar algum valor, pede-o em texto.\n"
            "3. Para perguntas gerais de nutrição, responde em texto.\n"
            "4. Nunca inventes valores. Nunca chames a ferramenta com argumentos null.\n\n"
            "Segue o estilo dos exemplos abaixo."
        ),
        "few_shot_messages": [
            # Exemplo 1: caso positivo
            {"role": "user", "content": "Tenho 78kg e 1.82m, qual o meu IMC?"},
            {"role": "assistant", "content": "", "tool_calls": [{
                "function": {
                    "name": "calcular_imc",
                    "arguments": {"peso_kg": 78, "altura_m": 1.82}
                }
            }]},
            # Exemplo 2: pergunta de nutrição geral (anti-spurious)
            {"role": "user", "content": "Quantas calorias tem uma banana?"},
            {"role": "assistant", "content": (
                "Não tenho informação sobre o conteúdo calórico de alimentos específicos "
                "disponível neste momento. Posso ajudar-te a calcular o IMC se me deres "
                "o peso e altura."
            )},
            # Exemplo 3: zero dados (anti-hallucination)
            {"role": "user", "content": "Calcula o meu IMC"},
            {"role": "assistant", "content": (
                "Para calcular o IMC preciso do teu peso (em kg) e da tua altura "
                "(em metros). Podes dizer-me esses valores?"
            )},
            # Exemplo 4: dados parciais (anti-null_args)
            {"role": "user", "content": "Peso 80kg, qual é o meu IMC?"},
            {"role": "assistant", "content": (
                "Tenho o peso (80 kg) mas falta-me a altura. Podes dizer-me a tua "
                "altura em metros?"
            )},
        ],
        "tool_schema": {
            "type": "function",
            "function": {
                "name": "calcular_imc",
                "description": "Calcula o Índice de Massa Corporal (IMC). Chamar apenas quando peso e altura foram ambos fornecidos.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "peso_kg": {"type": "number", "description": "Peso em quilogramas"},
                        "altura_m": {"type": "number", "description": "Altura em metros"},
                    },
                    "required": ["peso_kg", "altura_m"],
                },
            },
        },
    },
    "v4": {
        "hypothesis": (
            "Mudar de Llama 3.2 3B para Qwen 2.5 3B (mesmo tamanho mas "
            "function calling treinado nativamente) resolve o limite estrutural "
            "observado em v1-v3, especialmente em categoria D (refusal)."
        ),
        "model": "qwen2.5:3b-instruct",
        # Mantemos prompt e few-shot da v3 — isolamos a variável modelo
        "system_prompt": V3_SYSTEM_PROMPT,
        "few_shot_messages": V3_FEW_SHOT_MESSAGES,
        "tool_schema": V3_TOOL_SCHEMA,
    },
    "v5": {
        "hypothesis": (
            "Adicionar 2 exemplos few-shot ao Qwen 2.5 3B (1 anti-prior 80 em "
            "formulação não-canónica, 1 anti-hallucination em D com altura-primeiro) "
            "resolve os 2 wrong_arguments e empurra refusal acima de 70%."
        ),
        "model": "qwen2.5:3b-instruct",
        "system_prompt": V3_SYSTEM_PROMPT,
        "few_shot_messages": V5_FEW_SHOT_MESSAGES,
        "tool_schema": V3_TOOL_SCHEMA,
    },
}
 
DEFAULT_MODEL = "llama3.2:3b"
GATES = {"selection": 0.85, "extraction": 0.85, "refusal": 0.70}
 
 
# ═══════════════════════════════════════════════════════════════════════════
# Caminhos
# ═══════════════════════════════════════════════════════════════════════════
 
EXPERIMENTS_DIR = Path(__file__).parent
TEST_SET_PATH = EXPERIMENTS_DIR / "test_set.json"
 
 
# ═══════════════════════════════════════════════════════════════════════════
# Harness — corre uma query e regista decisão
# ═══════════════════════════════════════════════════════════════════════════
 
def run_query(query: str, system_prompt: str, tool_schema: dict,
              few_shot_messages: list = None, model: str = DEFAULT_MODEL) -> dict:
    """Corre query contra o modelo. NÃO executa a tool — só observa decisão."""
    messages = [{"role": "system", "content": system_prompt}]
    if few_shot_messages:
        messages.extend(few_shot_messages)
    messages.append({"role": "user", "content": query})

    response = ollama.chat(
        model=model,
        messages=messages,
        tools=[tool_schema],
    )
    message = response["message"]
    tool_calls = message.get("tool_calls", [])

    if tool_calls:
        call = tool_calls[0]
        return {
            "decision": "call",
            "args": dict(call["function"]["arguments"]),
            "text": message.get("content", ""),
        }
    return {
        "decision": "no_call",
        "args": None,
        "text": message.get("content", ""),
    }

# ═══════════════════════════════════════════════════════════════════════════
# Avaliação
# ═══════════════════════════════════════════════════════════════════════════
 
def args_match(expected: dict, actual: dict, tol: float = 0.01) -> bool:
    """Compara args com tolerância numérica e robustez a strings/None."""
    if not expected or not actual:
        return False
    if set(expected.keys()) != set(actual.keys()):
        return False
    try:
        return all(abs(float(actual[k]) - float(expected[k])) < tol for k in expected)
    except (TypeError, ValueError):
        return False
 
 
def classify_failure(case: dict, result: dict) -> str | None:
    """Classifica o tipo de falha — útil para diagnóstico agregado."""
    expected = case["expected_behavior"]
    actual = result["decision"]
 
    if expected == actual:
        # Pode ainda haver falha de extraction
        if expected == "call" and not args_match(case["expected_args"], result["args"]):
            return "wrong_arguments"
        return None  # tudo ok
 
    if expected == "no_call" and actual == "call":
        args = result.get("args") or {}
        # Argumentos null ou vazios
        if all(v is None or v == "null" or v == "<nil>" for v in args.values()):
            return "null_args_call"
        # Categoria D ou C com altura mas sem peso (ou vice-versa) → invenção
        if case["category"] == "D":
            return "argument_hallucination"
        if case["category"] == "C":
            return "spurious_tool_use"
        return "unexpected_call"
 
    if expected == "call" and actual == "no_call":
        return "missed_call"
 
    return "unknown"
 
 
def evaluate(test_set: list, system_prompt: str, tool_schema: dict,
             few_shot_messages: list = None, model: str = DEFAULT_MODEL) -> list:
    results = []
    for i, case in enumerate(test_set, 1):
        print(f"  [{i}/{len(test_set)}] {case['category']}: {case['query'][:60]}...")
        try:
            result = run_query(case["query"], system_prompt, tool_schema,
                               few_shot_messages, model)
        except Exception as e:
            result = {"decision": "error", "args": None, "text": str(e)}
 
        selection_ok = result["decision"] == case["expected_behavior"]
        extraction_ok = (
            args_match(case["expected_args"], result["args"])
            if case["expected_behavior"] == "call" and result["decision"] == "call"
            else None
        )
        refusal_ok = (
            result["decision"] == "no_call" if case["category"] == "D" else None
        )
        failure_mode = classify_failure(case, result)
 
        results.append({
            **case,
            "actual_decision": result["decision"],
            "actual_args": result["args"],
            "actual_text": result["text"][:200],
            "selection_ok": selection_ok,
            "extraction_ok": extraction_ok,
            "refusal_ok": refusal_ok,
            "failure_mode": failure_mode,
        })
    return results
 
 
# ═══════════════════════════════════════════════════════════════════════════
# Métricas e relatórios
# ═══════════════════════════════════════════════════════════════════════════
 
def compute_metrics(results: list) -> dict:
    sel_total = len(results)
    sel_ok = sum(1 for r in results if r["selection_ok"])
 
    ext_cases = [r for r in results if r["extraction_ok"] is not None]
    ext_ok = sum(1 for r in ext_cases if r["extraction_ok"])
 
    ref_cases = [r for r in results if r["refusal_ok"] is not None]
    ref_ok = sum(1 for r in ref_cases if r["refusal_ok"])
 
    per_category = {}
    for cat in ["A", "B", "C", "D"]:
        cat_r = [r for r in results if r["category"] == cat]
        if cat_r:
            per_category[cat] = {
                "n": len(cat_r),
                "selection_ok": sum(1 for r in cat_r if r["selection_ok"]),
                "selection_pct": sum(1 for r in cat_r if r["selection_ok"]) / len(cat_r),
            }
 
    failure_modes = Counter(
        r["failure_mode"] for r in results if r["failure_mode"]
    )
 
    selection_pct = sel_ok / sel_total if sel_total else 0
    extraction_pct = ext_ok / len(ext_cases) if ext_cases else 0
    refusal_pct = ref_ok / len(ref_cases) if ref_cases else 0
 
    return {
        "overall": {
            "selection_accuracy": round(selection_pct, 3),
            "extraction_accuracy": round(extraction_pct, 3),
            "refusal_accuracy": round(refusal_pct, 3),
            "total_queries": sel_total,
        },
        "per_category": per_category,
        "gate_status": {
            "selection": {
                "threshold": GATES["selection"],
                "actual": round(selection_pct, 3),
                "passed": selection_pct >= GATES["selection"],
            },
            "extraction": {
                "threshold": GATES["extraction"],
                "actual": round(extraction_pct, 3),
                "passed": extraction_pct >= GATES["extraction"],
            },
            "refusal": {
                "threshold": GATES["refusal"],
                "actual": round(refusal_pct, 3),
                "passed": refusal_pct >= GATES["refusal"],
            },
        },
        "failure_modes": dict(failure_modes),
    }
 
 
def write_summary_md(experiment_id: str, config: dict, metrics: dict, output_path: Path):
    """Gera summary.md humano-legível."""
    g = metrics["gate_status"]
    overall = metrics["overall"]
 
    def status(passed: bool) -> str:
        return "✅" if passed else "❌"
 
    all_passed = all(v["passed"] for v in g.values())
 
    lines = [
        f"# {experiment_id} — Gate de tool calling",
        "",
        f"**Data:** {config['date']}",
        f"**Modelo:** {config['model']}",
        f"**Hipótese:** {config['hypothesis']}",
        "",
        "## TL;DR",
        "",
        f"Gate **{'PASSOU' if all_passed else 'NÃO passou'}**.",
        "",
        "## Resultados",
        "",
        "| Métrica | Valor | Gate | Status |",
        "|---|---|---|---|",
        f"| Selection | {overall['selection_accuracy']:.0%} | >{g['selection']['threshold']:.0%} | {status(g['selection']['passed'])} |",
        f"| Extraction | {overall['extraction_accuracy']:.0%} | >{g['extraction']['threshold']:.0%} | {status(g['extraction']['passed'])} |",
        f"| Refusal | {overall['refusal_accuracy']:.0%} | >{g['refusal']['threshold']:.0%} | {status(g['refusal']['passed'])} |",
        "",
        "## Por categoria",
        "",
        "| Categoria | Selection | n |",
        "|---|---|---|",
    ]
    for cat, v in metrics["per_category"].items():
        lines.append(f"| {cat} | {v['selection_pct']:.0%} | {v['n']} |")
 
    lines += ["", "## Failure modes", ""]
    if metrics["failure_modes"]:
        lines.append("| Tipo | Contagem |")
        lines.append("|---|---|")
        for mode, count in sorted(metrics["failure_modes"].items(), key=lambda x: -x[1]):
            lines.append(f"| `{mode}` | {count} |")
    else:
        lines.append("Nenhum.")
 
    output_path.write_text("\n".join(lines), encoding="utf-8")
 
 
# ═══════════════════════════════════════════════════════════════════════════
# Orquestração
# ═══════════════════════════════════════════════════════════════════════════
 
def run_experiment(version: str):
    if version not in EXPERIMENTS:
        print(f"Erro: versão '{version}' não definida em EXPERIMENTS.")
        print(f"Disponíveis: {list(EXPERIMENTS.keys())}")
        sys.exit(1)

    exp = EXPERIMENTS[version]
    experiment_id = f"day1_{version}"
    output_dir = EXPERIMENTS_DIR / experiment_id
    output_dir.mkdir(parents=True, exist_ok=True)

    test_set_data = json.loads(TEST_SET_PATH.read_text(encoding="utf-8"))
    test_set = test_set_data["queries"]

    config = {
        "experiment_id": experiment_id,
        "date": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "hypothesis": exp["hypothesis"],
        "model": exp.get("model", DEFAULT_MODEL),
        "test_set_version": test_set_data["version"],
        "test_set_size": len(test_set),
        "system_prompt": exp["system_prompt"],
        "tool_schema": exp["tool_schema"],
        "few_shot_messages": exp.get("few_shot_messages"), 
        "gates": GATES,
    }

    print(f"\n{'='*70}\nA correr {experiment_id} ({len(test_set)} queries)\n{'='*70}")
    results = evaluate(
        test_set,
        exp["system_prompt"],
        exp["tool_schema"],
        exp.get("few_shot_messages"),
        exp.get("model", DEFAULT_MODEL),
    )
    metrics = compute_metrics(results)

    # Escrever os 4 ficheiros
    (output_dir / "config.json").write_text(
        json.dumps(config, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (output_dir / "raw_results.json").write_text(
        json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (output_dir / "metrics.json").write_text(
        json.dumps(metrics, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    write_summary_md(experiment_id, config, metrics, output_dir / "summary.md")

    # Output na consola
    print(f"\n{'='*70}\nRESULTADOS — {experiment_id}\n{'='*70}")
    o = metrics["overall"]
    g = metrics["gate_status"]
    print(f"Selection:  {o['selection_accuracy']:.0%}  (gate >{g['selection']['threshold']:.0%}) "
          f"{'✅' if g['selection']['passed'] else '❌'}")
    print(f"Extraction: {o['extraction_accuracy']:.0%}  (gate >{g['extraction']['threshold']:.0%}) "
          f"{'✅' if g['extraction']['passed'] else '❌'}")
    print(f"Refusal:    {o['refusal_accuracy']:.0%}  (gate >{g['refusal']['threshold']:.0%}) "
          f"{'✅' if g['refusal']['passed'] else '❌'}")
    print(f"\nPor categoria:")
    for cat, v in metrics["per_category"].items():
        print(f"  {cat}: {v['selection_ok']}/{v['n']} ({v['selection_pct']:.0%})")
    if metrics["failure_modes"]:
        print(f"\nFailure modes:")
        for mode, count in sorted(metrics["failure_modes"].items(), key=lambda x: -x[1]):
            print(f"  {mode}: {count}")

    print(f"\nResultados em: {output_dir}/")
 
if __name__ == "__main__":
    version = sys.argv[1] if len(sys.argv) > 1 else "v1"
    run_experiment(version)