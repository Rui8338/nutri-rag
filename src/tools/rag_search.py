"""
Tool de RAG: pesquisa em chunks de conhecimento nutricional INSA.

Wrapper sobre src/retrievel/custom_retriever.py (Semana 1), adaptado para
uso como tool no agent loop:
- Converte List[Document] → dict simples (chunks, sources, scores)
- Filtra por threshold de similaridade
- Retorna None se nenhum chunk relevante
"""

from typing import Optional
from src.retrieval.custom_retriever import get_retriever


# Threshold de similaridade (0-1). Acima: chunk considerado relevante.
# Empírico: 0.3 é razoável para queries em PT com este modelo.
DEFAULT_THRESHOLD = 0.5

# Top-K chunks a recuperar (decisão Dia 4)
DEFAULT_TOP_K = 3


def search_nutrition_principles(
    query: str,
    k: int = DEFAULT_TOP_K,
    threshold: float = DEFAULT_THRESHOLD,
) -> Optional[dict]:
    """
    Procura chunks relevantes na base de conhecimento nutricional.

    Args:
        query: Pergunta ou termo de pesquisa em português.
        k: Número máximo de chunks a retornar.
        threshold: Similaridade mínima (0-1) para considerar relevante.

    Returns:
        Dict com {chunks: [str], sources: [str], scores: [float]} se algum
        chunk passou threshold; None se nenhum chunk relevante.

    Raises:
        ValueError: se query for vazia.
    """
    if not query or not query.strip():
        raise ValueError("Query não pode ser vazia")

    retriever = get_retriever(top_k=k)
    documents = retriever.invoke(query.strip())

    if not documents:
        return None

    # Filtrar por threshold
    chunks, sources, scores = [], [], []
    for doc in documents:
        similarity = doc.metadata.get("similarity", 0.0)
        if similarity >= threshold:
            chunks.append(doc.page_content)
            source_str = doc.metadata.get("source", "desconhecido")
            page = doc.metadata.get("page")
            if page is not None:
                source_str = f"{source_str}, p.{page}"
            sources.append(source_str)
            scores.append(round(similarity, 3))

    if not chunks:
        return None

    return {
        "chunks": chunks,
        "sources": sources,
        "scores": scores,
    }