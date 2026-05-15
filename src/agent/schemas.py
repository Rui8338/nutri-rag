"""
JSON schemas para as 3 tools de produção, formatados para Ollama function calling.

Princípios de design das descriptions:
1. Diz QUANDO usar, não só o que faz
2. Diz QUANDO NÃO usar (delimita fronteiras vs outras tools)
3. Para parâmetros, indica unidades e formato esperado
4. Reforça "valores fornecidos pelo utilizador" para combater hallucination
"""

# ═══════════════════════════════════════════════════════════════════════════
# Schema 1: calculate_tdee
# ═══════════════════════════════════════════════════════════════════════════

CALCULATE_TDEE_SCHEMA = {
    "type": "function",
    "function": {
        "name": "calculate_tdee",
        "description": (
            "Calcula as calorias diárias necessárias (TDEE - Total Daily Energy Expenditure) "
            "para uma pessoa, com base em idade, peso, altura, sexo e nível de atividade física. "
            "Usar quando o utilizador pergunta quantas calorias deve consumir, qual é o seu gasto "
            "calórico diário, ou pede um plano alimentar (que precisa do TDEE como base). "
            "NÃO usar para procurar calorias de alimentos específicos (usar lookup_food) "
            "nem para calcular distribuição de macronutrientes (usar calculate_macros, "
            "que recebe o TDEE já calculado)."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "idade": {
                    "type": "integer",
                    "description": "Idade em anos. Valor inteiro fornecido pelo utilizador.",
                },
                "peso_kg": {
                    "type": "number",
                    "description": "Peso em quilogramas. Valor fornecido pelo utilizador.",
                },
                "altura_cm": {
                    "type": "number",
                    "description": (
                        "Altura em CENTÍMETROS (não metros). "
                        "Se o utilizador disser '1.75m', converter para 175."
                    ),
                },
                "sexo": {
                    "type": "string",
                    "enum": ["masculino", "feminino"],
                    "description": "Sexo biológico (afecta a fórmula). Apenas 'masculino' ou 'feminino'.",
                },
                "fator_atividade": {
                    "type": "string",
                    "enum": ["sedentario", "ligeiro", "moderado", "intenso", "muito_intenso"],
                    "description": (
                        "Nível de atividade física semanal:\n"
                        "- sedentario: pouco ou nenhum exercício\n"
                        "- ligeiro: exercício leve 1-3 dias/semana\n"
                        "- moderado: exercício moderado 3-5 dias/semana\n"
                        "- intenso: exercício intenso 6-7 dias/semana\n"
                        "- muito_intenso: atletas ou trabalho físico"
                    ),
                },
            },
            "required": ["idade", "peso_kg", "altura_cm", "sexo", "fator_atividade"],
        },
    },
}


# ═══════════════════════════════════════════════════════════════════════════
# Schema 2: calculate_macros
# ═══════════════════════════════════════════════════════════════════════════

CALCULATE_MACROS_SCHEMA = {
    "type": "function",
    "function": {
        "name": "calculate_macros",
        "description": (
            "Calcula a distribuição diária de macronutrientes (proteína, hidratos, gorduras) "
            "em gramas para um plano alimentar, a partir de um TDEE já calculado. "
            "Usar quando o utilizador quer saber quanta proteína/hidratos/gorduras consumir "
            "POR DIA no total, ou pede a distribuição de macros do plano. "
            "Esta tool RECEBE o TDEE - não o calcula. Se ainda não tens TDEE, "
            "usa primeiro calculate_tdee. "
            "NÃO usar para procurar conteúdo nutricional de UM alimento específico "
            "(ex: 'quantas calorias tem a banana?', 'a maçã tem fibra?') — "
            "para isso usa lookup_food."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "tdee": {
                    "type": "number",
                    "description": (
                        "Total Daily Energy Expenditure em kcal/dia. "
                        "Valor previamente calculado por calculate_tdee."
                    ),
                },
                "peso_kg": {
                    "type": "number",
                    "description": "Peso corporal em quilogramas, fornecido pelo utilizador.",
                },
                "objetivo": {
                    "type": "string",
                    "enum": ["perder_peso", "manter", "ganhar_massa"],
                    "description": (
                        "Objetivo nutricional:\n"
                        "- perder_peso: défice calórico de 20%\n"
                        "- manter: calorias iguais ao TDEE\n"
                        "- ganhar_massa: superávit calórico de 10%"
                    ),
                },
                "perfil_atividade": {
                    "type": "string",
                    "enum": ["sedentario", "ativo", "atleta"],
                    "description": (
                        "Perfil de atividade (afecta proteína g/kg):\n"
                        "- sedentario: 1.2 g/kg de proteína\n"
                        "- ativo: 1.6 g/kg\n"
                        "- atleta: 2.0 g/kg\n"
                        "NOTA: vocabulário diferente de calculate_tdee (que usa 5 níveis)."
                    ),
                },
            },
            "required": ["tdee", "peso_kg", "objetivo", "perfil_atividade"],
        },
    },
}


# ═══════════════════════════════════════════════════════════════════════════
# Schema 3: lookup_food
# ═══════════════════════════════════════════════════════════════════════════

LOOKUP_FOOD_SCHEMA = {
    "type": "function",
    "function": {
        "name": "lookup_food",
        "description": (
            "Procura informação nutricional (calorias, proteína, hidratos, gorduras, fibra) "
            "de um alimento específico na base de dados portuguesa INSA. "
            "Devolve valores por 100 gramas do alimento. "
            "Usar quando o utilizador pergunta sobre o conteúdo nutricional de um alimento concreto "
            "(ex: 'quantas calorias tem o arroz cozido?', 'a banana tem fibra?'). "
            "NÃO usar para calcular calorias diárias totais (usar calculate_tdee) "
            "nem para distribuição de macros do dia (usar calculate_macros)."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": (
                        "Nome do alimento como o utilizador o referiu, ou versão normalizada "
                        "(ex: 'arroz cozido', 'maçã', 'frango grelhado'). "
                        "Suporta nomes em português europeu e tolera variações de escrita."
                    ),
                },
            },
            "required": ["query"],
        },
    },
}

# ═══════════════════════════════════════════════════════════════════════════
# Schema 4: search_nutrition_principles (RAG)
# ═══════════════════════════════════════════════════════════════════════════

SEARCH_NUTRITION_PRINCIPLES_SCHEMA = {
    "type": "function",
    "function": {
        "name": "search_nutrition_principles",
        "description": (
            "Procura informação em literatura científica de nutrição "
            "(documentos INSA, DGS, ISSN) para responder a perguntas "
            "FACTUAIS ou DE PRINCÍPIOS sobre nutrição. "
            "Usar quando o utilizador faz perguntas como: 'quanta proteína "
            "precisa um atleta?', 'que benefícios tem a fibra?', 'devo comer "
            "hidratos à noite?', 'como é metabolizada a proteína?'. "
            "NÃO usar para procurar dados nutricionais de UM alimento "
            "específico (usar lookup_food). NÃO usar para cálculos de "
            "calorias diárias ou macros (usar calculate_tdee/calculate_macros). "
            "NÃO usar para perguntas subjectivas ou éticas (responder em texto)."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": (
                        "Pergunta ou termo de pesquisa em português sobre "
                        "princípios ou factos de nutrição."
                    ),
                },
            },
            "required": ["query"],
        },
    },
}

# Lista de schemas para passar ao Ollama
ALL_SCHEMAS = [
    CALCULATE_TDEE_SCHEMA,
    CALCULATE_MACROS_SCHEMA,
    LOOKUP_FOOD_SCHEMA,
    SEARCH_NUTRITION_PRINCIPLES_SCHEMA,
]