"""Application factory + lifespan (startup/shutdown).

Run locally:  uv run --env-file .env uvicorn app.main:app --reload
"""

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

import httpx
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.api.error_handlers import install_error_handlers
from app.api.middleware import RequestContextMiddleware
from app.api.routes import router
from app.config import get_settings
from app.db import apply_schema, open_pool
from app.llm import GeminiProvider
from app.logging_config import configure_logging
from app.models import ErrorResponse
from app.rate_limit import TokenBucket
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
        settings.gemini_api_key,
        http_client,
        embedding_model=settings.embedding_model,
        generation_model=settings.generation_model,
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
# Added last = outermost: every response gets the CORS headers, including the last-resort 500
# from RequestContextMiddleware. Without them the browser hides the error body from the UI.
app.add_middleware(
    CORSMiddleware,
    allow_origins=list(get_settings().cors_allowed_origins),
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type", "X-Request-ID"],
    # Response headers JavaScript may read; by default a cross-origin page sees almost none.
    expose_headers=["X-Request-ID", "Server-Timing"],
    max_age=600,  # the browser may cache a preflight answer for 10 minutes
)
install_error_handlers(app)
# Created here, not in the lifespan: it needs no I/O, and it is per process by nature.
app.state.query_limiter = TokenBucket(
    capacity=get_settings().query_burst,
    refill_per_second=get_settings().query_rate_per_minute / 60,
)
app.include_router(router, prefix="/v1")


def mount_ui(app: FastAPI, directory: Path) -> None:
    """Serve the built UI at `/`. Must be called after the API routes are registered:
    routes are matched in order, so /v1/... is answered by the API and only what is left
    falls through to the files. html=True makes `/` return index.html."""
    app.mount("/", StaticFiles(directory=directory, html=True), name="ui")


_static_dir = get_settings().static_dir
if _static_dir is not None and _static_dir.is_dir():
    mount_ui(app, _static_dir)
