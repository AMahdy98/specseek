"""Postgres access: schema bootstrap, connection pool, health check."""

from pathlib import Path

import psycopg
from pgvector.psycopg import register_vector_async
from psycopg_pool import AsyncConnectionPool

# Read once at import time (outside the event loop), so no blocking file I/O in async code.
_SCHEMA_SQL = (Path(__file__).parent / "schema.sql").read_text()

# Arbitrary constant: every app instance takes the same lock, so only one applies the schema.
_SCHEMA_LOCK_ID = 8_163_702


async def apply_schema(database_url: str) -> None:
    """Create extension/tables/indexes if missing. Safe to run on every startup."""
    async with await psycopg.AsyncConnection.connect(database_url) as conn:
        async with conn.transaction():
            # Two instances starting together would race on CREATE ... IF NOT EXISTS.
            # A transaction-scoped advisory lock serializes them; it's released at COMMIT.
            await conn.execute("SELECT pg_advisory_xact_lock(%s)", (_SCHEMA_LOCK_ID,))
            await conn.execute(_SCHEMA_SQL)


async def _configure_connection(conn: psycopg.AsyncConnection) -> None:
    # Teach psycopg to convert Postgres `vector` <-> Python/numpy values on this connection.
    await register_vector_async(conn)


async def open_pool(database_url: str) -> AsyncConnectionPool:
    pool = AsyncConnectionPool(
        database_url,
        min_size=1,
        max_size=10,
        open=False,  # open explicitly below, inside the running event loop
        configure=_configure_connection,
    )
    # wait=True: fail fast at startup if the DB is unreachable, instead of on the first request.
    await pool.open(wait=True, timeout=10)
    return pool


async def ping(pool: AsyncConnectionPool) -> bool:
    """True if a connection can be borrowed and runs a trivial query within 2 s."""
    try:
        async with pool.connection(timeout=2) as conn:
            await conn.execute("SELECT 1")
        return True
    except psycopg.Error:  # includes PoolTimeout and OperationalError
        return False
