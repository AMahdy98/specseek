"""Shared fixtures.

Environment is set at the very top, before anything imports `app`: tests must use their own
database and must never be able to call the real embedding provider.
"""

import os

_DEV_DATABASE_URL = os.environ.get(
    "DATABASE_URL", "postgresql://specseek:specseek@localhost:5432/specseek"
)
TEST_DATABASE_URL = _DEV_DATABASE_URL.rsplit("/", 1)[0] + "/specseek_test"
os.environ["DATABASE_URL"] = TEST_DATABASE_URL
os.environ["GEMINI_API_KEY"] = ""

from collections.abc import AsyncIterator, Callable  # noqa: E402

import httpx  # noqa: E402
import psycopg  # noqa: E402
import pytest  # noqa: E402

from app.api.routes import database_is_up  # noqa: E402
from app.db import apply_schema  # noqa: E402
from app.main import app  # noqa: E402
from app.models import DocumentPage, DocumentSummary  # noqa: E402
from app.rate_limit import TokenBucket  # noqa: E402
from app.repository import get_repository  # noqa: E402

# The real limiter (6 at once, 12 per minute) would reject most of the test suite.
# Tests of the limit itself override `get_query_limiter` with a small bucket.
app.state.query_limiter = TokenBucket(capacity=100_000, refill_per_second=100_000)


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


class FakeDocumentRepository:
    """Test double for the DocumentRepository Protocol: no database, records its calls."""

    def __init__(self, documents: list[DocumentSummary]) -> None:
        self.documents = list(documents)
        self.calls: list[tuple[int, str | None]] = []

    async def list_documents(self, limit: int, cursor: str | None) -> DocumentPage:
        self.calls.append((limit, cursor))
        return DocumentPage(items=self.documents[:limit], next_cursor=None)


@pytest.fixture
def use_repo() -> Callable[[list[DocumentSummary]], FakeDocumentRepository]:
    """Swap the real repository dependency for a fake seeded with the given documents."""

    def _use(documents: list[DocumentSummary]) -> FakeDocumentRepository:
        repo = FakeDocumentRepository(documents)
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
    """Integration tests only: an empty `specseek_test` database with the schema applied.

    Skips (does not fail) when no Postgres is reachable; start one with
    `docker compose up -d db`. The dev database `specseek` is never touched.
    """
    try:
        admin = await psycopg.AsyncConnection.connect(
            _DEV_DATABASE_URL, connect_timeout=2, autocommit=True
        )
    except psycopg.OperationalError:
        pytest.skip("Postgres not reachable; run `docker compose up -d db`")
    async with admin:
        exists = await admin.execute("SELECT 1 FROM pg_database WHERE datname = 'specseek_test'")
        if await exists.fetchone() is None:
            # CREATE DATABASE cannot run inside a transaction, hence autocommit above.
            await admin.execute("CREATE DATABASE specseek_test")

    await apply_schema(TEST_DATABASE_URL)
    async with await psycopg.AsyncConnection.connect(TEST_DATABASE_URL) as conn:
        await conn.execute("TRUNCATE documents CASCADE")  # CASCADE also empties chunks
    return TEST_DATABASE_URL
