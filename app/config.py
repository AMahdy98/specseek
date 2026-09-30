"""Runtime configuration, read from environment variables (12-factor style).

Locally: `uv run --env-file .env ...` loads `.env`. In Docker/Cloud Run: the platform sets env vars.
"""

import os
from dataclasses import dataclass
from functools import lru_cache

# Matches docker-compose.yml's dev credentials. Local-only; never a real secret.
_DEFAULT_DATABASE_URL = "postgresql://specseek:specseek@localhost:5432/specseek"


@dataclass(frozen=True)
class Settings:
    database_url: str
    log_level: str


@lru_cache
def get_settings() -> Settings:
    # lru_cache: read the environment once per process, then reuse the same object.
    return Settings(
        database_url=os.environ.get("DATABASE_URL", _DEFAULT_DATABASE_URL),
        log_level=os.environ.get("LOG_LEVEL", "info"),
    )
