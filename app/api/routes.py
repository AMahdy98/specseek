"""HTTP routes. Handlers stay thin: validate (Pydantic does it), delegate, return.

Mounted under /v1 in app/main.py.
"""

from typing import Annotated

from fastapi import APIRouter, Depends, Request, Response, status

from app.db import ping
from app.models import DocumentSummary, HealthResponse
from app.repository import DocumentRepository, get_repository

router = APIRouter()


async def database_is_up(request: Request) -> bool:
    """Dependency: can we reach Postgres right now? Overridden in unit tests."""
    return await ping(request.app.state.pool)


# Type aliases so every handler declares its dependencies the same way.
RepoDep = Annotated[DocumentRepository, Depends(get_repository)]
DbUpDep = Annotated[bool, Depends(database_is_up)]


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


@router.get("/documents", response_model=list[DocumentSummary])
async def list_documents(repo: RepoDep) -> list[DocumentSummary]:
    return await repo.list_documents()
