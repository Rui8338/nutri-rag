"""
Router rule-based: detecta perguntas factuais sobre nutrição antes do LLM
decidir tools.

Razão: Qwen 2.5 3B não generaliza para a 4ª tool (RAG) mesmo com few-shot
explícito. Esta camada força routing para search_nutrition_principles em
queries claramente factuais.

Filosofia: pre-routing simples (keyword matching). Não é o LLM a decidir,
é o sistema a impor.

Para queries que NÃO são factuais, o LLM mantém o seu poder de decisão
entre as 3 tools determinísticas.
"""

import re
import ollama


# Keywords que sinalizam pergunta factual sobre nutrição.
# Lista deliberadamente pequena — falsos positivos custam mais do que falsos
# negativos (se classifica errado, o LLM acaba a chamar RAG; se omite, o LLM
# continua a fazer o que faria antes).
FACTUAL_KEYWORDS = [
    # Perguntas sobre benefícios/efeitos
    "benefício", "benefícios", "vantagens", "desvantagens",
    "efeito", "efeitos", "consequências",
    # Perguntas factuais directas
    "é verdade", "é mito", "é mau", "é bom", "faz mal", "faz bem",
    # Perguntas explicativas
    "o que são", "o que é", "como é metabolizada", "como funciona",
    # Recomendações
    "devo comer", "devo evitar", "devo consumir", "quanto devo",
    "recomendações", "recomendado",
    # Princípios nutricionais
    "princípios", "diretrizes",
]


# Padrões que indicam pergunta sobre UM alimento específico (NÃO usar RAG)
# Estes têm prioridade — se a query é sobre um alimento, vai para lookup_food.
FOOD_LOOKUP_PATTERNS = [
    r"\bcalorias d[aoe]\s+\w+",        # "calorias da banana"
    r"\bproteína d[aoe]\s+\w+",
    r"\bgordura[s]? d[aoe]\s+\w+",
    r"\bhidratos d[aoe]\s+\w+",
    r"\bfibra d[aoe]\s+\w+",
    r"\bnutricional d[aoe]\s+\w+",
    r"\btem\s+(?:o|a|os|as)\s+\w+",   # "tem a banana", "tem o frango"
]


# Padrões que indicam cálculo (NÃO usar RAG)
CALCULATION_PATTERNS = [
    r"\bquantas calorias devo (?:comer|consumir|ingerir)",
    r"\bcalcula\s+(?:o\s+)?(?:meu\s+)?(?:tdee|macros?)",
    r"\bqual\s+(?:é\s+)?(?:o\s+)?meu tdee",
    r"\bdistribuição (?:de\s+)?macros?",
]


def is_factual_question(query: str) -> bool:
    """
    Determina se uma query é factual sobre nutrição (deve ir para RAG).

    Lógica:
    1. Se parece pergunta sobre alimento específico (lookup_food) → False
    2. Se parece pedido de cálculo (TDEE/macros) → False
    3. Se contém keyword factual → True
    4. Default → False (deixa o LLM decidir)
    """
    query_lower = query.lower()

    # Prioridade 1: pergunta sobre alimento específico
    for pattern in FOOD_LOOKUP_PATTERNS:
        if re.search(pattern, query_lower):
            return False

    # Prioridade 2: pedido de cálculo
    for pattern in CALCULATION_PATTERNS:
        if re.search(pattern, query_lower):
            return False

    # Prioridade 3: keyword factual
    for keyword in FACTUAL_KEYWORDS:
        if keyword in query_lower:
            return True

    # Default: deixar LLM decidir (queries ambíguas ou não cobertas)
    return False

# ═══════════════════════════════════════════════════════════════════════════
# Query rewriting para RAG via LLM
# ═══════════════════════════════════════════════════════════════════════════

REWRITER_MODEL = "qwen2.5:3b-instruct"

# Prompt para o rewriter. Mantido curto e directo — o modelo 3B perde-se em
# instruções longas. Few-shot de 3 exemplos ensina o padrão sem ambiguidade.
REWRITER_SYSTEM = (
    "És um sistema de query rewriting para retrieval em literatura científica "
    "de nutrição em português. Recebes uma pergunta de utilizador e devolves "
    "uma versão optimizada para pesquisa semântica.\n\n"
    "REGRAS:\n"
    "- Devolve APENAS a query reformulada, sem aspas, sem explicações, sem prefixos.\n"
    "- Expande termos coloquiais para termos técnicos (ex: 'hidratos' → 'hidratos de carbono').\n"
    "- Remove palavras conversacionais ('é verdade que', 'devo', 'faz mal').\n"
    "- Adiciona termos técnicos relevantes que podem aparecer em literatura científica.\n"
    "- Mantém entre 3 e 8 palavras-chave."
)

REWRITER_EXAMPLES = [
    {"role": "user", "content": "É verdade que comer hidratos à noite faz mal?"},
    {"role": "assistant", "content": "hidratos de carbono consumo noturno recomendações"},
    {"role": "user", "content": "Quais são os benefícios da fibra alimentar?"},
    {"role": "assistant", "content": "fibra alimentar benefícios saúde digestiva"},
    {"role": "user", "content": "Devo evitar açúcar?"},
    {"role": "assistant", "content": "açúcar consumo recomendações saúde"},
]


# Fallback rule-based (mantido para casos em que o LLM falha)
_FALLBACK_STOPWORDS = {
    "é", "será", "que", "se", "como", "verdade", "mito",
    "devo", "posso", "pode", "deves",
    "faz", "mal", "bem", "bom", "mau",
    "o", "a", "os", "as", "um", "uma",
    "de", "da", "do", "das", "dos", "no", "na", "em",
    "eu", "tu", "meu", "minha", "teu", "tua",
}


def _fallback_rewrite(user_query: str) -> str:
    """Fallback rule-based usado se o LLM rewriter falhar."""
    query = user_query.lower()
    query = re.sub(r"[?!.,;:]", "", query)
    tokens = query.split()
    tokens = [t for t in tokens if t not in _FALLBACK_STOPWORDS and len(t) > 1]
    rewritten = " ".join(tokens)
    return rewritten if len(rewritten.split()) >= 2 else user_query.strip()


def rewrite_query_for_rag(user_query: str) -> str:
    """
    Reformula query do utilizador para optimizar retrieval semântico.

    Usa LLM (Qwen 2.5 3B) com prompt + few-shot. Se LLM falhar ou devolver
    output suspeito (vazio, demasiado longo, contém artefactos), usa fallback
    rule-based.

    Args:
        user_query: pergunta original do utilizador.

    Returns:
        Query reformulada (3-8 palavras técnicas) optimizada para retrieval.
    """
    if not user_query or not user_query.strip():
        return user_query

    messages = [
        {"role": "system", "content": REWRITER_SYSTEM},
        *REWRITER_EXAMPLES,
        {"role": "user", "content": user_query.strip()},
    ]

    try:
        response = ollama.chat(
            model=REWRITER_MODEL,
            messages=messages,
            options={"temperature": 0.0},
        )
        rewritten = response["message"].get("content", "").strip()

        # Validação do output — defesa contra alucinações do rewriter
        if not rewritten:
            return _fallback_rewrite(user_query)

        # Remover aspas se o LLM as adicionou apesar das instruções
        rewritten = rewritten.strip('"\'')

        word_count = len(rewritten.split())
        # Se output for absurdo (vazio, demasiado curto/longo) → fallback
        if word_count < 2 or word_count > 15:
            return _fallback_rewrite(user_query)

        # Se output contiver prefixos comuns de "explanation" (LLM ignora instrução)
        suspicious_prefixes = ["query:", "reformulação:", "resposta:", "aqui está"]
        if any(rewritten.lower().startswith(p) for p in suspicious_prefixes):
            return _fallback_rewrite(user_query)

        return rewritten

    except Exception:
        # Qualquer erro de Ollama → fallback rule-based, agent continua a funcionar
        return _fallback_rewrite(user_query)