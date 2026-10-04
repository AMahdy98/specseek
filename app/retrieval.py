"""Vector search: the "R" in RAG. One SQL query, parameterized."""

from dataclasses import dataclass
from uuid import UUID

import psycopg
from pgvector import Vector

from app.ingest.types import Strategy

TOP_K = 5


@dataclass(frozen=True)
class RetrievedChunk:
    document_id: UUID
    document_title: str
    clause_id: str | None
    heading: str | None
    page: int
    content: str
    score: float  # cosine similarity: 1.0 = same direction, 0.0 = unrelated


# `<=>` is pgvector's cosine *distance* (0 = identical, 2 = opposite), so:
#   - ORDER BY distance ascending puts the closest chunks first
#   - similarity = 1 - distance is what we report as the score
# The query vector appears twice (SELECT and ORDER BY), hence two parameters.
_SEARCH = """
    SELECT d.id, d.title, c.clause_id, c.parent_heading, c.page, c.content,
           1 - (c.embedding <=> %(query)s) AS score
    FROM chunks c
    JOIN documents d ON d.id = c.document_id
    WHERE c.strategy = %(strategy)s
      {document_filter}
    ORDER BY c.embedding <=> %(query)s
    LIMIT %(top_k)s
"""
_SEARCH_ALL = _SEARCH.format(document_filter="")
_SEARCH_ONE_DOCUMENT = _SEARCH.format(document_filter="AND c.document_id = %(document_id)s")


async def search_chunks(
    conn: psycopg.AsyncConnection,
    query_vector: list[float],
    strategy: Strategy,
    document_id: UUID | None = None,
    top_k: int = TOP_K,
) -> list[RetrievedChunk]:
    """The `top_k` chunks of one chunking strategy closest in meaning to the query vector."""
    # Only the *fixed* SQL fragment above is chosen by code; every value is a parameter.
    sql = _SEARCH_ALL if document_id is None else _SEARCH_ONE_DOCUMENT
    cursor = await conn.execute(
        sql,
        {
            "query": Vector(query_vector),
            "strategy": strategy,
            "document_id": document_id,
            "top_k": top_k,
        },
    )
    return [RetrievedChunk(*row) for row in await cursor.fetchall()]


async def document_exists(conn: psycopg.AsyncConnection, document_id: UUID) -> bool:
    cursor = await conn.execute("SELECT 1 FROM documents WHERE id = %s", (document_id,))
    return await cursor.fetchone() is not None
