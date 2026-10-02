"""Application factory + lifespan (startup/shutdown).

Run locally:  uv run --env-file .env uvicorn app.main:app --reload
"""

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.error_handlers import install_error_handlers
from app.api.middleware import RequestContextMiddleware
from app.api.routes import router
from app.config import get_settings
from app.db import apply_schema, open_pool
from app.logging_config import configure_logging
from app.models import ErrorResponse
from app.repository import InMemoryDocumentRepository

# At import time: uvicorn has already set up its own loggers by the time it imports
# this module, so this is where we take them over.
configure_logging(get_settings().log_level)
logger = logging.getLogger("specseek")


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    # Startup: runs once, before the first request is accepted.
    settings = get_settings()
    await apply_schema(settings.database_url)
    app.state.pool = await open_pool(settings.database_url)
    app.state.repo = InMemoryDocumentRepository()  # Phase 2: Postgres-backed repository
    logger.info("startup_complete")
    try:
        yield
    finally:
        # Shutdown: uvicorn got SIGTERM/SIGINT, stopped accepting connections and waited for
        # in-flight requests. Now return every connection to Postgres cleanly.
        await app.state.pool.close()
        logger.info("shutdown_complete")


app = FastAPI(
    title="SpecSeek",
    lifespan=lifespan,
    # Document the shared error shape on every route in /docs.
    responses={422: {"model": ErrorResponse}, 500: {"model": ErrorResponse}},
)
app.add_middleware(RequestContextMiddleware)
install_error_handlers(app)
app.include_router(router, prefix="/v1")
