"""
Lookup de alimentos da tabela INSA com fuzzy matching.

Os utilizadores escrevem nomes informais ("arroz cozido"), a tabela INSA
tem nomes formais ("Arroz, agulha, cozido simples"). Este módulo faz a
ponte com rapidfuzz, cache em memória, e fail-graceful quando não há match.

Padrão: classe `FoodLookup` injectável (session_factory passada no constructor)
para que testes possam usar uma DB mock sem patches globais.
"""

from typing import Callable, Optional
from rapidfuzz import process, fuzz
from sqlalchemy.orm import Session

from src.database import Food, SessionLocal


# Threshold default — queries com score < 70 são consideradas "não encontrado"
# (testado empiricamente: abaixo de 70, os matches são geralmente lixo)
DEFAULT_THRESHOLD = 70


class FoodLookup:
    """
    Lookup de alimentos com cache em memória e fuzzy matching.

    A primeira chamada carrega todos os alimentos da DB para memória
    (~1377 rows, ~50KB). Chamadas seguintes são <10ms.

    Args:
        session_factory: Callable que devolve uma SQLAlchemy Session.
                         Default: SessionLocal do projeto.
                         Em testes, passa um factory que devolve mock session.
    """

    def __init__(self, session_factory: Callable[[], Session] = SessionLocal):
        self._session_factory = session_factory
        self._cache: Optional[list[Food]] = None
        self._name_to_food: Optional[dict[str, Food]] = None

    def _load(self) -> None:
        """Carrega alimentos da DB para cache em memória."""
        session = self._session_factory()
        try:
            foods = session.query(Food).all()
            self._cache = foods
            # Index por nome (lowercase) para retrieval O(1) após match
            self._name_to_food = {f.name.lower(): f for f in foods}
        finally:
            session.close()

    def reset_cache(self) -> None:
        """Força reload na próxima chamada. Útil em testes ou após mudanças à DB."""
        self._cache = None
        self._name_to_food = None

    def __call__(
        self,
        query: str,
        threshold: int = DEFAULT_THRESHOLD,
    ) -> Optional[dict]:
        """
        Procura o alimento mais semelhante a `query` na tabela INSA.

        Args:
            query: Nome do alimento como o utilizador escreveu (ex: "arroz cozido").
            threshold: Score mínimo (0-100) para considerar match válido.
                       Default 70.

        Returns:
            Dict com {nome, score, calorias, proteina_g, hidratos_g,
                      gorduras_g, fibra_g, porcao_g} se score >= threshold,
            None caso contrário.

        Raises:
            ValueError: se query for vazia ou só whitespace.

        Exemplos:
            >>> lookup = FoodLookup()
            >>> result = lookup("arroz cru")
            >>> result["nome"]
            'Arroz agulha cru'
            >>> result = lookup("xpto inexistente")
            >>> result is None
            True
        """
        if not query or not query.strip():
            raise ValueError("Query não pode ser vazia")

        if self._cache is None:
            self._load()

        # rapidfuzz: process.extractOne devolve (match, score, index)
        # WRatio é o algoritmo "esperto" recomendado para nomes de produtos
        names = list(self._name_to_food.keys())
        result = process.extractOne(
            query.lower(),
            names,
            scorer=fuzz.WRatio,
            score_cutoff=threshold,
        )

        if result is None:
            return None

        matched_name, score, _ = result
        food = self._name_to_food[matched_name]

        return {
            "nome": food.name,
            "score": int(round(score)),
            "calorias": float(food.calories) if food.calories is not None else 0.0,
            "proteina_g": float(food.protein_g) if food.protein_g is not None else 0.0,
            "hidratos_g": float(food.carbs_g) if food.carbs_g is not None else 0.0,
            "gorduras_g": float(food.fat_g) if food.fat_g is not None else 0.0,
            "fibra_g": float(food.fiber_g) if food.fiber_g is not None else 0.0,
            "porcao_g": float(food.portion_size_g) if food.portion_size_g is not None else 100.0,
        }


# Instância singleton para uso em produção (Dia 3 — agent loop)
_default_lookup = FoodLookup()


def lookup_food(query: str, threshold: int = DEFAULT_THRESHOLD) -> Optional[dict]:
    """
    Função wrapper para uso directo. Usa singleton interno.

    Para testes, instancia FoodLookup directamente com mock session_factory.
    """
    return _default_lookup(query, threshold=threshold)