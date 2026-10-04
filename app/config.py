"""Runtime configuration, read from environment variables (12-factor style).

Locally: `uv run --env-file .env ...` loads `.env`. In Docker/Cloud Run: the platform sets env vars.
"""

import os
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

# Matches docker-compose.yml's dev credentials. Local-only; never a real secret.
_DEFAULT_DATABASE_URL = "postgresql://specseek:specseek@localhost:5432/specseek"


@dataclass(frozen=True)
class Settings:
    database_url: str
    log_level: str
    data_dir: Path  # POST /v1/ingest may only read PDFs under this directory
    embedding_model: str
    generation_model: str
    # repr=False: the key must never show up in a log line or a stack trace.
    gemini_api_key: str = field(repr=False)


@lru_cache
def get_settings() -> Settings:
    # lru_cache: read the environment once per process, then reuse the same object.
    return Settings(
        database_url=os.environ.get("DATABASE_URL", _DEFAULT_DATABASE_URL),
        log_level=os.environ.get("LOG_LEVEL", "info"),
        data_dir=Path(os.environ.get("DATA_DIR", "data")),
        embedding_model=os.environ.get("EMBEDDING_MODEL", "gemini-embedding-001"),
        # A pinned model name, not an alias like "flash-latest": answers must not change
        # under the evaluation without us choosing to change the model.
        generation_model=os.environ.get("GENERATION_MODEL", "gemini-3.8-flash"),
        gemini_api_key=os.environ.get("GEMINI_API_KEY", ""),
    )
