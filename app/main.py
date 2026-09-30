"""Application factory + lifespan (startup/shutdown).

Run locally:  uv run --env-file .env uvicorn app.main:app --reload
"""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.routes import router
from app.config import get_settings
from app.db import apply_schema, open_pool
from app.repository import InMemoryDocumentRepository


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    # Startup: runs once, before the first request is accepted.
    settings = get_settings()
    await apply_schema(settings.database_url)
    app.state.pool = await open_pool(settings.database_url)
    app.state.repo = InMemoryDocumentRepository()  # Phase 2: Postgres-backed repository
    try:
        yield
    finally:
        # Shutdown: uvicorn got SIGTERM/SIGINT, stopped accepting connections and waited for
        # in-flight requests. Now return every connection to Postgres cleanly.
        await app.state.pool.close()


app = FastAPI(title="SpecSeek", lifespan=lifespan)
app.include_router(router, prefix="/v1")
