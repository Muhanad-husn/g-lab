"""Application configuration via environment variables."""

from pathlib import Path

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """G-Lab backend configuration.

    All values can be overridden via environment variables.
    Phase 1 requires only NEO4J_URI, NEO4J_USER, and NEO4J_PASSWORD.
    """

    # Neo4j connection
    NEO4J_URI: str = "bolt://localhost:7687"
    NEO4J_USER: str = "neo4j"
    NEO4J_PASSWORD: str = "password"

    # OpenRouter (Phase 2 — Copilot)
    OPENROUTER_API_KEY: str = ""
    OPENROUTER_BASE_URL: str = "https://openrouter.ai/api/v1"

    # ChromaDB vector store (Phase 3 — Document grounding)
    CHROMA_HOST: str = "chromadb"
    CHROMA_PORT: int = 8000
    EMBEDDING_MODEL: str = "all-MiniLM-L6-v2"

    # Application
    GLAB_DATA_DIR: Path = Path("/data")
    GLAB_LOG_LEVEL: str = "INFO"

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}
