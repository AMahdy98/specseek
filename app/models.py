"""Pydantic models: the wire contract of the API.

Request models validate input at the boundary (bad input -> 422 before route code runs).
Response models filter output (only declared fields are serialized).
"""

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field


class ErrorDetail(BaseModel):
    code: str  # stable identifier, e.g. "not_found"
    message: str
    request_id: str | None
    details: list[dict[str, str]] | None = None  # only for validation errors


class ErrorResponse(BaseModel):
    """Body of every non-2xx response. Built in app/api/error_handlers.py."""

    error: ErrorDetail


class HealthResponse(BaseModel):
    """Body of GET /v1/health."""

    status: Literal["ok", "degraded"]
    database: Literal["ok", "unavailable"]


class IngestRequest(BaseModel):
    # Relative to the server's data directory, e.g. "public/NPR-7150.2D.pdf".
    path: str = Field(min_length=1, max_length=300)


class IngestResponse(BaseModel):
    document_id: UUID
    title: str
    created: bool  # True with 201; False with 200 when this content was already ingested
    chunk_counts: dict[str, int]  # per chunking strategy


class QueryRequest(BaseModel):
    question: str = Field(min_length=3, max_length=1000)
    document_id: UUID | None = None  # restrict the search to one document
    # Which set of chunks to search. Both exist so the evaluation can compare them.
    strategy: Literal["naive", "section_aware"] = "section_aware"


class Citation(BaseModel):
    """One passage that was given to the model as context."""

    document_id: UUID
    document: str
    clause_id: str | None
    heading: str | None
    page: int
    snippet: str  # the start of the passage, for display
    score: float  # cosine similarity between question and passage, 0..1


class QueryResponse(BaseModel):
    answer: str
    refused: bool  # True when the answer is "I don't know based on these documents."
    strategy: Literal["naive", "section_aware"]
    citations: list[Citation]  # best match first


class DocumentSummary(BaseModel):
    """One row of GET /v1/documents."""

    id: UUID
    title: str = Field(min_length=1)
    chunk_count: int = Field(ge=0)  # across both chunking strategies
    created_at: datetime


class DocumentPage(BaseModel):
    """Body of GET /v1/documents: newest first."""

    items: list[DocumentSummary]
    next_cursor: str | None  # pass back as ?cursor=... for the next page; null on the last page
