"""Document listing behind an interface.

Routes depend on the `DocumentRepository` Protocol; tests inject a fake, production
uses Postgres. Listing uses *cursor* (keyset) pagination.
"""

import base64
import binascii
from datetime import datetime
from typing import Protocol
from uuid import UUID

from fastapi import Request
from psycopg_pool import AsyncConnectionPool

from app.errors import InvalidCursor
from app.models import DocumentPage, DocumentSummary


class DocumentRepository(Protocol):
    """Structural interface (like a C++ concept / pure-virtual base, but duck-typed)."""

    async def list_documents(self, limit: int, cursor: str | None) -> DocumentPage: ...


def encode_cursor(created_at: datetime, document_id: UUID) -> str:
    """Opaque bookmark for "the last row you saw": its sort key, base64-encoded.

    Opaque on purpose: clients must pass it back untouched, which leaves us free to
    change the sort key later without breaking them.
    """
    raw = f"{created_at.isoformat()}|{document_id}"
    return base64.urlsafe_b64encode(raw.encode()).decode()


def decode_cursor(cursor: str) -> tuple[datetime, UUID]:
    try:
        raw = base64.urlsafe_b64decode(cursor.encode()).decode()
        created_at, document_id = raw.split("|")
        return datetime.fromisoformat(created_at), UUID(document_id)
    except (ValueError, binascii.Error) as exc:  # the cursor comes from the client: untrusted
        raise InvalidCursor("The pagination cursor is not valid") from exc


# One query for documents AND their chunk counts (no N+1): LEFT JOIN keeps documents that
# have no chunks, COUNT(c.id) counts only real chunk rows, GROUP BY folds them per document.
_SELECT = """
    SELECT d.id, d.title, d.created_at, COUNT(c.id) AS chunk_count
    FROM documents d
    LEFT JOIN chunks c ON c.document_id = d.id
"""
_GROUP_ORDER_LIMIT = """
    GROUP BY d.id
    ORDER BY d.created_at DESC, d.id DESC
    LIMIT %s
"""
# Keyset condition: "rows that sort after the last one you saw". Postgres compares the
# pair (created_at, id) as a unit; id breaks ties between equal timestamps.
_AFTER_CURSOR = "WHERE (d.created_at, d.id) < (%s, %s)"


class PostgresDocumentRepository:
    def __init__(self, pool: AsyncConnectionPool) -> None:
        self._pool = pool

    async def list_documents(self, limit: int, cursor: str | None) -> DocumentPage:
        # Ask for one row more than requested: if it comes back, there is a next page.
        if cursor is None:
            query, params = _SELECT + _GROUP_ORDER_LIMIT, (limit + 1,)
        else:
            query = _SELECT + _AFTER_CURSOR + _GROUP_ORDER_LIMIT
            params = (*decode_cursor(cursor), limit + 1)

        async with self._pool.connection() as conn:
            rows = await (await conn.execute(query, params)).fetchall()

        items = [
            DocumentSummary(id=row[0], title=row[1], created_at=row[2], chunk_count=row[3])
            for row in rows[:limit]
        ]
        has_more = len(rows) > limit
        next_cursor = encode_cursor(items[-1].created_at, items[-1].id) if has_more else None
        return DocumentPage(items=items, next_cursor=next_cursor)


def get_repository(request: Request) -> DocumentRepository:
    """FastAPI dependency: hands the route the repository created in the lifespan."""
    return request.app.state.repo
