"""
Unit tests para src/tools/food_lookup.py

Estratégia:
- Mock session com 8 alimentos cuidadosamente escolhidos para cobrir
  casos de teste (matches exactos, fuzzy, ambíguos, sem match)
- Sem dependência da DB real — testes correm offline e são deterministas
- Smoke tests contra DB real ficam num ficheiro separado (test_food_lookup_integration.py)

Os 8 alimentos foram escolhidos para cobrir:
- Match exacto e match fuzzy
- Nomes com vírgulas (estilo INSA)
- Acentos
- Alimentos com macros = 0 (azeite tem 0 hidratos, frango tem 0 hidratos)
- Pares semelhantes (arroz cru vs cozido) para testar disambiguação
"""

import pytest
from src.tools.food_lookup import FoodLookup, DEFAULT_THRESHOLD


# ═══════════════════════════════════════════════════════════════════════════
# Mock infrastructure
# ═══════════════════════════════════════════════════════════════════════════

class MockFood:
    """Mock de Food com os campos que FoodLookup acede."""
    def __init__(self, id, name, calories, protein_g, carbs_g, fat_g, fiber_g,
                 portion_size_g=100.0):
        self.id = id
        self.name = name
        self.calories = calories
        self.protein_g = protein_g
        self.carbs_g = carbs_g
        self.fat_g = fat_g
        self.fiber_g = fiber_g
        self.portion_size_g = portion_size_g


class MockQuery:
    """Mock estrito — só suporta .all()."""
    def __init__(self, foods):
        self.foods = foods

    def all(self):
        return self.foods


class MockSession:
    """Mock estrito — só suporta query() e close()."""
    def __init__(self, foods):
        self.foods = foods
        self.closed = False

    def query(self, model):
        return MockQuery(self.foods)

    def close(self):
        self.closed = True


def make_mock_factory(foods):
    """Cria um session_factory que devolve uma MockSession com os alimentos dados."""
    return lambda: MockSession(foods)


# ═══════════════════════════════════════════════════════════════════════════
# Fixture com 8 alimentos (cobre casos de teste relevantes)
# ═══════════════════════════════════════════════════════════════════════════

@pytest.fixture
def sample_foods():
    """8 alimentos escolhidos para cobrir casos de teste relevantes."""
    return [
        MockFood(1, "Arroz agulha cru", 347.0, 6.7, 78.1, 0.4, 2.1),
        MockFood(2, "Arroz cozido simples", 125.0, 2.5, 28.0, 0.2, 0.8),
        MockFood(3, "Azeite", 899.0, 0.0, 0.0, 99.9, 0.0),
        MockFood(4, "Frango peito grelhado", 165.0, 31.0, 0.0, 3.6, 0.0),
        MockFood(5, "Maçã", 52.0, 0.3, 13.8, 0.2, 2.4),
        MockFood(6, "Banana madura", 89.0, 1.1, 22.8, 0.3, 2.6),
        MockFood(7, "Pão de mistura", 250.0, 9.0, 49.0, 1.2, 4.5),
        MockFood(8, "Queijo flamengo", 305.0, 24.0, 0.5, 23.0, 0.0),
    ]


@pytest.fixture
def lookup(sample_foods):
    """FoodLookup pré-configurado com sample_foods."""
    return FoodLookup(session_factory=make_mock_factory(sample_foods))


# ═══════════════════════════════════════════════════════════════════════════
# Matches positivos — várias variações de input
# ═══════════════════════════════════════════════════════════════════════════

class TestPositiveMatches:

    def test_match_exacto(self, lookup):
        """Nome exacto deve dar score muito alto."""
        result = lookup("Arroz agulha cru")
        assert result is not None
        assert result["nome"] == "Arroz agulha cru"
        assert result["score"] >= 95

    def test_match_lowercase(self, lookup):
        """Lowercase do user deve fazer match com nome em title case."""
        result = lookup("arroz agulha cru")
        assert result is not None
        assert result["nome"] == "Arroz agulha cru"

    def test_match_uppercase(self, lookup):
        """Uppercase também deve funcionar."""
        result = lookup("ARROZ COZIDO")
        assert result is not None
        assert result["nome"] == "Arroz cozido simples"

    def test_match_parcial(self, lookup):
        """Query sem 'simples' deve achar o cozido."""
        result = lookup("arroz cozido")
        assert result is not None
        assert "cozido" in result["nome"].lower()

    def test_match_com_typo_pequeno(self, lookup):
        """'arrz' (typo) deve achar arroz."""
        result = lookup("arrz cozido")
        assert result is not None
        assert "arroz" in result["nome"].lower()

    def test_match_palavra_unica(self, lookup):
        """'azeite' deve achar 'Azeite'."""
        result = lookup("azeite")
        assert result is not None
        assert result["nome"] == "Azeite"


# ═══════════════════════════════════════════════════════════════════════════
# Disambiguação entre opções similares
# ═══════════════════════════════════════════════════════════════════════════

class TestDisambiguation:

    def test_cru_vs_cozido_query_cru(self, lookup):
        """'arroz cru' deve achar o cru, não o cozido."""
        result = lookup("arroz cru")
        assert result is not None
        assert "cru" in result["nome"].lower()
        assert "cozido" not in result["nome"].lower()

    def test_cru_vs_cozido_query_cozido(self, lookup):
        """'arroz cozido' deve achar o cozido, não o cru."""
        result = lookup("arroz cozido")
        assert result is not None
        assert "cozido" in result["nome"].lower()


# ═══════════════════════════════════════════════════════════════════════════
# Não-matches — devem devolver None
# ═══════════════════════════════════════════════════════════════════════════

class TestNoMatch:

    def test_alimento_inexistente(self, lookup):
        """Query sem qualquer relação deve devolver None."""
        result = lookup("xptoblargh")
        assert result is None

    def test_alimento_inexistente_palavra_real(self, lookup):
        """'pizza' não está nos 8 alimentos — deve devolver None."""
        result = lookup("pizza margherita")
        assert result is None

    def test_threshold_alto_rejeita_match_fraco(self, lookup):
        """Com threshold 95, 'arrz cozido' (typo) já não deve passar."""
        result_strict = lookup("arrz cozido", threshold=95)
        assert result_strict is None

    def test_threshold_baixo_aceita_quase_tudo(self, lookup):
        """Com threshold muito baixo, quase qualquer query encontra algo."""
        result = lookup("aaa", threshold=10)
        # Documenta que threshold baixo é permissivo
        assert result is not None


# ═══════════════════════════════════════════════════════════════════════════
# Estrutura do retorno
# ═══════════════════════════════════════════════════════════════════════════

class TestReturnStructure:

    def test_retorna_dict_com_chaves_correctas(self, lookup):
        result = lookup("arroz cru")
        assert result is not None
        expected_keys = {
            "nome", "score", "calorias", "proteina_g",
            "hidratos_g", "gorduras_g", "fibra_g", "porcao_g",
        }
        assert set(result.keys()) == expected_keys

    def test_score_entre_0_e_100(self, lookup):
        result = lookup("arroz cru")
        assert 0 <= result["score"] <= 100

    def test_macros_sao_float(self, lookup):
        """Todos os campos numéricos devem ser float (Numeric da DB → float)."""
        result = lookup("arroz cru")
        for key in ["calorias", "proteina_g", "hidratos_g", "gorduras_g", "fibra_g"]:
            assert isinstance(result[key], float), f"{key} deveria ser float"

    def test_valores_correspondem_ao_alimento(self, lookup):
        """Os valores no dict devem bater com os do alimento mockado."""
        result = lookup("Arroz agulha cru")
        assert result["calorias"] == 347.0
        assert result["proteina_g"] == 6.7
        assert result["hidratos_g"] == 78.1
        assert result["gorduras_g"] == 0.4
        assert result["fibra_g"] == 2.1


# ═══════════════════════════════════════════════════════════════════════════
# Edge cases
# ═══════════════════════════════════════════════════════════════════════════

class TestEdgeCases:

    def test_query_vazia_levanta_erro(self, lookup):
        with pytest.raises(ValueError, match="vazia"):
            lookup("")

    def test_query_so_whitespace_levanta_erro(self, lookup):
        with pytest.raises(ValueError, match="vazia"):
            lookup("   ")

    def test_alimento_com_macros_zero(self, lookup):
        """Frango tem hidratos=0; deve devolver 0.0, não None."""
        result = lookup("frango peito")
        assert result is not None
        assert result["hidratos_g"] == 0.0

    def test_porcao_g_devolvida_correctamente(self, lookup):
        """Todos os mocks têm portion_size_g=100."""
        result = lookup("azeite")
        assert result["porcao_g"] == 100.0


# ═══════════════════════════════════════════════════════════════════════════
# Cache behaviour
# ═══════════════════════════════════════════════════════════════════════════

class TestCache:

    def test_cache_carrega_uma_vez(self, sample_foods):
        """Múltiplas chamadas → o factory só é invocado uma vez."""
        call_count = {"n": 0}

        def counting_factory():
            call_count["n"] += 1
            return MockSession(sample_foods)

        lookup = FoodLookup(session_factory=counting_factory)

        lookup("arroz")
        lookup("azeite")
        lookup("frango")

        assert call_count["n"] == 1, "factory devia ser chamado só uma vez (cache)"

    def test_reset_cache_forca_reload(self, sample_foods):
        """Após reset_cache, factory deve ser invocado novamente."""
        call_count = {"n": 0}

        def counting_factory():
            call_count["n"] += 1
            return MockSession(sample_foods)

        lookup = FoodLookup(session_factory=counting_factory)
        lookup("arroz")
        assert call_count["n"] == 1

        lookup.reset_cache()
        lookup("arroz")
        assert call_count["n"] == 2

    def test_session_e_fechada_apos_load(self, sample_foods):
        """A session do load deve ser fechada (recurso limpo)."""
        sessions_created = []

        def tracking_factory():
            s = MockSession(sample_foods)
            sessions_created.append(s)
            return s

        lookup = FoodLookup(session_factory=tracking_factory)
        lookup("arroz")

        assert len(sessions_created) == 1
        assert sessions_created[0].closed is True