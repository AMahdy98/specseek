"""Runtime configuration, read from environment variables (12-factor style).

Locally: `uv run --env-file .env ...` loads `.env`. In Docker/Cloud Run: the platform sets env vars.
"""

import os
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

# Matches docker-compose.yml's dev credentials. Local-only; never a real secret.
_DEFAULT_DATABASE_URL = "postgresql://specseek:specseek@localhost:5432/specseek"

# The Vite dev server. `localhost` and `127.0.0.1` are different origins to a browser.
_DEFAULT_CORS_ORIGINS = "http://localhost:5173,http://127.0.0.1:5173"


@dataclass(frozen=True)
class Settings:
    database_url: str
    log_level: str
    data_dir: Path  # POST /v1/ingest may only read PDFs under this directory
    embedding_model: str
    generation_model: str
    # Browser origins (scheme://host:port) allowed to call the API from JavaScript.
    cors_allowed_origins: tuple[str, ...]
    # Token bucket on POST /v1/query: long-run average, and how many may arrive at once.
    query_rate_per_minute: float
    query_burst: int
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
        generation_model=os.environ.get("GENERATION_MODEL", "gemini-3.5-flash-lite"),
        cors_allowed_origins=parse_origins(
            os.environ.get("CORS_ALLOWED_ORIGINS", _DEFAULT_CORS_ORIGINS)
        ),
        # The provider allows 15 generations/minute. 12 leaves room for the server's own
        # retries, which also count against that limit.
        query_rate_per_minute=float(os.environ.get("QUERY_RATE_PER_MINUTE", "12")),
        query_burst=int(os.environ.get("QUERY_BURST", "6")),
        gemini_api_key=os.environ.get("GEMINI_API_KEY", ""),
    )


def parse_origins(raw: str) -> tuple[str, ...]:
    """Comma-separated list → tuple. An origin never ends in a slash, so strip one if given."""
    return tuple(o.strip().rstrip("/") for o in raw.split(",") if o.strip())
