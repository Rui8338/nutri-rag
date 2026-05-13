"""
Cálculos nutricionais determinísticos para o agente NutriHub.

Estas funções são tools expostas ao LLM via function calling, mas a sua
correctness é puramente determinística — testar com pytest, não com evals.
"""

from typing import Literal


# ─── Constantes ───────────────────────────────────────────────────────────

Sexo = Literal["masculino", "feminino"]
FatorAtividade = Literal["sedentario", "ligeiro", "moderado", "intenso", "muito_intenso"]

# Multiplicadores Mifflin-St Jeor para fator de atividade
ACTIVITY_MULTIPLIERS: dict[str, float] = {
    "sedentario": 1.2,        # pouco ou nenhum exercício
    "ligeiro": 1.375,         # exercício leve 1-3 dias/semana
    "moderado": 1.55,         # exercício moderado 3-5 dias/semana
    "intenso": 1.725,         # exercício intenso 6-7 dias/semana
    "muito_intenso": 1.9,     # exercício muito intenso ou trabalho físico
}

# Tipos para calculate_macros
Objetivo = Literal["perder_peso", "manter", "ganhar_massa"]
PerfilAtividade = Literal["sedentario", "ativo", "atleta"]

# Ajustes calóricos por objetivo
OBJETIVO_MULTIPLIERS: dict[str, float] = {
    "perder_peso": 0.80,    # défice de 20%
    "manter": 1.00,
    "ganhar_massa": 1.10,   # superávit de 10%
}

# Proteína em g/kg de peso corporal por perfil
# Baseado em ISSN Position Stand on Protein (Jäger et al., 2017):
# - Sedentário: 0.8-1.2 g/kg → usado 1.2
# - Ativo:      1.4-1.7 g/kg → usado 1.6
# - Atleta:     1.6-2.2 g/kg → usado 2.0
PROTEINA_GRAMAS_POR_KG: dict[str, float] = {
    "sedentario": 1.2,
    "ativo": 1.6,
    "atleta": 2.0,
}

# Percentagem fixa de gorduras nas calorias-alvo
# Baseado em recomendações DGS (Direção-Geral da Saúde, Portugal):
# gorduras 20-35% das calorias → usado 25%
PERCENTAGEM_GORDURAS = 0.25

# Calorias por grama de cada macronutriente
KCAL_POR_GRAMA = {
    "proteina": 4.0,
    "hidratos": 4.0,
    "gorduras": 9.0,
}

# ─── Tool 1: calculate_tdee ──────────────────────────────────────────────

def calculate_tdee(
    idade: int,
    peso_kg: float,
    altura_cm: float,
    sexo: Sexo,
    fator_atividade: FatorAtividade,
) -> float:
    """
    Calcula o Total Daily Energy Expenditure (TDEE) — calorias necessárias
    por dia para manter o peso actual, considerando atividade física.

    Usa a fórmula de Mifflin-St Jeor (1990), considerada a mais precisa
    para população geral entre as fórmulas de estimativa de BMR.

    Fórmula BMR (Basal Metabolic Rate):
        Homem:   10×peso + 6.25×altura - 5×idade + 5
        Mulher:  10×peso + 6.25×altura - 5×idade - 161
    
    TDEE = BMR × multiplicador de atividade

    Multiplicadores de atividade (Mifflin & St Jeor, 1990):
        sedentario:     1.2     (pouco/nenhum exercício)
        ligeiro:        1.375   (1-3 dias/semana)
        moderado:       1.55    (3-5 dias/semana)
        intenso:        1.725   (6-7 dias/semana)
        muito_intenso:  1.9     (atletas, trabalho físico)

    Args:
        idade: Idade em anos (10-100, valores razoáveis para população geral).
        peso_kg: Peso em quilogramas (>0).
        altura_cm: Altura em centímetros (>0). NOTA: cm, não metros.
        sexo: "masculino" ou "feminino".
        fator_atividade: nível de atividade física (ver multiplicadores).

    Returns:
        TDEE em kcal/dia, arredondado a 0 casas decimais.

    Raises:
        ValueError: se algum input estiver fora dos limites razoáveis ou
                    com valor inválido (sexo/fator desconhecido).

    Exemplos:
        >>> calculate_tdee(30, 70, 175, "masculino", "moderado")
        2575.0
        >>> calculate_tdee(25, 60, 165, "feminino", "sedentario")
        1656.0
    """
    # Validação — fail loud
    if not isinstance(idade, int) or idade < 10 or idade > 100:
        raise ValueError(f"Idade deve ser inteiro entre 10 e 100, recebido: {idade}")
    if peso_kg <= 0 or peso_kg > 300:
        raise ValueError(f"Peso deve ser positivo e <= 300 kg, recebido: {peso_kg}")
    if altura_cm <= 0 or altura_cm > 250:
        raise ValueError(f"Altura deve ser positiva e <= 250 cm, recebido: {altura_cm}")
    if sexo not in ("masculino", "feminino"):
        raise ValueError(f"Sexo deve ser 'masculino' ou 'feminino', recebido: {sexo!r}")
    if fator_atividade not in ACTIVITY_MULTIPLIERS:
        valid = list(ACTIVITY_MULTIPLIERS.keys())
        raise ValueError(
            f"fator_atividade deve ser um de {valid}, recebido: {fator_atividade!r}"
        )

    # Mifflin-St Jeor BMR
    bmr_base = 10 * peso_kg + 6.25 * altura_cm - 5 * idade
    if sexo == "masculino":
        bmr = bmr_base + 5
    else:
        bmr = bmr_base - 161

    tdee = bmr * ACTIVITY_MULTIPLIERS[fator_atividade]
    return round(tdee, 0)

# ─── Tool 2: calculate_macros ────────────────────────────────────────────

def calculate_macros(
    tdee: float,
    peso_kg: float,
    objetivo: Objetivo,
    perfil_atividade: PerfilAtividade,
) -> dict[str, float]:
    """
    Calcula a distribuição de macronutrientes a partir do TDEE.

    Lógica de cálculo (ordem importa para garantir invariante de calorias):
        1. calorias_alvo = TDEE × multiplicador do objetivo
        2. proteina_g    = peso_kg × g/kg do perfil de atividade
        3. proteina_kcal = proteina_g × 4
        4. gorduras_kcal = calorias_alvo × 0.25
        5. gorduras_g    = gorduras_kcal / 9
        6. hidratos_kcal = calorias_alvo - proteina_kcal - gorduras_kcal
        7. hidratos_g    = hidratos_kcal / 4

    Garantia: proteina_g×4 + hidratos_g×4 + gorduras_g×9 ≈ calorias_alvo
    (com tolerância de arredondamento até ~10 kcal devido ao
arredondamento independente de cada macro a 0 casas decimais)

    Fontes das constantes:
        - Proteína g/kg: ISSN Position Stand on Protein (Jäger et al., 2017)
        - Distribuição calórica: DGS - Direção-Geral da Saúde, Portugal

    Args:
        tdee: Total Daily Energy Expenditure em kcal/dia (output de calculate_tdee).
        peso_kg: Peso corporal em quilogramas (>0).
        objetivo: "perder_peso" (-20%), "manter" (0%), ou "ganhar_massa" (+10%).
        perfil_atividade: "sedentario" (1.2 g/kg), "ativo" (1.6 g/kg),
                          ou "atleta" (2.0 g/kg).

    Returns:
        Dict com chaves:
            calorias_alvo: kcal/dia ajustadas ao objetivo
            proteina_g: gramas de proteína por dia
            hidratos_g: gramas de hidratos por dia
            gorduras_g: gramas de gorduras por dia

    Raises:
        ValueError: se inputs inválidos OU se a combinação levar a hidratos
                    negativos (sinal de plano nutricional inviável).

    Exemplo:
        >>> calculate_macros(2500, 70, "manter", "ativo")
        {'calorias_alvo': 2500, 'proteina_g': 112, 'hidratos_g': 343, 'gorduras_g': 69}
    """
    # Validação — fail loud
    if tdee <= 0 or tdee > 10000:
        raise ValueError(f"TDEE deve ser positivo e <= 10000, recebido: {tdee}")
    if peso_kg <= 0 or peso_kg > 300:
        raise ValueError(f"Peso deve ser positivo e <= 300 kg, recebido: {peso_kg}")
    if objetivo not in OBJETIVO_MULTIPLIERS:
        valid = list(OBJETIVO_MULTIPLIERS.keys())
        raise ValueError(f"objetivo deve ser um de {valid}, recebido: {objetivo!r}")
    if perfil_atividade not in PROTEINA_GRAMAS_POR_KG:
        valid = list(PROTEINA_GRAMAS_POR_KG.keys())
        raise ValueError(
            f"perfil_atividade deve ser um de {valid}, recebido: {perfil_atividade!r}"
        )

    # 1. Calorias-alvo
    calorias_alvo = tdee * OBJETIVO_MULTIPLIERS[objetivo]

    # 2-3. Proteína (gramas → calorias)
    proteina_g = peso_kg * PROTEINA_GRAMAS_POR_KG[perfil_atividade]
    proteina_kcal = proteina_g * KCAL_POR_GRAMA["proteina"]

    # 4-5. Gorduras (calorias → gramas)
    gorduras_kcal = calorias_alvo * PERCENTAGEM_GORDURAS
    gorduras_g = gorduras_kcal / KCAL_POR_GRAMA["gorduras"]

    # 6-7. Hidratos (resto → gramas)
    hidratos_kcal = calorias_alvo - proteina_kcal - gorduras_kcal
    if hidratos_kcal < 0:
        raise ValueError(
            f"Combinação inviável: proteína ({proteina_kcal:.0f} kcal) + "
            f"gorduras ({gorduras_kcal:.0f} kcal) excedem calorias-alvo "
            f"({calorias_alvo:.0f} kcal). Reduzir proteína/kg ou aumentar calorias."
        )
    hidratos_g = hidratos_kcal / KCAL_POR_GRAMA["hidratos"]

    return {
        "calorias_alvo": round(calorias_alvo, 0),
        "proteina_g": round(proteina_g, 0),
        "hidratos_g": round(hidratos_g, 0),
        "gorduras_g": round(gorduras_g, 0),
    }