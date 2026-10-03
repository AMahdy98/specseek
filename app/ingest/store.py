"""Data layer for ingestion: raw parameterized SQL, one function per statement.

Every value travels as a parameter (`%s`), never by string formatting: the driver sends
the SQL text and the values separately, so a value can never be executed as SQL.
"""

from dataclasses import dataclass
from uuid import UUID

import psycopg
from pgvector import Vector

from app.ingest.types import Chunk


@dataclass(frozen=True)
class DocumentRecord:
    id: UUID
    title: str


async def find_document_by_hash(
    conn: psycopg.AsyncConnection, content_hash: str
) -> DocumentRecord | None:
    cursor = await conn.execute(
        "SELECT id, title FROM documents WHERE content_hash = %s", (content_hash,)
    )
    row = await cursor.fetchone()
    return DocumentRecord(id=row[0], title=row[1]) if row else None


async def insert_document(
    conn: psycopg.AsyncConnection, title: str, source_path: str, content_hash: str
) -> UUID | None:
    """Insert the document; return its new ID, or None if this content already exists.

    The UNIQUE constraint on content_hash makes "check and insert" one atomic step:
    of two concurrent ingests of the same file, exactly one gets an ID back.
    """
    cursor = await conn.execute(
        """
        INSERT INTO documents (title, source_path, content_hash)
        VALUES (%s, %s, %s)
        ON CONFLICT (content_hash) DO NOTHING
        RETURNING id
        """,
        (title, source_path, content_hash),
    )
    row = await cursor.fetchone()
    return row[0] if row else None


async def insert_chunks(
    conn: psycopg.AsyncConnection,
    document_id: UUID,
    chunks: list[Chunk],
    embeddings: list[list[float]],
) -> None:
    rows = [
        (
            document_id,
            chunk.strategy,
            chunk.chunk_index,
            chunk.clause_id,
            chunk.parent_heading,
            chunk.page,
            chunk.content,
            Vector(embedding),
        )
        for chunk, embedding in zip(chunks, embeddings, strict=True)
    ]
    async with conn.cursor() as cursor:
        # executemany sends all rows in one network round-trip (pipeline mode).
        await cursor.executemany(
            """
            INSERT INTO chunks (document_id, strategy, chunk_index, clause_id,
                                parent_heading, page, content, embedding)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            """,
            rows,
        )


async def count_chunks_by_strategy(
    conn: psycopg.AsyncConnection, document_id: UUID
) -> dict[str, int]:
    cursor = await conn.execute(
        "SELECT strategy, COUNT(*) FROM chunks WHERE document_id = %s GROUP BY strategy",
        (document_id,),
    )
    return {strategy: count for strategy, count in await cursor.fetchall()}
