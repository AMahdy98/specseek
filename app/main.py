"""Application factory + lifespan (startup/shutdown).

Run locally:  uv run --env-file .env uvicorn app.main:app --reload
"""

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI

from app.api.error_handlers import install_error_handlers
from app.api.middleware import RequestContextMiddleware
from app.api.routes import router
from app.config import get_settings
from app.db import apply_schema, open_pool
from app.llm import GeminiProvider
from app.logging_config import configure_logging
from app.models import ErrorResponse
from app.repository import PostgresDocumentRepository

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
    # One shared HTTP client: it keeps TCP/TLS connections to the provider open and reuses
    # them, instead of paying a new handshake per call. 60 s covers a batch of 100 texts.
    http_client = httpx.AsyncClient(timeout=httpx.Timeout(60.0, connect=10.0))
    app.state.provider = GeminiProvider(
        settings.gemini_api_key, http_client, settings.embedding_model
    )
    app.state.repo = PostgresDocumentRepository(app.state.pool)
    logger.info("startup_complete")
    try:
        yield
    finally:
        # Shutdown: uvicorn got SIGTERM/SIGINT, stopped accepting connections and waited for
        # in-flight requests. Now release what startup acquired, in reverse order.
        await http_client.aclose()
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
