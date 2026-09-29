"""Phase 0 API and model tests."""

import httpx
import pytest
from pydantic import ValidationError

from app.main import app
from app.models import DocumentSummary
from app.repository import InMemoryDocumentRepository


async def test_lifespan_wires_real_repository():
    # ASGITransport doesn't run the lifespan, so enter it by hand. This covers the real
    # path with no overrides: lifespan -> app.state.repo -> get_repository -> route.
    async with app.router.lifespan_context(app):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
            resp = await c.get("/documents")
    assert resp.status_code == 200
    assert resp.json() == []


async def test_health_ok(client):
    resp = await client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


async def test_documents_empty(client, use_repo):
    use_repo([])
    resp = await client.get("/documents")
    assert resp.status_code == 200
    assert resp.json() == []


async def test_documents_lists_seeded(client, use_repo):
    use_repo(
        [
            DocumentSummary(id="doc-a", title="Doc A", chunk_count=3),
            DocumentSummary(id="doc-b", title="Doc B", chunk_count=0),
        ]
    )
    resp = await client.get("/documents")
    assert resp.status_code == 200
    assert resp.json() == [
        {"id": "doc-a", "title": "Doc A", "chunk_count": 3},
        {"id": "doc-b", "title": "Doc B", "chunk_count": 0},
    ]


async def test_list_returns_copy():
    repo = InMemoryDocumentRepository([DocumentSummary(id="x", title="X", chunk_count=1)])
    first = await repo.list_documents()
    first.clear()
    assert len(await repo.list_documents()) == 1


@pytest.mark.parametrize(
    "kwargs",
    [
        {"id": "x", "title": "", "chunk_count": 1},  # empty title
        {"id": "x", "title": "X", "chunk_count": -1},  # negative count
    ],
)
def test_document_summary_rejects_bad_values(kwargs):
    with pytest.raises(ValidationError):
        DocumentSummary(**kwargs)
