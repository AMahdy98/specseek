"""Insert documents and chunks with hand-picked vectors, so search results are predictable."""

import math
from uuid import UUID

import psycopg
from pgvector import Vector

from app.llm import EMBEDDING_DIM


def axis(*indexes: int) -> list[float]:
    """A unit vector pointing equally along the given axes.

    axis(0) and axis(1) are perpendicular (similarity 0); axis(0) and axis(0, 1) are 45°
    apart (similarity 0.7071); axis(0) with itself is similarity 1.
    """
    vector = [0.0] * EMBEDDING_DIM
    for index in indexes:
        vector[index] = 1.0 / math.sqrt(len(indexes))
    return vector


async def add_document(conn: psycopg.AsyncConnection, title: str) -> UUID:
    cursor = await conn.execute(
        "INSERT INTO documents (title, source_path, content_hash) VALUES (%s, %s, %s) RETURNING id",
        (title, f"{title}.pdf", f"{abs(hash(title)):064d}"[:64]),
    )
    (document_id,) = await cursor.fetchone()
    return document_id


async def add_chunk(
    conn: psycopg.AsyncConnection,
    document_id: UUID,
    index: int,
    content: str,
    vector: list[float],
    strategy: str = "section_aware",
    clause_id: str | None = None,
    heading: str | None = None,
    page: int = 1,
) -> None:
    await conn.execute(
        "INSERT INTO chunks (document_id, strategy, chunk_index, clause_id, parent_heading, "
        "page, content, embedding) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)",
        (document_id, strategy, index, clause_id, heading, page, content, Vector(vector)),
    )
