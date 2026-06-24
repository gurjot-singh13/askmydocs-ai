from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # ── Database ────────────────────────────────────────────────────────────
    DATABASE_URL: str

    # ── Auth ────────────────────────────────────────────────────────────────
    SECRET_KEY: str
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60

    # ── Google AI ───────────────────────────────────────────────────────────
    GOOGLE_API_KEY: str = ""

    # ── Qdrant ──────────────────────────────────────────────────────────────
    QDRANT_URL: str = "http://localhost:6333"

    # ── File storage ────────────────────────────────────────────────────────
    UPLOAD_DIR: str = "./uploads"
    MAX_FILE_SIZE_MB: int = 50
    CHROMA_PERSIST_DIR: str = "./chroma_data"
    
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


# Module-level singleton — import this everywhere
settings = Settings()
