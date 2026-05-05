from sentence_transformers import SentenceTransformer
from src.database import SessionLocal
from sqlalchemy import text

# Tem de ser o mesmo modelo usado na indexação
model = SentenceTransformer('paraphrase-multilingual-MiniLM-L12-v2')

def retrieve(query: str, top_k: int = 3):
    """
    Converte query em vetor e procura chunks mais próximos.
    """
    query_vector = model.encode(query).tolist()

    session = SessionLocal()
    try:
        results = session.execute(text("""
            SELECT source, page_number, content,
                   1 - (embedding <=> CAST(:embedding AS vector)) as similarity
            FROM nutrition.knowledge_chunks
            ORDER BY embedding <=> CAST(:embedding AS vector)
            LIMIT :top_k
        """), {"embedding": str(query_vector), "top_k": top_k})

        return results.fetchall()
    finally:
        session.close()

if __name__ == "__main__":
    queries = [
        "quanto proteina precisa um atleta?",
        "qual e a porcao recomendada de cereais?",
        "quanto sal se deve comer por dia?",
    ]

    for query in queries:
        print(f"\n{'='*60}")
        print(f"Query: {query}")
        print('='*60)
        results = retrieve(query)
        for r in results:
            print(f"\n[{r.source} p.{r.page_number}] similarity={r.similarity:.3f}")
            print(f"{r.content[:150]}...")