"""
Smoke tests para src/tools/food_lookup.py contra a DB REAL.

Diferente dos unit tests em test_food_lookup.py:
- Estes precisam da DB Postgres a correr com a tabela nutrition.foods populada
- Validam que a integração ponta-a-ponta funciona (conexão, query, conversão de tipos)
- Não substituem unit tests — complementam-nos

Para correr sem DB (ex: CI), use:
    pytest --ignore=tests/test_food_lookup_integration.py

Para correr só estes:
    pytest tests/test_food_lookup_integration.py -v
"""

import pytest
from src.tools.food_lookup import FoodLookup


# ═══════════════════════════════════════════════════════════════════════════
# Fixture — FoodLookup contra DB real, skip se não disponível
# ═══════════════════════════════════════════════════════════════════════════

@pytest.fixture(scope="module")
def real_lookup():
    """
    FoodLookup real. Scope='module' → carregamos cache uma vez para os 3 testes.
    Skip se DB não disponível (em vez de FAIL — não é bug, é ambiente).
    """
    try:
        lookup = FoodLookup()
        lookup._load()  # força conexão imediata; falha aqui se DB offline
        return lookup
    except Exception as e:
        pytest.skip(f"DB não disponível: {e}")


# ═══════════════════════════════════════════════════════════════════════════
# Smoke tests
# ═══════════════════════════════════════════════════════════════════════════

class TestRealDatabaseIntegration:

    def test_carrega_alimentos_reais(self, real_lookup):
        """A DB tem >100 alimentos carregados (sanity check da importação)."""
        assert real_lookup._cache is not None
        assert len(real_lookup._cache) > 100, (
            f"Esperava >100 alimentos na DB, encontrei {len(real_lookup._cache)}"
        )

    def test_match_plausivel_para_query_tipica(self, real_lookup):
        """'arroz cozido' deve devolver algo com 'arroz' E 'cozido' no nome."""
        result = real_lookup("arroz cozido")
        assert result is not None
        nome_lower = result["nome"].lower()
        assert "arroz" in nome_lower
        assert "cozido" in nome_lower
        # Sanity nutricional: arroz cozido tem 100-150 kcal/100g
        assert 80 < result["calorias"] < 200, (
            f"Calorias fora do range esperado para arroz cozido: {result['calorias']}"
        )

    def test_query_nonsense_devolve_none(self, real_lookup):
        """Query sem qualquer relação real deve devolver None."""
        result = real_lookup("xptoblargh asdfqwerty")
        assert result is None