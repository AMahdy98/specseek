"""API and model unit tests. No database: dependencies are overridden."""

import pytest
from pydantic import ValidationError

from app.models import DocumentSummary
from app.repository import InMemoryDocumentRepository


async def test_health_ok(client, db_up):
    db_up(True)
    resp = await client.get("/v1/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok", "database": "ok"}


async def test_health_db_down_returns_503(client, db_up):
    db_up(False)
    resp = await client.get("/v1/health")
    assert resp.status_code == 503
    assert resp.json() == {"status": "degraded", "database": "unavailable"}


async def test_unversioned_path_is_404(client, db_up):
    db_up(True)
    resp = await client.get("/health")
    assert resp.status_code == 404


async def test_documents_empty(client, use_repo):
    use_repo([])
    resp = await client.get("/v1/documents")
    assert resp.status_code == 200
    assert resp.json() == []


async def test_documents_lists_seeded(client, use_repo):
    use_repo(
        [
            DocumentSummary(id="doc-a", title="Doc A", chunk_count=3),
            DocumentSummary(id="doc-b", title="Doc B", chunk_count=0),
        ]
    )
    resp = await client.get("/v1/documents")
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
