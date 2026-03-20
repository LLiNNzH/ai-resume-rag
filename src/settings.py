from pydantic import BaseModel
import os

class Settings(BaseModel):
    provider: str = os.getenv("PROVIDER", "openai")
    base_url: str = os.getenv("BASE_URL", "https://api.openai.com/v1")
    api_key: str = os.getenv("API_KEY") or ""

    model_id: str = os.getenv("MODEL_ID", "gpt-4o-mini")
    model_name: str = os.getenv("MODEL_NAME", "gpt-4o-mini")

    embed_model: str = os.getenv(
        "EMBED_MODEL", "text-embedding-3-small"
    )

    chunk_size: int = int(os.getenv("CHUNK_SIZE", "800"))
    chunk_overlap: int = int(os.getenv("CHUNK_OVERLAP", "100"))

    top_k: int = int(os.getenv("TOP_K", "8"))

SETTINGS = Settings()
