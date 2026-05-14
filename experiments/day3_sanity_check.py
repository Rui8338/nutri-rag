"""
Sanity check funcional do agent loop — 4 queries cobrindo os 4 caminhos.

Não é um teste formal. É um smoke test para confirmar que cada caminho
do agente funciona com input limpo antes de investir no eval formal.
"""

from src.agent.loop import run_agent


SANITY_QUERIES = [
    {
        "label": "TDEE com dados completos",
        "query": (
            "Quantas calorias devo comer? Tenho 30 anos, sou homem, "
            "peso 75kg, 178cm, treino moderado."
        ),
        "expected_tool": "calculate_tdee",
    },
    {
        "label": "Lookup de alimento existente",
        "query": "Quantas calorias tem o arroz cozido?",
        "expected_tool": "lookup_food",
    },
    {
        "label": "Macros com TDEE dado",
        "query": (
            "O meu TDEE é 2400 kcal, peso 70kg, sou ativo "
            "e quero manter o peso. Quanta proteína devo comer por dia?"
        ),
        "expected_tool": "calculate_macros",
    },
    {
        "label": "Pergunta geral sem ferramenta",
        "query": "Devo comer hidratos à noite?",
        "expected_tool": None,  # não deve chamar tool
    },
]


def run_sanity_check():
    for i, case in enumerate(SANITY_QUERIES, 1):
        print(f"\n{'='*70}")
        print(f"[{i}/{len(SANITY_QUERIES)}] {case['label']}")
        print(f"{'='*70}")
        print(f"Query: {case['query']}")
        print(f"Tool esperada: {case['expected_tool']}")
        print()

        response = run_agent(case["query"])

        # Diagnóstico
        tool_match = response.tool_used == case["expected_tool"]
        status = "✅" if tool_match else "❌"

        print(f"Tool usada: {response.tool_used} {status}")
        if response.tool_args:
            print(f"Args: {response.tool_args}")
        if response.tool_result is not None:
            # Truncar resultado para não poluir output
            result_str = str(response.tool_result)[:200]
            print(f"Resultado da tool: {result_str}")
        if response.validation_failed:
            print(f"⚠️ Validação falhou — args suspeitos: {response.suspicious_args}")
        if response.error:
            print(f"⚠️ Erro: {response.error}")
        print()
        print(f"Resposta final ao utilizador:")
        print(f"  {response.text[:300]}")


if __name__ == "__main__":
    run_sanity_check()