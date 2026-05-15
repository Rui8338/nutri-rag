"""
Agent loop single-step: orquestra LLM + tools + validador.

Fluxo:
1. Pre-router: queries factuais → RAG (com query rewriting LLM-based)
2. LLM recebe query + schemas (queries não-factuais)
3. Se LLM responde em texto → devolver
4. Se LLM chama tool: validar args → executar → 2ª chamada LLM com resultado
"""

from dataclasses import dataclass, field
from typing import Any
import ollama

from src.agent.schemas import ALL_SCHEMAS
from src.agent.prompts import SYSTEM_PROMPT, FEW_SHOT_MESSAGES
from src.agent.validator import (
    validate_tool_call,
    format_validation_message,
    validate_required_args,
    format_missing_args_message,
)
from src.agent.router import is_factual_question, rewrite_query_for_rag
from src.tools.nutrition_calc import calculate_tdee, calculate_macros
from src.tools.food_lookup import lookup_food
from src.tools.rag_search import search_nutrition_principles
from src.agent.config import AgentConfig, DEFAULT_CONFIG


# Mapa de nome → função Python real
# Mapa de nome → metadados da tool
TOOL_REGISTRY = {
    "calculate_tdee": {
        "fn": calculate_tdee,
        "no_result_message": None,  # nunca devolve None
    },
    "calculate_macros": {
        "fn": calculate_macros,
        "no_result_message": None,  # nunca devolve None
    },
    "lookup_food": {
        "fn": lookup_food,
        "no_result_message": (
            "Não encontrei esse alimento na base de dados INSA. "
            "Podes tentar com um nome diferente?"
        ),
    },
    "search_nutrition_principles": {
        "fn": search_nutrition_principles,
        "no_result_message": (
            "Não encontrei conteúdo relevante sobre essa pergunta na base "
            "de conhecimento. Posso ajudar-te com cálculos de TDEE, "
            "distribuição de macros, ou informação nutricional de "
            "alimentos específicos."
        ),
    },
}


@dataclass
class AgentResponse:
    """Resposta rica do agente — texto final + metadados para observabilidade."""
    text: str
    tool_used: str | None = None
    tool_args: dict | None = None
    tool_result: Any = None
    validation_failed: bool = False
    suspicious_args: list[str] = field(default_factory=list)
    error: str | None = None


def _coerce_arg(value: Any) -> Any:
    """
    Converte valores que o LLM mandou para tipos Python apropriados.

    Aceita int, float, ou string convertível. Mantém strings categóricas
    (como 'masculino', 'moderado') intactas.
    """
    if isinstance(value, (int, float)):
        return value
    if isinstance(value, str):
        # Normalizar vírgula portuguesa
        normalized = value.replace(',', '.').strip()
        # Tentar int primeiro, depois float
        try:
            if '.' not in normalized:
                return int(normalized)
            return float(normalized)
        except ValueError:
            # Não é número — devolver string original (ex: "masculino")
            return value
    return value


def _coerce_args(args: dict) -> dict:
    """Aplica _coerce_arg a todos os args do tool call."""
    return {k: _coerce_arg(v) for k, v in args.items()}

def _run_rag_search(user_query: str, config: AgentConfig) -> tuple[Any, dict]:
    """
    Caminho único da tool RAG: reformula a query e procura nos chunks.

    Existe para a reformulação ser propriedade do CAMINHO DA TOOL RAG, não
    do branch do pre-router. Antes do refactor, rewrite_query_for_rag só
    corria dentro do pre-router — se o LLM escolhesse a tool RAG sozinho
    (ou o pre-router estivesse desligado), a query chegava crua ao retrieval
    e os scores afundavam abaixo do threshold (Dia 4: cru ~0.40, reformulado ~0.65).

    Chamado pelos DOIS sítios que levam à tool RAG:
    - branch do pre-router (queries factuais detectadas por keyword)
    - branch do LLM (LLM escolheu search_nutrition_principles)

    Returns:
        (tool_result, rag_args) — tool_result são os chunks (ou None se nada
        acima do threshold); rag_args é o dict de metadados para a AgentResponse.
    """
    rag_query = rewrite_query_for_rag(user_query, config.rewriter_model)
    tool_result = search_nutrition_principles(rag_query)
    rag_args = {"query": rag_query, "original_query": user_query}
    return tool_result, rag_args


def run_agent(user_query: str, config: AgentConfig | None = None) -> AgentResponse:
    """
    Executa um turno do agente para a query do utilizador.

    Args:
        user_query: pergunta do utilizador em linguagem natural.

    Returns:
        AgentResponse com texto final + metadados para debug/eval.
    """
    if config is None:
        config = DEFAULT_CONFIG

    # 1. Construir messages
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        *FEW_SHOT_MESSAGES,
        {"role": "user", "content": user_query},
    ]

    # 1.5 Pre-router: queries factuais → RAG directo
    if config.pre_router_enabled and is_factual_question(user_query):
        tool_result, rag_args = _run_rag_search(user_query, config)

        if tool_result is None:
            return AgentResponse(
                text=(
                    "Não encontrei conteúdo relevante na base de conhecimento "
                    "sobre essa pergunta. Posso ajudar-te com cálculos de TDEE, "
                    "distribuição de macros, ou informação nutricional de "
                    "alimentos específicos."
                ),
                tool_used="search_nutrition_principles",
                tool_args=rag_args,
                tool_result=None,
            )

        # Há chunks — passa ao LLM para gerar resposta natural com citações
        messages.append({
            "role": "tool",
            "content": str(tool_result),
            "name": "search_nutrition_principles",
        })

        try:
            final_response = ollama.chat(
                model=config.model,
                messages=messages,
                options={"temperature": 0.0},
            )
        except Exception as e:
            return AgentResponse(
                text=f"Erro a gerar resposta: {e}",
                tool_used="search_nutrition_principles",
                tool_args=rag_args,
                tool_result=tool_result,
                error=str(e),
            )

        return AgentResponse(
            text=final_response["message"].get("content", ""),
            tool_used="search_nutrition_principles",
            tool_args=rag_args,
            tool_result=tool_result,
        )
    
    # 2. Primeira chamada ao LLM
    try:
        response = ollama.chat(
            model=config.model,
            messages=messages,
            tools=ALL_SCHEMAS,
            options={"temperature": 0.0},
        )
    except Exception as e:
        return AgentResponse(
            text=f"Erro ao contactar o modelo: {e}",
            error=str(e),
        )

    message = response["message"]
    tool_calls = message.get("tool_calls", [])

    # 3a. LLM respondeu em texto (sem tool)
    if not tool_calls:
        return AgentResponse(text=message.get("content", ""))

    # 3b. LLM chamou tool — processar
    call = tool_calls[0]  # single-step: ignoramos múltiplas
    tool_name = call["function"]["name"]
    raw_args = dict(call["function"]["arguments"])

    # Validador a jusante
    is_valid, suspicious = validate_tool_call(tool_name, raw_args, user_query)
    if not is_valid:
        return AgentResponse(
            text=format_validation_message(suspicious, tool_name),
            tool_used=tool_name,
            tool_args=raw_args,
            validation_failed=True,
            suspicious_args=suspicious,
        )
    
        # Validação de completude — args required estão presentes?
    tool_schema = next(
        (s for s in ALL_SCHEMAS if s["function"]["name"] == tool_name),
        None,
    )
    if tool_schema is not None:
        is_complete, missing = validate_required_args(raw_args, tool_schema)
        if not is_complete:
            return AgentResponse(
                text=format_missing_args_message(missing, tool_name),
                tool_used=tool_name,
                tool_args=raw_args,
                validation_failed=True,
                suspicious_args=missing,
            )

    # Validar que a tool existe
    if tool_name not in TOOL_REGISTRY:
        return AgentResponse(
            text=f"Erro interno: tool '{tool_name}' não está registada.",
            tool_used=tool_name,
            tool_args=raw_args,
            error=f"Unknown tool: {tool_name}",
        )
    
    if tool_name == "search_nutrition_principles":
        tool_result, rag_args = _run_rag_search(user_query, config)

        if tool_result is None:
            return AgentResponse(
                text=TOOL_REGISTRY[tool_name]["no_result_message"],
                tool_used=tool_name,
                tool_args=rag_args,
                tool_result=None,
            )

        messages.append({
            "role": "assistant",
            "content": "",
            "tool_calls": [call],
        })
        messages.append({
            "role": "tool",
            "content": str(tool_result),
            "name": tool_name,
        })

        try:
            final_response = ollama.chat(
                model=config.model,
                messages=messages,
                options={"temperature": 0.0},
            )
        except Exception as e:
            return AgentResponse(
                text=f"Tool executada mas erro a gerar resposta final: {e}",
                tool_used=tool_name,
                tool_args=rag_args,
                tool_result=tool_result,
                error=str(e),
            )

        return AgentResponse(
            text=final_response["message"].get("content", ""),
            tool_used=tool_name,
            tool_args=rag_args,
            tool_result=tool_result,
        )

    # Conversão de tipos
    try:
        coerced_args = _coerce_args(raw_args)
    except Exception as e:
        return AgentResponse(
            text=f"Erro a interpretar os valores: {e}",
            tool_used=tool_name,
            tool_args=raw_args,
            error=str(e),
        )

    # Executar tool
    try:
        tool_result = TOOL_REGISTRY[tool_name]["fn"](**coerced_args)
    except ValueError as e:
        # Erro de domínio (ex: combinação inviável de macros)
        return AgentResponse(
            text=f"Não consegui calcular: {e}",
            tool_used=tool_name,
            tool_args=coerced_args,
            error=str(e),
        )
    except Exception as e:
        return AgentResponse(
            text="Ocorreu um erro inesperado ao executar a ferramenta.",
            tool_used=tool_name,
            tool_args=coerced_args,
            error=str(e),
        )

    # Tool devolveu None — usar mensagem específica da tool, ou fallback genérico
    if tool_result is None:
        msg = TOOL_REGISTRY[tool_name].get("no_result_message")
        return AgentResponse(
            text=msg or "A ferramenta não devolveu resultado utilizável.",
            tool_used=tool_name,
            tool_args=coerced_args,
            tool_result=None,
        )

    # 4. Segunda chamada ao LLM com resultado da tool
    messages.append({
        "role": "assistant",
        "content": "",
        "tool_calls": [call],
    })
    messages.append({
        "role": "tool",
        "content": str(tool_result),
        "name": tool_name,
    })

    try:
        final_response = ollama.chat(
            model=config.model,
            messages=messages,
            options={"temperature": 0.0},
        )
    except Exception as e:
        return AgentResponse(
            text=f"Tool executada mas erro a gerar resposta final: {e}",
            tool_used=tool_name,
            tool_args=coerced_args,
            tool_result=tool_result,
            error=str(e),
        )

    return AgentResponse(
        text=final_response["message"].get("content", ""),
        tool_used=tool_name,
        tool_args=coerced_args,
        tool_result=tool_result,
    )