"""Pydantic models: the wire contract of the API.

Request models validate input at the boundary (bad input -> 422 before route code runs).
Response models filter output (only declared fields are serialized).
"""

from typing import Literal

from pydantic import BaseModel, Field


class HealthResponse(BaseModel):
    """Body of GET /health. Phase 1 adds a `database` field."""

    status: Literal["ok"]


class DocumentSummary(BaseModel):
    """One row of GET /documents."""

    id: str
    title: str = Field(min_length=1)
    chunk_count: int = Field(ge=0)
