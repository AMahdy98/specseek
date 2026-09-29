"""Application factory + lifespan (startup/shutdown).

Run locally:  uv run uvicorn app.main:app --reload
"""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.routes import router
from app.repository import InMemoryDocumentRepository


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    # Startup: runs once, before the first request is accepted.
    # Phase 1 replaces this with a Postgres connection pool.
    app.state.repo = InMemoryDocumentRepository()
    yield
    # Shutdown: runs once, after the server stops accepting requests.
    # Phase 1: close the pool here.


app = FastAPI(title="SpecSeek", lifespan=lifespan)
app.include_router(router)
