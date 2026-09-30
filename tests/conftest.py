from collections.abc import AsyncIterator, Callable

import httpx
import psycopg
import pytest

from app.api.routes import database_is_up
from app.config import get_settings
from app.main import app
from app.models import DocumentSummary
from app.repository import InMemoryDocumentRepository, get_repository


@pytest.fixture
async def client() -> AsyncIterator[httpx.AsyncClient]:
    """In-process HTTP client: goes through the full ASGI stack, but no socket.

    Note: ASGITransport does NOT run the lifespan, so app.state has no pool or repo here.
    Unit tests override the dependencies instead (`use_repo`, `db_up`).
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


@pytest.fixture
def db_up() -> Callable[[bool], None]:
    """Pretend the database is up (True) or down (False) without touching Postgres."""

    def _set(is_up: bool) -> None:
        app.dependency_overrides[database_is_up] = lambda: is_up

    return _set


@pytest.fixture
async def database_url() -> str:
    """Integration tests only: skip (not fail) when no Postgres is reachable.

    Start one with `docker compose up -d db`.
    """
    url = get_settings().database_url
    try:
        conn = await psycopg.AsyncConnection.connect(url, connect_timeout=2)
    except psycopg.OperationalError:
        pytest.skip("Postgres not reachable; run `docker compose up -d db`")
    await conn.close()
    return url
