from langchain_ollama import ChatOllama
from langchain_core.prompts import PromptTemplate
from langchain_core.output_parsers import StrOutputParser
from langchain_core.runnables import RunnablePassthrough
from src.retrieval.custom_retriever import get_retriever
import logging

logger = logging.getLogger(__name__)

# Inicializa LLM local via Ollama
llm = ChatOllama(
    model="llama3.2:3b",
    temperature=0.2,  # Baixo = mais determinístico, menos criativo
)

# Prompt que instrui o LLM a usar o contexto e citar fontes
prompt = PromptTemplate(
    input_variables=["context", "query"],
    template="""Es um assistente de nutricao informacional baseado em fontes cientificas.

INSTRUCOES CRITICAS:
1. Responde APENAS com base no contexto fornecido abaixo.
2. Se o contexto nao tiver informacao suficiente, diz claramente "Nao encontrei informacao sobre isto nas minhas fontes."
3. Cita sempre as fontes no formato [Fonte: nome, pagina X].
4. Responde sempre em portugues.
5. Aviso: este assistente e informacional e nao substitui consulta com nutricionista qualificado.

CONTEXTO:
{context}

PERGUNTA:
{query}

RESPOSTA:"""
)

def format_docs(docs) -> str:
    """
    Converte lista de Documents em string de contexto para o LLM.
    Inclui source e page para o LLM poder citar.
    """
    parts = []
    for doc in docs:
        source = doc.metadata.get("source", "Unknown")
        page = doc.metadata.get("page", "?")
        similarity = doc.metadata.get("similarity", 0)

        # Só inclui chunks com relevância mínima
        if similarity > 0.5:
            parts.append(
                f"[Fonte: {source}, pagina {page}]\n{doc.page_content}"
            )

    return "\n\n---\n\n".join(parts)

def get_citations(docs) -> list:
    """
    Extrai lista de citations dos chunks mais relevantes.
    """
    return list(set([
        f"{doc.metadata.get('source')} (p.{doc.metadata.get('page')})"
        for doc in docs
        if doc.metadata.get("similarity", 0) > 0.5
    ]))

def run_rag(query: str) -> dict:
    """
    Pipeline RAG completo:
    1. Retrieval — busca chunks relevantes
    2. Augment — formata contexto
    3. Generate — LLM responde com contexto
    """
    retriever = get_retriever(top_k=5)

    # 1. Retrieval
    logger.info(f"A recuperar contexto para: {query}")
    docs = retriever.invoke(query)

    if not docs:
        return {
            "query": query,
            "answer": "Nao encontrei informacao relevante nas minhas fontes.",
            "citations": []
        }

    # 2. Augment
    context = format_docs(docs)
    citations = get_citations(docs)

    # 3. Generate
    logger.info("A gerar resposta com LLM...")
    chain = prompt | llm | StrOutputParser()
    answer = chain.invoke({"context": context, "query": query})

    return {
        "query": query,
        "answer": answer,
        "citations": citations
    }

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)

    queries = [
        "quanto proteina precisa um atleta de forca?",
        "qual e a porcao recomendada de cereais por dia?",
        "quanto sal se deve comer por dia?",
    ]

    for query in queries:
        print(f"\n{'='*60}")
        print(f"Q: {query}")
        print('='*60)

        result = run_rag(query)

        print(f"\nResposta:\n{result['answer']}")
        print(f"\nFontes: {result['citations']}")