"""Ingestion service: file -> hash -> parse -> chunk -> embed -> store.

Knows nothing about HTTP. Raises domain errors (NotFound, IngestError, ProviderError);
the API layer turns those into status codes.
"""

import asyncio
import hashlib
import logging
import time
from dataclasses import dataclass
from pathlib import Path
from uuid import UUID

from psycopg_pool import AsyncConnectionPool

from app.errors import IngestError, NotFound
from app.ingest import store
from app.ingest.chunkers import chunk_naive, chunk_section_aware
from app.ingest.parser import parse_pdf
from app.ingest.types import Chunk
from app.llm import Provider

logger = logging.getLogger("specseek.ingest")


@dataclass(frozen=True)
class IngestResult:
    document_id: UUID
    title: str
    created: bool  # False: this exact file was ingested before; nothing was written
    chunk_counts: dict[str, int]


def resolve_data_path(data_dir: Path, requested: str) -> Path:
    """Turn a client-supplied relative path into a real file inside `data_dir`.

    Guards against path traversal: "../../etc/passwd" or an absolute path must not let a
    client read files outside the data directory.
    """
    root = data_dir.resolve()
    path = (root / requested).resolve()  # resolve() collapses ".." and follows symlinks
    if not path.is_relative_to(root):
        raise IngestError("Path must be inside the data directory")
    if path.suffix.lower() != ".pdf":
        raise IngestError("Only .pdf files can be ingested")
    if not path.is_file():
        raise NotFound(f"No such file in the data directory: '{requested}'")
    return path


async def ingest_pdf(path: Path, pool: AsyncConnectionPool, provider: Provider) -> IngestResult:
    started = time.perf_counter()

    # File reading, hashing, PDF parsing and chunking are blocking work: run them on a
    # worker thread so the event loop keeps serving other requests meanwhile.
    content_hash = await asyncio.to_thread(_sha256_of_file, path)

    # Cheap early exit: skip parsing and (paid) embedding for a file we already have.
    async with pool.connection() as conn:
        existing = await store.find_document_by_hash(conn, content_hash)
        if existing:
            return await _existing_result(conn, existing)

    title, chunks = await asyncio.to_thread(_parse_and_chunk, path)
    parsed_at = time.perf_counter()

    # No DB connection is held during this network call: it can take minutes.
    embeddings = await provider.embed([chunk.content for chunk in chunks], kind="document")
    embedded_at = time.perf_counter()

    # One transaction: the document row and all its chunks appear together or not at all.
    async with pool.connection() as conn, conn.transaction():
        document_id = await store.insert_document(conn, title, path.name, content_hash)
        if document_id is None:
            # Another request ingested the same file while we were embedding. The UNIQUE
            # constraint made ours a no-op; report the winner's document instead.
            winner = await store.find_document_by_hash(conn, content_hash)
            assert winner is not None
            return await _existing_result(conn, winner)
        await store.insert_chunks(conn, document_id, chunks, embeddings)
    stored_at = time.perf_counter()

    counts = _count_by_strategy(chunks)
    logger.info(
        "ingest_complete",
        extra={
            "document_id": str(document_id),
            "document_title": title,
            "chunks": counts,
            "parse_ms": round((parsed_at - started) * 1000),
            "embed_ms": round((embedded_at - parsed_at) * 1000),
            "store_ms": round((stored_at - embedded_at) * 1000),
        },
    )
    return IngestResult(document_id, title, created=True, chunk_counts=counts)


async def _existing_result(conn, document: store.DocumentRecord) -> IngestResult:
    counts = await store.count_chunks_by_strategy(conn, document.id)
    logger.info("ingest_skipped_duplicate", extra={"document_id": str(document.id)})
    return IngestResult(document.id, document.title, created=False, chunk_counts=counts)


def _sha256_of_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as file:
        # Read in 1 MB blocks so a large PDF never has to fit in memory at once.
        for block in iter(lambda: file.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def _parse_and_chunk(path: Path) -> tuple[str, list[Chunk]]:
    document = parse_pdf(path)
    # Both strategies are stored side by side; the evaluation compares them.
    return document.title, chunk_naive(document.lines) + chunk_section_aware(document.lines)


def _count_by_strategy(chunks: list[Chunk]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for chunk in chunks:
        counts[chunk.strategy] = counts.get(chunk.strategy, 0) + 1
    return counts
