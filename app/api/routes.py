"""HTTP routes. Handlers stay thin: validate (Pydantic does it), delegate, return.

Mounted under /v1 in app/main.py.
"""

from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request, Response, status
from psycopg_pool import AsyncConnectionPool

from app.config import Settings, get_settings
from app.db import ping
from app.ingest.service import ingest_pdf, resolve_data_path
from app.llm import Provider
from app.models import (
    DocumentPage,
    ErrorResponse,
    HealthResponse,
    IngestRequest,
    IngestResponse,
)
from app.repository import DocumentRepository, get_repository

router = APIRouter()


def get_pool(request: Request) -> AsyncConnectionPool:
    return request.app.state.pool


def get_provider(request: Request) -> Provider:
    return request.app.state.provider


async def database_is_up(request: Request) -> bool:
    """Dependency: can we reach Postgres right now? Overridden in unit tests."""
    return await ping(request.app.state.pool)


# Type aliases so every handler declares its dependencies the same way.
RepoDep = Annotated[DocumentRepository, Depends(get_repository)]
DbUpDep = Annotated[bool, Depends(database_is_up)]
PoolDep = Annotated[AsyncConnectionPool, Depends(get_pool)]
ProviderDep = Annotated[Provider, Depends(get_provider)]
SettingsDep = Annotated[Settings, Depends(get_settings)]


@router.get(
    "/health",
    response_model=HealthResponse,
    responses={503: {"model": HealthResponse, "description": "Database unreachable"}},
)
async def health(db_up: DbUpDep, response: Response) -> HealthResponse:
    if not db_up:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        return HealthResponse(status="degraded", database="unavailable")
    return HealthResponse(status="ok", database="ok")


@router.get("/documents", response_model=DocumentPage)
async def list_documents(
    repo: RepoDep,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    cursor: Annotated[str | None, Query(max_length=200)] = None,
) -> DocumentPage:
    """Ingested documents, newest first. Follow `next_cursor` until it is null."""
    return await repo.list_documents(limit=limit, cursor=cursor)


@router.post(
    "/ingest",
    response_model=IngestResponse,
    status_code=status.HTTP_201_CREATED,
    responses={
        200: {"model": IngestResponse, "description": "Already ingested; nothing was written"},
        404: {"model": ErrorResponse, "description": "No such file in the data directory"},
        502: {"model": ErrorResponse, "description": "Embedding provider failed"},
    },
)
async def ingest(
    body: IngestRequest,
    response: Response,
    pool: PoolDep,
    provider: ProviderDep,
    settings: SettingsDep,
) -> IngestResponse:
    """Ingest a PDF from the server's data directory. Idempotent: the same file content
    always maps to the same document, however many times it is submitted."""
    path = resolve_data_path(settings.data_dir, body.path)
    result = await ingest_pdf(path, pool, provider)
    if not result.created:
        response.status_code = status.HTTP_200_OK
    return IngestResponse(
        document_id=result.document_id,
        title=result.title,
        created=result.created,
        chunk_counts=result.chunk_counts,
    )
