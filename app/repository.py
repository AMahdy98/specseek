"""Document storage behind an interface.

Phase 0: an in-memory implementation. Phase 1 adds a Postgres implementation with the
same interface; the route code does not change. That is the point of the Protocol.
"""

from typing import Protocol

from fastapi import Request

from app.models import DocumentSummary


class DocumentRepository(Protocol):
    """Structural interface (like a C++ concept / pure-virtual base, but duck-typed).

    Any class with a matching `async def list_documents` satisfies it; no inheritance needed.
    """

    async def list_documents(self) -> list[DocumentSummary]: ...


class InMemoryDocumentRepository:
    def __init__(self, documents: list[DocumentSummary] | None = None) -> None:
        # `None` default + copy, never `documents=[]`: a default list is created once at
        # function definition and shared by every instance.
        self._documents = list(documents) if documents is not None else []

    async def list_documents(self) -> list[DocumentSummary]:
        # Return a copy so callers can't mutate internal state.
        return list(self._documents)


def get_repository(request: Request) -> DocumentRepository:
    """FastAPI dependency: hands the route the repository created in the lifespan."""
    return request.app.state.repo
