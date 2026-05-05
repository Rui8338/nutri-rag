from pathlib import Path
import pdfplumber
import re
import json
import logging
from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter
from src.config import settings

# Suprime warnings do pdfminer
logging.getLogger("pdfminer").setLevel(logging.ERROR)

logger = logging.getLogger(__name__)

# Mapa PDF → source name (para citations)
PDF_SOURCES = {
    "DGS_Roda_Alimentos.pdf": {"name": "DGS_Roda", "lang": "pt"},
    "ISSN_Protein_Athletic_Performance_2017.pdf": {"name": "ISSN_Protein", "lang": "en"},
    "Programa_Distribuicao_Alimentos.pdf": {"name": "Distribuicao_Alim", "lang": "pt"},
}

def load_pdf_documents(pdf_path: str | Path):
    """
    Usa pdfplumber para parsear PDFs.
    Retorna lista de LangChain Document objects.
    """
    docs = []

    with pdfplumber.open(str(pdf_path)) as pdf:
        for i, page in enumerate(pdf.pages):
            text = page.extract_text()
            if text:
                docs.append(Document(
                    page_content=text,
                    metadata={"source": str(pdf_path), "page": i + 1}
                ))

    logger.info(f"Loaded {len(docs)} pages from {Path(pdf_path).name}")
    return docs

def fix_duplicated_chars(text: str) -> str:
    """
    Corrige letras duplicadas: 'RROODDAA' → 'RODA'
    """
    return re.sub(r'(.)\1+', r'\1', text)

def fix_encoding_chars(text: str) -> str:
    """
    Substitui caracteres mal codificados pelos equivalentes portugueses.
    """
    replacements = {
        "ã": "a", "Ã": "A",
        "â": "a", "Â": "A",
        "à": "a", "À": "A",
        "á": "a", "Á": "A",
        "ç": "c", "Ç": "C",
        "é": "e", "É": "E",
        "ê": "e", "Ê": "E",
        "è": "e", "È": "E",
        "í": "i", "Í": "I",
        "ó": "o", "Ó": "O",
        "ô": "o", "Ô": "O",
        "õ": "o", "Õ": "O",
        "ú": "u", "Ú": "U",
        "ü": "u", "Ü": "U",
        "ñ": "n", "Ñ": "N",
        #"�": "",  # Remove caracteres impossíveis de recuperar
    }

    for original, replacement in replacements.items():
        text = text.replace(original, replacement)

    return text

def clean_chunks(chunks: list) -> list:
    """
    Remove lixo comum em PDFs e corrige problemas de encoding.
    """
    cleaned = []

    for chunk in chunks:
        content = chunk.page_content

        # Corrige letras duplicadas e encoding
        content = fix_duplicated_chars(content)
        content = fix_encoding_chars(content)

        # Remove linhas com menos de 10 caracteres (números de página, etc)
        lines = content.split('\n')
        lines = [line for line in lines if len(line.strip()) > 10]
        content = '\n'.join(lines)

        # Remove espaços em branco excessivos
        content = '\n'.join([line.strip() for line in content.split('\n') if line.strip()])

        # Só mantém chunks com conteúdo significativo
        if len(content) > 100:
            chunk.page_content = content
            cleaned.append(chunk)

    removed = len(chunks) - len(cleaned)
    logger.info(f"Removed {removed} low-quality chunks")
    return cleaned

def chunk_documents(documents: list, chunk_size: int = 500, chunk_overlap: int = 50, source_name: str = None):
    """
    Usa RecursiveCharacterTextSplitter para chunking semântico.
    """
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
        separators=["\n\n", "\n", ". ", " ", ""],
        length_function=len,
    )

    chunks = splitter.split_documents(documents)

    # Enriquece metadata
    for i, chunk in enumerate(chunks):
        chunk.metadata["chunk_index"] = i
        chunk.metadata["source"] = source_name or Path(chunk.metadata.get("source", "unknown")).stem

    logger.info(f"Generated {len(chunks)} chunks (size={chunk_size}, overlap={chunk_overlap})")
    return chunks

def ingest_all_pdfs():
    """
    Carrega todos os PDFs, chunks e retorna lista consolidada.
    """
    all_chunks = []

    for pdf_file, info in PDF_SOURCES.items():
        pdf_path = settings.sources_dir / pdf_file

        if not pdf_path.exists():
            logger.warning(f"Skipped {pdf_file} (not found)")
            continue

        logger.info(f"\n📄 Processing {pdf_file}...")
        docs = load_pdf_documents(pdf_path)
        chunks = chunk_documents(
            docs,
            chunk_size=settings.chunk_size,
            chunk_overlap=settings.chunk_overlap,
            source_name=info["name"]
        )
        chunks = clean_chunks(chunks)

        for chunk in chunks:
            chunk.metadata["lang"] = info["lang"]

        all_chunks.extend(chunks)

    logger.info(f"\n✅ Total chunks: {len(all_chunks)}")
    return all_chunks

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)

    chunks = ingest_all_pdfs()

    # Debug: salva primeiros chunks
    debug_chunks = [
        {
            "content": c.page_content[:150],
            "source": c.metadata.get("source"),
            "page": c.metadata.get("page"),
            "chunk_idx": c.metadata.get("chunk_index")
        }
        for c in chunks[:10]
    ]

    Path(settings.processed_dir).mkdir(exist_ok=True)
    with open(settings.processed_dir / "chunks_debug.json", "w", encoding="utf-8") as f:
        json.dump(debug_chunks, f, indent=2, ensure_ascii=False)

    print(f"\nDebug chunks saved to {settings.processed_dir}/chunks_debug.json")