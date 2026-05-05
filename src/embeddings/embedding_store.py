from sentence_transformers import SentenceTransformer
from src.database import KnowledgeChunk, SessionLocal
from src.ingestion.pdf_loader import ingest_all_pdfs
import logging

logger = logging.getLogger(__name__)

# IMPORTANTE: Este modelo tem de ser sempre o mesmo
# em indexação E em retrieval
MODEL_NAME = 'paraphrase-multilingual-MiniLM-L12-v2'
model = SentenceTransformer(MODEL_NAME)

def embed_text(text: str) -> list:
    """
    Converte texto em vetor de 384 dimensões.
    """
    return model.encode(text).tolist()

def store_chunks(chunks: list) -> int:
    """
    Para cada chunk:
    1. Gera embedding
    2. Guarda texto + vetor em Postgres
    """
    session = SessionLocal()
    count = 0

    try:
        for i, chunk in enumerate(chunks):
            if i % 50 == 0:
                logger.info(f"  Embedding {i}/{len(chunks)}...")

            embedding = embed_text(chunk.page_content)

            knowledge_chunk = KnowledgeChunk(
                source=chunk.metadata.get("source", "unknown"),
                content=chunk.page_content,
                embedding=embedding,
                page_number=chunk.metadata.get("page"),
                chunk_index=chunk.metadata.get("chunk_index"),
            )
            session.add(knowledge_chunk)
            count += 1

            if i % 50 == 49:
                session.commit()

        session.commit()
        logger.info(f"✅ Guardados {count} chunks com embeddings")
        return count

    except Exception as e:
        session.rollback()
        logger.error(f"❌ Falhou: {e}")
        raise
    finally:
        session.close()

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)

    chunks = ingest_all_pdfs()
    store_chunks(chunks)