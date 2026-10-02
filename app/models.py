"""Pydantic models: the wire contract of the API.

Request models validate input at the boundary (bad input -> 422 before route code runs).
Response models filter output (only declared fields are serialized).
"""

from typing import Literal

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


class DocumentSummary(BaseModel):
    """One row of GET /v1/documents."""

    id: str
    title: str = Field(min_length=1)
    chunk_count: int = Field(ge=0)
