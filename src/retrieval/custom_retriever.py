from langchain_core.retrievers import BaseRetriever
from langchain_core.documents import Document
from langchain_core.callbacks import CallbackManagerForRetrieverRun
from sentence_transformers import SentenceTransformer
from src.database import SessionLocal
from sqlalchemy import text
from src.config import settings
from typing import List

MODEL_NAME = 'paraphrase-multilingual-MiniLM-L12-v2'
model = SentenceTransformer(MODEL_NAME)

class NutritionRetriever(BaseRetriever):
    """
    Retriever customizado que faz ANN search no pgvector.
    Estende BaseRetriever para compatibilidade com LangChain chains.
    """

    top_k: int = 5

    def _get_relevant_documents(
        self,
        query: str,
        *,
        run_manager: CallbackManagerForRetrieverRun = None
    ) -> List[Document]:

        # Embed query
        query_vector = model.encode(query).tolist()

        session = SessionLocal()
        try:
            results = session.execute(text("""
                SELECT source, page_number, content,
                       1 - (embedding <=> CAST(:embedding AS vector)) as similarity
                FROM nutrition.knowledge_chunks
                ORDER BY embedding <=> CAST(:embedding AS vector)
                LIMIT :top_k
            """), {"embedding": str(query_vector), "top_k": self.top_k})

            # Converte para LangChain Documents
            documents = []
            for r in results.fetchall():
                documents.append(Document(
                    page_content=r.content,
                    metadata={
                        "source": r.source,
                        "page": r.page_number,
                        "similarity": r.similarity
                    }
                ))

            return documents

        finally:
            session.close()


def get_retriever(top_k: int = 5) -> NutritionRetriever:
    return NutritionRetriever(top_k=top_k)

if __name__ == "__main__":
    retriever = get_retriever()
    docs = retriever.invoke("quanto proteina precisa um atleta?")
    for doc in docs:
        print(f"[{doc.metadata['source']} p.{doc.metadata['page']}] sim={doc.metadata['similarity']:.3f}")
        print(doc.page_content[:100])
        print()