from pydantic_settings import BaseSettings, SettingsConfigDict
from pathlib import Path

class Settings(BaseSettings):
    # Database
    database_url: str
    log_level: str = "INFO"

    # Paths
    data_dir: Path = Path(__file__).parent.parent / "data"
    sources_dir: Path = data_dir / "sources"
    processed_dir: Path = data_dir / "processed"

    # RAG params
    chunk_size: int = 500
    chunk_overlap: int = 50
    top_k: int = 5

    # Models
    embedding_model: str = "paraphrase-multilingual-MiniLM-L12-v2"
    llm_model: str = "llama3.2:3b"

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


settings = Settings()