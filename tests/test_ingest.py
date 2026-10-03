"""Ingestion tests: path guard (unit) and the full endpoint against a real test database.

The embedding provider is always a fake, so these never touch the network.
"""

from dataclasses import replace
from pathlib import Path

import httpx
import psycopg
import pytest

from app.api.routes import get_provider
from app.config import get_settings
from app.errors import IngestError, NotFound, ProviderError
from app.ingest.service import resolve_data_path
from app.llm import EMBEDDING_DIM
from app.main import app
from tests.pdf_factory import BOLD, REGULAR, make_pdf

# ---------------------------------------------------------------- path guard (no DB)


def test_resolve_accepts_a_pdf_inside_the_data_directory(tmp_path):
    make_pdf(tmp_path / "doc.pdf", [[(72, 100, "text", REGULAR)]])
    assert resolve_data_path(tmp_path, "doc.pdf") == (tmp_path / "doc.pdf").resolve()


@pytest.mark.parametrize("requested", ["../secret.pdf", "/etc/passwd.pdf", "sub/../../x.pdf"])
def test_resolve_rejects_paths_outside_the_data_directory(tmp_path, requested):
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    (tmp_path / "secret.pdf").write_text("outside")
    with pytest.raises(IngestError, match="inside the data directory"):
        resolve_data_path(data_dir, requested)


def test_resolve_rejects_non_pdf_and_missing_files(tmp_path):
    (tmp_path / "notes.txt").write_text("hello")
    with pytest.raises(IngestError, match="Only .pdf"):
        resolve_data_path(tmp_path, "notes.txt")
    with pytest.raises(NotFound):
        resolve_data_path(tmp_path, "missing.pdf")


# ---------------------------------------------------------------- endpoint (real test DB)


class FakeProvider:
    """Deterministic unit vectors; records how often it was asked."""

    def __init__(self) -> None:
        self.calls = 0

    async def embed(self, texts: list[str], kind: str) -> list[list[float]]:
        self.calls += 1
        vectors = []
        for text in texts:
            vector = [0.0] * EMBEDDING_DIM
            vector[len(text) % EMBEDDING_DIM] = 1.0
            vectors.append(vector)
        return vectors


class FailingProvider:
    async def embed(self, texts: list[str], kind: str) -> list[list[float]]:
        raise ProviderError("Embedding provider unavailable after 6 attempts")


def _sample_pdf(path: Path, marker: str = "A") -> Path:
    return make_pdf(
        path,
        [
            [
                (72, 100, "3.1 Software Life Cycle Planning", BOLD),
                (
                    72,
                    130,
                    f"3.1.1 Planning covers the software aspects of project {marker}.",
                    REGULAR,
                ),
                (72, 160, "3.1.2 The project manager shall assess options. [SWE-033]", REGULAR),
            ]
        ],
        title=f"Sample Standard {marker}",
    )


@pytest.fixture
async def ingest_env(database_url, tmp_path):
    """The real app (lifespan, pool, test DB) with a fake provider and a temp data directory."""
    provider = FakeProvider()
    settings = replace(get_settings(), data_dir=tmp_path)
    app.dependency_overrides[get_provider] = lambda: provider
    app.dependency_overrides[get_settings] = lambda: settings
    async with app.router.lifespan_context(app):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            yield client, provider, tmp_path
    app.dependency_overrides.clear()


async def _row_counts(database_url: str) -> tuple[int, int]:
    async with await psycopg.AsyncConnection.connect(database_url) as conn:
        documents = await (await conn.execute("SELECT COUNT(*) FROM documents")).fetchone()
        chunks = await (await conn.execute("SELECT COUNT(*) FROM chunks")).fetchone()
    return documents[0], chunks[0]


async def test_first_ingest_creates_document_and_chunks(ingest_env, database_url):
    client, provider, data_dir = ingest_env
    _sample_pdf(data_dir / "sample.pdf")

    resp = await client.post("/v1/ingest", json={"path": "sample.pdf"})

    assert resp.status_code == 201
    body = resp.json()
    assert body["created"] is True
    assert body["title"] == "Sample Standard A"
    assert body["chunk_counts"] == {"naive": 1, "section_aware": 2}
    assert await _row_counts(database_url) == (1, 3)

    async with await psycopg.AsyncConnection.connect(database_url) as conn:
        cursor = await conn.execute(
            "SELECT clause_id, parent_heading, page, vector_dims(embedding) FROM chunks "
            "WHERE strategy = 'section_aware' ORDER BY chunk_index"
        )
        assert await cursor.fetchall() == [
            ("3.1.1", "3.1 Software Life Cycle Planning", 1, EMBEDDING_DIM),
            ("3.1.2", "3.1 Software Life Cycle Planning", 1, EMBEDDING_DIM),
        ]


async def test_ingesting_the_same_file_twice_is_idempotent(ingest_env, database_url):
    client, provider, data_dir = ingest_env
    _sample_pdf(data_dir / "sample.pdf")

    first = await client.post("/v1/ingest", json={"path": "sample.pdf"})
    second = await client.post("/v1/ingest", json={"path": "sample.pdf"})

    assert (first.status_code, second.status_code) == (201, 200)
    assert second.json()["created"] is False
    assert second.json()["document_id"] == first.json()["document_id"]
    assert second.json()["chunk_counts"] == first.json()["chunk_counts"]
    assert await _row_counts(database_url) == (1, 3)
    assert provider.calls == 1  # the replay never reached the (paid) embedding provider


async def test_identity_is_the_content_not_the_filename(ingest_env, database_url):
    client, _, data_dir = ingest_env
    original = _sample_pdf(data_dir / "sample.pdf")
    (data_dir / "renamed-copy.pdf").write_bytes(original.read_bytes())
    _sample_pdf(data_dir / "different.pdf", marker="B")

    first = await client.post("/v1/ingest", json={"path": "sample.pdf"})
    copy = await client.post("/v1/ingest", json={"path": "renamed-copy.pdf"})
    other = await client.post("/v1/ingest", json={"path": "different.pdf"})

    assert copy.status_code == 200
    assert copy.json()["document_id"] == first.json()["document_id"]
    assert other.status_code == 201
    assert other.json()["document_id"] != first.json()["document_id"]


async def test_provider_failure_returns_502_and_leaves_no_rows(ingest_env, database_url):
    client, _, data_dir = ingest_env
    _sample_pdf(data_dir / "sample.pdf")
    app.dependency_overrides[get_provider] = lambda: FailingProvider()

    resp = await client.post(
        "/v1/ingest", json={"path": "sample.pdf"}, headers={"X-Request-ID": "r1"}
    )

    assert resp.status_code == 502
    assert resp.json()["error"]["code"] == "provider_error"
    assert resp.json()["error"]["request_id"] == "r1"
    assert await _row_counts(database_url) == (0, 0)


async def test_bad_requests_map_to_the_right_status(ingest_env, database_url):
    client, _, data_dir = ingest_env
    (data_dir / "notes.txt").write_text("hello")
    (data_dir / "fake.pdf").write_text("not really a pdf")

    missing = await client.post("/v1/ingest", json={"path": "nope.pdf"})
    traversal = await client.post("/v1/ingest", json={"path": "../outside.pdf"})
    wrong_type = await client.post("/v1/ingest", json={"path": "notes.txt"})
    corrupt = await client.post("/v1/ingest", json={"path": "fake.pdf"})
    no_body = await client.post("/v1/ingest", json={})

    assert (missing.status_code, missing.json()["error"]["code"]) == (404, "not_found")
    assert (traversal.status_code, traversal.json()["error"]["code"]) == (422, "ingest_failed")
    assert (wrong_type.status_code, wrong_type.json()["error"]["code"]) == (422, "ingest_failed")
    assert (corrupt.status_code, corrupt.json()["error"]["code"]) == (422, "ingest_failed")
    assert (no_body.status_code, no_body.json()["error"]["code"]) == (422, "validation_error")
    assert await _row_counts(database_url) == (0, 0)
