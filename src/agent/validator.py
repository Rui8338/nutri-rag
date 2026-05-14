"""
Validador a jusante para detectar argumentos numéricos inventados pelo LLM.

Estratégia:
- Extrair todos os números da query original do utilizador
- Para cada arg numérico do tool call, verificar se pode ser explicado por algum
  número da query (incluindo conversões comuns: metros→cm)
- Args string são ignorados (LLM raramente os inventa, e validar semanticamente
  é difícil sem outro LLM)

Princípio: detectar SÓ onde o problema é real. Tentar validar tudo cria falsos
positivos e fricção desnecessária.
"""

import re


# Tolerância para comparação numérica (ex: 1.78 metros vs 178 cm)
NUMERIC_TOLERANCE = 0.5

# Args numéricos que devemos validar (lista permissiva — qualquer arg numérico
# que apareça em qualquer tool é candidato)
NUMERIC_ARG_NAMES = {
    "idade", "peso_kg", "altura_cm", "altura_m",
    "tdee", "calorias",
}


def extract_numbers_from_query(query: str) -> list[float]:
    """
    Extrai todos os números da query do utilizador.

    Suporta:
    - Inteiros: 75, 178, 30
    - Decimais com ponto: 1.75, 70.5
    - Decimais com vírgula portuguesa: 1,75 → tratada como 1.75
    """
    pattern = r'\d+(?:[.,]\d+)?'
    matches = re.findall(pattern, query)
    numbers = []
    for m in matches:
        normalized = m.replace(',', '.')
        try:
            numbers.append(float(normalized))
        except ValueError:
            continue
    return numbers


def number_explained_by_query(value: float, query_numbers: list[float]) -> bool:
    """
    Verifica se `value` (arg do tool call) pode ser explicado por algum número
    presente na query.

    Considera:
    - Match directo (com tolerância pequena)
    - Conversão metros → cm (1.75 na query → 175 no arg)
    - Conversão cm → metros (175 na query → 1.75 no arg)
    """
    for q_num in query_numbers:
        # Match directo
        if abs(value - q_num) < NUMERIC_TOLERANCE:
            return True
        # Conversão: query em metros, arg em cm (1.78 → 178)
        if abs(value - q_num * 100) < NUMERIC_TOLERANCE:
            return True
        # Conversão: query em cm, arg em metros (178 → 1.78)
        if abs(value - q_num / 100) < NUMERIC_TOLERANCE * 0.01:
            return True
    return False


def validate_tool_call(
    tool_name: str,
    args: dict,
    user_query: str,
) -> tuple[bool, list[str]]:
    """
    Valida se os args de um tool call são suportados pela query do utilizador.

    Args:
        tool_name: nome da tool (não usado por agora, mas reservado para
                   regras específicas por tool no futuro)
        args: dicionário de argumentos do tool call
        user_query: query original do utilizador

    Returns:
        (is_valid, suspicious_args)
        - is_valid: True se todos os args numéricos são suportados pela query
        - suspicious_args: lista de nomes de args que parecem inventados
                          (vazia se is_valid=True)
    """
    query_numbers = extract_numbers_from_query(user_query)
    suspicious = []

    for arg_name, arg_value in args.items():
        # Só validamos args numéricos conhecidos
        if arg_name not in NUMERIC_ARG_NAMES:
            continue

        # Tentar converter para float (LLM pode mandar string ou número)
        try:
            numeric_value = float(arg_value)
        except (TypeError, ValueError):
            # Não é numérico — ignorar (não é caso de hallucination)
            continue

        if not number_explained_by_query(numeric_value, query_numbers):
            suspicious.append(arg_name)

    return (len(suspicious) == 0, suspicious)


def format_validation_message(suspicious_args: list[str], tool_name: str) -> str:
    """
    Gera mensagem amigável para o utilizador quando validação falha.

    Em vez de erro técnico, traduz para "preciso desta informação".
    """
    if not suspicious_args:
        return ""

    # Tradução de nomes técnicos para português natural
    pretty_names = {
        "idade": "idade",
        "peso_kg": "peso",
        "altura_cm": "altura",
        "altura_m": "altura",
        "tdee": "TDEE (calorias diárias)",
        "calorias": "calorias",
    }

    pretty = [pretty_names.get(a, a) for a in suspicious_args]
    if len(pretty) == 1:
        return f"Para te ajudar, podes dizer-me a tua {pretty[0]}?"
    elif len(pretty) == 2:
        return f"Para te ajudar, podes dizer-me a tua {pretty[0]} e {pretty[1]}?"
    else:
        all_but_last = ", ".join(pretty[:-1])
        return f"Para te ajudar, podes dizer-me: {all_but_last} e {pretty[-1]}?"
    
def validate_required_args(
    args: dict,
    tool_schema: dict,
) -> tuple[bool, list[str]]:
    """
    Verifica se todos os args 'required' do schema estão presentes em args.

    Diferente de validate_tool_call:
    - validate_tool_call valida valores (numéricos inventados)
    - validate_required_args valida estrutura (campos em falta)

    Args:
        args: dict de argumentos extraídos pelo LLM
        tool_schema: schema JSON da tool (formato Ollama)

    Returns:
        (is_complete, missing_args)
    """
    required = tool_schema.get("function", {}).get("parameters", {}).get("required", [])
    missing = [name for name in required if name not in args]
    return (len(missing) == 0, missing)


def format_missing_args_message(missing_args: list[str], tool_name: str) -> str:
    """
    Gera mensagem amigável quando args required estão em falta.

    Distingue de format_validation_message (que trata valores inventados):
    aqui o problema é o LLM ter omitido campos, não inventado valores.
    """
    if not missing_args:
        return ""

    pretty_names = {
        "idade": "idade",
        "peso_kg": "peso",
        "altura_cm": "altura",
        "sexo": "sexo (masculino/feminino)",
        "fator_atividade": "nível de atividade física",
        "perfil_atividade": "perfil de atividade (sedentário/ativo/atleta)",
        "objetivo": "objetivo (perder/manter/ganhar peso)",
        "tdee": "TDEE (calorias diárias)",
        "query": "nome do alimento",
    }

    pretty = [pretty_names.get(a, a) for a in missing_args]
    if len(pretty) == 1:
        return f"Para te ajudar, podes dizer-me {pretty[0]}?"
    elif len(pretty) == 2:
        return f"Para te ajudar, faltam-me {pretty[0]} e {pretty[1]}."
    else:
        all_but_last = ", ".join(pretty[:-1])
        return f"Para te ajudar, faltam-me: {all_but_last} e {pretty[-1]}."