"""POST /v1/query end to end: real app, real test database, fake embedding + LLM."""

import httpx
import psycopg
import pytest
from pgvector.psycopg import register_vector_async

from app.api.routes import get_provider
from app.errors import ProviderError
from app.main import app
from app.prompt import REFUSAL, SYSTEM_PROMPT
from tests.seeding import add_chunk, add_document, axis


class FakeLLM:
    """Embeds every question as axis(0); answers with a canned string; records its calls."""

    def __init__(
        self, answer: str = "The project manager shall assess options [Doc A, 3.1.2]."
    ) -> None:
        self.answer = answer
        self.embed_calls: list[tuple[list[str], str]] = []
        self.generate_calls: list[tuple[str, str]] = []

    async def embed(self, texts: list[str], kind: str) -> list[list[float]]:
        self.embed_calls.append((texts, kind))
        return [axis(0) for _ in texts]

    async def generate(self, system: str, prompt: str) -> str:
        self.generate_calls.append((system, prompt))
        return self.answer


class TimingOutLLM(FakeLLM):
    async def generate(self, system: str, prompt: str) -> str:
        raise ProviderError("LLM provider unavailable after 3 attempts (ReadTimeout)")


@pytest.fixture
async def db(database_url):
    async with await psycopg.AsyncConnection.connect(database_url, autocommit=True) as conn:
        await register_vector_async(conn)
        yield conn


@pytest.fixture
async def api(database_url):
    llm = FakeLLM()
    app.dependency_overrides[get_provider] = lambda: llm
    async with app.router.lifespan_context(app):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            yield client, llm
    app.dependency_overrides.clear()


async def _seed(db):
    doc_a = await add_document(db, "Doc A")
    await add_chunk(
        db, doc_a, 0, "3.1.2 The project manager shall assess options. [SWE-033]", axis(0),
        clause_id="3.1.2", heading="3.1 Software Life Cycle Planning", page=20,
    )  # fmt: skip
    await add_chunk(db, doc_a, 1, "3.1.3 Somewhat related text.", axis(0, 1), clause_id="3.1.3")
    await add_chunk(db, doc_a, 0, "naive window of text", axis(0), strategy="naive", page=3)
    return doc_a


async def test_query_returns_the_answer_and_the_passages_as_citations(api, db):
    client, llm = api
    doc_a = await _seed(db)

    resp = await client.post("/v1/query", json={"question": "Who assesses acquisition options?"})

    assert resp.status_code == 200
    body = resp.json()
    assert body["answer"] == "The project manager shall assess options [Doc A, 3.1.2]."
    assert body["refused"] is False
    assert body["strategy"] == "section_aware"
    assert body["citations"] == [
        {
            "document_id": str(doc_a),
            "document": "Doc A",
            "clause_id": "3.1.2",
            "heading": "3.1 Software Life Cycle Planning",
            "page": 20,
            "snippet": "3.1.2 The project manager shall assess options. [SWE-033]",
            "score": 1.0,
        },
        {
            "document_id": str(doc_a),
            "document": "Doc A",
            "clause_id": "3.1.3",
            "heading": None,
            "page": 1,
            "snippet": "3.1.3 Somewhat related text.",
            "score": 0.7071,
        },
    ]


async def test_the_model_receives_the_rules_the_passages_and_the_question(api, db):
    client, llm = api
    await _seed(db)

    await client.post("/v1/query", json={"question": "Who assesses acquisition options?"})

    assert llm.embed_calls == [(["Who assesses acquisition options?"], "query")]
    ((system, prompt),) = llm.generate_calls
    assert system == SYSTEM_PROMPT
    assert "[1] Document: Doc A | Clause: 3.1.2" in prompt
    assert "The project manager shall assess options. [SWE-033]" in prompt
    assert prompt.endswith("Question: Who assesses acquisition options?")
    assert "naive window" not in prompt  # the other strategy's chunks are not mixed in


async def test_strategy_selects_which_chunks_are_searched(api, db):
    client, _ = api
    await _seed(db)

    resp = await client.post("/v1/query", json={"question": "anything?", "strategy": "naive"})

    assert resp.json()["strategy"] == "naive"
    assert [c["snippet"] for c in resp.json()["citations"]] == ["naive window of text"]
    assert resp.json()["citations"][0]["clause_id"] is None


async def test_a_refusal_from_the_model_is_flagged(api, db):
    client, llm = api
    await _seed(db)
    llm.answer = REFUSAL

    resp = await client.post("/v1/query", json={"question": "What is the capital of France?"})

    assert resp.status_code == 200  # a refusal is a valid answer, not an error
    assert resp.json()["answer"] == REFUSAL
    assert resp.json()["refused"] is True
    assert len(resp.json()["citations"]) == 2  # what was searched is still shown


async def test_empty_corpus_refuses_without_calling_the_model(api, db):
    client, llm = api

    resp = await client.post("/v1/query", json={"question": "Anything at all?"})

    assert resp.status_code == 200
    assert resp.json() == {
        "answer": REFUSAL,
        "refused": True,
        "strategy": "section_aware",
        "citations": [],
    }
    assert llm.generate_calls == []


async def test_document_filter_and_unknown_document(api, db):
    client, _ = api
    doc_a = await _seed(db)
    doc_b = await add_document(db, "Doc B")
    await add_chunk(db, doc_b, 0, "text in B", axis(0, 2))

    only_b = await client.post(
        "/v1/query", json={"question": "anything?", "document_id": str(doc_b)}
    )
    unknown = await client.post(
        "/v1/query",
        json={"question": "anything?", "document_id": "00000000-0000-0000-0000-000000000000"},
    )

    assert [c["document"] for c in only_b.json()["citations"]] == ["Doc B"]
    assert only_b.json()["citations"][0]["document_id"] != str(doc_a)
    assert unknown.status_code == 404
    assert unknown.json()["error"]["code"] == "not_found"


async def test_llm_timeout_becomes_a_502_error_envelope(api, db):
    client, _ = api
    await _seed(db)
    app.dependency_overrides[get_provider] = lambda: TimingOutLLM()

    resp = await client.post(
        "/v1/query", json={"question": "Who assesses options?"}, headers={"X-Request-ID": "q-1"}
    )

    assert resp.status_code == 502
    assert resp.json() == {
        "error": {
            "code": "provider_error",
            "message": "LLM provider unavailable after 3 attempts (ReadTimeout)",
            "request_id": "q-1",
        }
    }


@pytest.mark.parametrize(
    "body",
    [
        {},  # no question
        {"question": "hi"},  # too short
        {"question": "x" * 1001},  # too long
        {"question": "valid question?", "strategy": "magic"},  # unknown strategy
        {"question": "valid question?", "document_id": "not-a-uuid"},
    ],
)
async def test_invalid_requests_are_rejected_before_any_provider_call(api, db, body):
    client, llm = api
    resp = await client.post("/v1/query", json=body)
    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "validation_error"
    assert llm.embed_calls == []
