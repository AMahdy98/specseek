"""Integration tests against a real Postgres (skipped if none is running)."""

import httpx
import psycopg

from app.db import apply_schema
from app.main import app


async def test_schema_is_idempotent(database_url):
    await apply_schema(database_url)
    await apply_schema(database_url)  # second run must not fail

    async with await psycopg.AsyncConnection.connect(database_url) as conn:
        cur = await conn.execute(
            "SELECT format_type(atttypid, atttypmod) FROM pg_attribute "
            "WHERE attrelid = 'chunks'::regclass AND attname = 'embedding'"
        )
        assert await cur.fetchone() == ("vector(768)",)


async def test_lifespan_opens_pool_and_health_sees_db(database_url):
    # ASGITransport doesn't run the lifespan, so enter it by hand: this covers the real path
    # (apply_schema -> open_pool -> database_is_up -> ping) with no overrides.
    async with app.router.lifespan_context(app):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
            health = await c.get("/v1/health")
            docs = await c.get("/v1/documents")
    assert health.status_code == 200
    assert health.json() == {"status": "ok", "database": "ok"}
    assert docs.json() == {"items": [], "next_cursor": None}
