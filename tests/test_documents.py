"""GET /v1/documents against a real test database: JOIN counts, cursor pagination, N+1."""

from datetime import UTC, datetime, timedelta
from uuid import UUID

import httpx
import psycopg
import pytest
from pgvector import Vector
from pgvector.psycopg import register_vector_async

from app.llm import EMBEDDING_DIM
from app.main import app

BASE_TIME = datetime(2026, 1, 1, tzinfo=UTC)


async def _add_document(conn, number: int, chunks: int) -> UUID:
    """Insert document `number` (higher number = newer) with `chunks` chunk rows."""
    cursor = await conn.execute(
        "INSERT INTO documents (title, source_path, content_hash, created_at) "
        "VALUES (%s, %s, %s, %s) RETURNING id",
        (
            f"Doc {number}",
            f"doc{number}.pdf",
            f"{number:064d}",
            BASE_TIME + timedelta(hours=number),
        ),
    )
    (document_id,) = await cursor.fetchone()
    for index in range(chunks):
        await conn.execute(
            "INSERT INTO chunks (document_id, strategy, chunk_index, page, content, embedding) "
            "VALUES (%s, 'naive', %s, 1, 'text', %s)",
            (document_id, index, Vector([1.0] + [0.0] * (EMBEDDING_DIM - 1))),
        )
    return document_id


@pytest.fixture
async def db(database_url):
    async with await psycopg.AsyncConnection.connect(database_url, autocommit=True) as conn:
        await register_vector_async(conn)
        yield conn


@pytest.fixture
async def api(database_url):
    async with app.router.lifespan_context(app):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            yield client


async def test_chunk_counts_come_from_one_join_including_documents_without_chunks(api, db):
    await _add_document(db, 1, chunks=3)
    await _add_document(db, 2, chunks=0)  # LEFT JOIN must keep this one, with count 0

    items = (await api.get("/v1/documents")).json()["items"]

    assert [(d["title"], d["chunk_count"]) for d in items] == [("Doc 2", 0), ("Doc 1", 3)]


async def test_pages_are_newest_first_complete_and_without_duplicates(api, db):
    for number in range(1, 6):
        await _add_document(db, number, chunks=1)

    titles, cursor, pages = [], None, 0
    while True:
        params = {"limit": 2} | ({"cursor": cursor} if cursor else {})
        page = (await api.get("/v1/documents", params=params)).json()
        titles += [d["title"] for d in page["items"]]
        pages += 1
        cursor = page["next_cursor"]
        if cursor is None:
            break

    assert titles == ["Doc 5", "Doc 4", "Doc 3", "Doc 2", "Doc 1"]
    assert pages == 3  # 2 + 2 + 1


async def test_a_cursor_is_stable_when_a_new_document_arrives_between_pages(api, db):
    """The reason for cursor pagination. OFFSET would repeat a row here; the cursor does not."""
    for number in range(1, 5):
        await _add_document(db, number, chunks=0)

    first = (await api.get("/v1/documents", params={"limit": 2})).json()
    assert [d["title"] for d in first["items"]] == ["Doc 4", "Doc 3"]

    await _add_document(db, 9, chunks=0)  # newest: lands in front of everything

    second = await api.get("/v1/documents", params={"limit": 2, "cursor": first["next_cursor"]})
    assert [d["title"] for d in second.json()["items"]] == ["Doc 2", "Doc 1"]

    # What page 2 would have been with OFFSET 2: "Doc 3" again (a duplicate), "Doc 1" pushed off.
    offset_page = await db.execute(
        "SELECT title FROM documents ORDER BY created_at DESC, id DESC LIMIT 2 OFFSET 2"
    )
    assert [row[0] for row in await offset_page.fetchall()] == ["Doc 3", "Doc 2"]


async def test_documents_with_the_same_timestamp_are_not_skipped(api, db):
    # Same created_at for all three: the id in the cursor is what breaks the tie.
    for number in range(1, 4):
        cursor = await db.execute(
            "INSERT INTO documents (title, source_path, content_hash, created_at) "
            "VALUES (%s, 'x.pdf', %s, %s)",
            (f"Twin {number}", f"{number:064d}", BASE_TIME),
        )
    seen, cursor = [], None
    for _ in range(3):
        params = {"limit": 1} | ({"cursor": cursor} if cursor else {})
        page = (await api.get("/v1/documents", params=params)).json()
        seen += [d["title"] for d in page["items"]]
        cursor = page["next_cursor"]
    assert sorted(seen) == ["Twin 1", "Twin 2", "Twin 3"]
    assert cursor is None


async def test_a_cursor_we_did_not_issue_is_rejected(api, db):
    resp = await api.get("/v1/documents", params={"cursor": "not-a-real-cursor"})
    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "invalid_cursor"


async def _list_n_plus_one(conn) -> list[tuple[str, int]]:
    """The naive way, kept here only to show the problem: 1 query + 1 more per document."""
    documents = await (
        await conn.execute("SELECT id, title FROM documents ORDER BY created_at DESC, id DESC")
    ).fetchall()
    result = []
    for document_id, title in documents:
        count = await (
            await conn.execute("SELECT COUNT(*) FROM chunks WHERE document_id = %s", (document_id,))
        ).fetchone()
        result.append((title, count[0]))
    return result


async def test_n_plus_one_versus_one_join(api, db, monkeypatch):
    for number in range(1, 11):
        await _add_document(db, number, chunks=number % 3)

    queries: list[str] = []
    original = psycopg.AsyncConnection.execute

    async def counting_execute(self, query, *args, **kwargs):
        if "documents" in str(query) or "chunks" in str(query):
            queries.append(str(query))
        return await original(self, query, *args, **kwargs)

    monkeypatch.setattr(psycopg.AsyncConnection, "execute", counting_execute)

    naive = await _list_n_plus_one(db)
    naive_queries = len(queries)
    queries.clear()

    joined = (await api.get("/v1/documents")).json()["items"]
    join_queries = len(queries)

    assert [(d["title"], d["chunk_count"]) for d in joined] == naive  # same answer...
    assert naive_queries == 11  # ...but 1 + N round-trips for N = 10 documents
    assert join_queries == 1  # versus a single round-trip
