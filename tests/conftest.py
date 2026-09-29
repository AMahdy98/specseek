from collections.abc import AsyncIterator, Callable

import httpx
import pytest

from app.main import app
from app.models import DocumentSummary
from app.repository import InMemoryDocumentRepository, get_repository


@pytest.fixture
async def client() -> AsyncIterator[httpx.AsyncClient]:
    """In-process HTTP client: goes through the full ASGI stack, but no socket.

    Note: ASGITransport does NOT run the lifespan, so app.state.repo is never set here.
    Tests that hit routes needing the repo must use `use_repo` below.
    """
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        yield c
    app.dependency_overrides.clear()  # don't leak overrides into the next test


@pytest.fixture
def use_repo() -> Callable[[list[DocumentSummary]], InMemoryDocumentRepository]:
    """Swap the real repository dependency for one seeded with the given documents."""

    def _use(documents: list[DocumentSummary]) -> InMemoryDocumentRepository:
        repo = InMemoryDocumentRepository(documents)
        app.dependency_overrides[get_repository] = lambda: repo
        return repo

    return _use
