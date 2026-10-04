"""Vector search against the real test database, with vectors chosen so results are known."""

import psycopg
import pytest
from pgvector.psycopg import register_vector_async

from app.retrieval import document_exists, search_chunks
from tests.seeding import add_chunk, add_document, axis


@pytest.fixture
async def db(database_url):
    async with await psycopg.AsyncConnection.connect(database_url, autocommit=True) as conn:
        await register_vector_async(conn)
        yield conn


async def test_results_are_ranked_by_cosine_similarity_with_the_right_scores(db):
    doc = await add_document(db, "Doc A")
    await add_chunk(db, doc, 0, "unrelated", axis(1))
    await add_chunk(
        db, doc, 1, "exact match", axis(0), clause_id="3.1.2", heading="3.1 Plan", page=20
    )
    await add_chunk(db, doc, 2, "half related", axis(0, 1))

    results = await search_chunks(db, axis(0), "section_aware")

    assert [r.content for r in results] == ["exact match", "half related", "unrelated"]
    assert [round(r.score, 4) for r in results] == [1.0, 0.7071, 0.0]
    best = results[0]
    assert (best.document_title, best.clause_id, best.heading, best.page) == (
        "Doc A",
        "3.1.2",
        "3.1 Plan",
        20,
    )


async def test_only_the_requested_strategy_is_searched(db):
    doc = await add_document(db, "Doc A")
    await add_chunk(db, doc, 0, "naive chunk", axis(0), strategy="naive")
    await add_chunk(db, doc, 0, "section chunk", axis(0), strategy="section_aware")

    naive = await search_chunks(db, axis(0), "naive")
    section = await search_chunks(db, axis(0), "section_aware")

    assert [r.content for r in naive] == ["naive chunk"]
    assert [r.content for r in section] == ["section chunk"]


async def test_document_filter_restricts_the_search(db):
    doc_a = await add_document(db, "Doc A")
    doc_b = await add_document(db, "Doc B")
    await add_chunk(db, doc_a, 0, "best match, but in A", axis(0))
    await add_chunk(db, doc_b, 0, "weaker match in B", axis(0, 1))

    everywhere = await search_chunks(db, axis(0), "section_aware")
    only_b = await search_chunks(db, axis(0), "section_aware", document_id=doc_b)

    assert everywhere[0].content == "best match, but in A"
    assert [r.content for r in only_b] == ["weaker match in B"]
    assert only_b[0].document_title == "Doc B"


async def test_at_most_top_k_results(db):
    doc = await add_document(db, "Doc A")
    for index in range(8):
        await add_chunk(db, doc, index, f"chunk {index}", axis(0, index + 1))

    assert len(await search_chunks(db, axis(0), "section_aware")) == 5
    assert len(await search_chunks(db, axis(0), "section_aware", top_k=3)) == 3


async def test_empty_corpus_returns_nothing(db):
    assert await search_chunks(db, axis(0), "section_aware") == []


async def test_document_exists(db):
    doc = await add_document(db, "Doc A")
    assert await document_exists(db, doc) is True
    assert await document_exists(db, "00000000-0000-0000-0000-000000000000") is False
