"""HTTP routes. Handlers stay thin: validate (Pydantic does it), delegate, return."""

from typing import Annotated

from fastapi import APIRouter, Depends

from app.models import DocumentSummary, HealthResponse
from app.repository import DocumentRepository, get_repository

router = APIRouter()

# Type alias so every handler that needs the repo declares it the same way.
RepoDep = Annotated[DocumentRepository, Depends(get_repository)]


@router.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    # Liveness only for now. Phase 1: also ping the DB.
    return HealthResponse(status="ok")


@router.get("/documents", response_model=list[DocumentSummary])
async def list_documents(repo: RepoDep) -> list[DocumentSummary]:
    return await repo.list_documents()
