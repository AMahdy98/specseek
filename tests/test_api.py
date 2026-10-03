"""API and model unit tests. No database: dependencies are overridden."""

from datetime import UTC, datetime
from uuid import UUID

import pytest
from pydantic import ValidationError

from app.models import DocumentSummary

DOC_A = UUID("00000000-0000-0000-0000-00000000000a")
DOC_B = UUID("00000000-0000-0000-0000-00000000000b")
WHEN = datetime(2026, 10, 2, 12, 0, tzinfo=UTC)


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
    assert resp.json() == {"items": [], "next_cursor": None}


async def test_documents_lists_what_the_repository_returns(client, use_repo):
    use_repo(
        [
            DocumentSummary(id=DOC_A, title="Doc A", chunk_count=3, created_at=WHEN),
            DocumentSummary(id=DOC_B, title="Doc B", chunk_count=0, created_at=WHEN),
        ]
    )
    resp = await client.get("/v1/documents")
    assert resp.status_code == 200
    assert resp.json()["items"] == [
        {
            "id": str(DOC_A),
            "title": "Doc A",
            "chunk_count": 3,
            "created_at": "2026-10-02T12:00:00Z",
        },
        {
            "id": str(DOC_B),
            "title": "Doc B",
            "chunk_count": 0,
            "created_at": "2026-10-02T12:00:00Z",
        },
    ]


async def test_documents_passes_limit_and_cursor_to_the_repository(client, use_repo):
    repo = use_repo([])
    await client.get("/v1/documents")
    await client.get("/v1/documents", params={"limit": 5, "cursor": "abc"})
    assert repo.calls == [(20, None), (5, "abc")]


@pytest.mark.parametrize("limit", [0, 101, "many"])
async def test_documents_rejects_an_out_of_range_limit(client, use_repo, limit):
    repo = use_repo([])
    resp = await client.get("/v1/documents", params={"limit": limit})
    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "validation_error"
    assert repo.calls == []  # rejected at the edge; the repository was never reached


@pytest.mark.parametrize(
    "kwargs",
    [
        {"id": DOC_A, "title": "", "chunk_count": 1, "created_at": WHEN},  # empty title
        {"id": DOC_A, "title": "X", "chunk_count": -1, "created_at": WHEN},  # negative count
    ],
)
def test_document_summary_rejects_bad_values(kwargs):
    with pytest.raises(ValidationError):
        DocumentSummary(**kwargs)
