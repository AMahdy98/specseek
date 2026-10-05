"""GeminiProvider tests. httpx.MockTransport answers instead of the network: no key, no cost."""

import json
import math

import httpx
import pytest

from app.errors import ProviderError
from app.llm import EMBEDDING_DIM, GeminiProvider


def _provider(handler, api_key: str = "test-key") -> tuple[GeminiProvider, list[float]]:
    """A provider wired to `handler`, plus the list of delays it 'slept' (nothing really waits)."""
    slept: list[float] = []

    async def fake_sleep(seconds: float) -> None:
        slept.append(seconds)

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    return GeminiProvider(api_key, client, sleep=fake_sleep), slept


def _ok(request: httpx.Request, value: float = 3.0) -> httpx.Response:
    count = len(json.loads(request.content)["requests"])
    return httpx.Response(200, json={"embeddings": [{"values": [value] * EMBEDDING_DIM}] * count})


async def test_embed_sends_the_expected_request():
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return _ok(request)

    provider, _ = _provider(handler)
    await provider.embed(["first text", "second text"], kind="document")

    (request,) = seen
    assert request.url.path.endswith("/models/gemini-embedding-001:batchEmbedContents")
    assert request.headers["x-goog-api-key"] == "test-key"
    assert "test-key" not in str(request.url)  # the key never goes in the URL
    body = json.loads(request.content)
    assert [r["content"]["parts"][0]["text"] for r in body["requests"]] == [
        "first text",
        "second text",
    ]
    assert all(r["taskType"] == "RETRIEVAL_DOCUMENT" for r in body["requests"])
    assert all(r["outputDimensionality"] == EMBEDDING_DIM for r in body["requests"])


async def test_queries_use_the_query_task_type():
    bodies = []

    def handler(request: httpx.Request) -> httpx.Response:
        bodies.append(json.loads(request.content))
        return _ok(request)

    provider, _ = _provider(handler)
    await provider.embed(["what is safety-critical software?"], kind="query")
    assert bodies[0]["requests"][0]["taskType"] == "RETRIEVAL_QUERY"


async def test_vectors_are_normalised_to_unit_length():
    provider, _ = _provider(_ok)  # the fake returns [3.0] * 768, far from unit length
    (vector,) = await provider.embed(["text"], kind="document")

    assert len(vector) == EMBEDDING_DIM
    assert math.isclose(math.sqrt(sum(v * v for v in vector)), 1.0, rel_tol=1e-9)


async def test_large_inputs_are_split_into_batches_of_100_in_order():
    batch_sizes: list[int] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests = json.loads(request.content)["requests"]
        batch_sizes.append(len(requests))
        # Encode each text's number in the vector so we can check the order afterwards.
        embeddings = [
            {
                "values": [float(r["content"]["parts"][0]["text"]) + 1.0]
                + [0.0] * (EMBEDDING_DIM - 1)
            }
            for r in requests
        ]
        return httpx.Response(200, json={"embeddings": embeddings})

    provider, _ = _provider(handler)
    vectors = await provider.embed([str(i) for i in range(250)], kind="document")

    assert batch_sizes == [100, 100, 50]
    assert len(vectors) == 250
    assert all(v[0] == 1.0 for v in vectors)  # each normalised to [1, 0, 0, ...]


async def test_retries_after_rate_limit_then_succeeds():
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        if calls == 1:
            return httpx.Response(429, headers={"Retry-After": "7"}, json={"error": {}})
        if calls == 2:
            return httpx.Response(503, json={"error": {"message": "overloaded"}})
        return _ok(request)

    provider, slept = _provider(handler)
    vectors = await provider.embed(["text"], kind="document")

    assert len(vectors) == 1
    assert calls == 3
    assert slept == [7.0, 4.0]  # first: what the provider asked for; second: 2**attempt


async def test_retry_delay_can_come_from_the_error_body():
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        if calls == 1:
            body = {"error": {"code": 429, "details": [{"retryDelay": "34s"}]}}
            return httpx.Response(429, json=body)
        return _ok(request)

    provider, slept = _provider(handler)
    await provider.embed(["text"], kind="document")
    assert slept == [34.0]


async def test_a_long_requested_wait_fails_immediately_instead_of_retrying():
    # Regression (docs/BUGS.md, 2026-10-02): the free tier's daily quota answers
    # "retry in 16464s". Retrying six times over five minutes could never succeed.
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        body = {"error": {"message": "Quota exceeded", "details": [{"retryDelay": "16464s"}]}}
        return httpx.Response(429, json=body)

    provider, slept = _provider(handler)
    with pytest.raises(ProviderError, match="quota exhausted; retry in about 275 minutes"):
        await provider.embed(["text"], kind="document")
    assert calls == 1
    assert slept == []


async def test_gives_up_after_six_attempts_with_a_provider_error():
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(500, json={"error": {"message": "boom"}})

    provider, slept = _provider(handler)
    with pytest.raises(ProviderError, match="unavailable after 6 attempts"):
        await provider.embed(["text"], kind="document")
    assert calls == 6
    assert slept == [2.0, 4.0, 8.0, 16.0, 32.0]


async def test_timeouts_are_retried_then_reported_as_provider_error():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("too slow", request=request)

    provider, slept = _provider(handler)
    with pytest.raises(ProviderError):
        await provider.embed(["text"], kind="document")
    assert len(slept) == 5


async def test_client_errors_are_not_retried():
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(400, json={"error": {"message": "API key not valid"}})

    provider, slept = _provider(handler)
    with pytest.raises(ProviderError, match="rejected the request"):
        await provider.embed(["text"], kind="document")
    assert calls == 1
    assert slept == []


async def test_wrong_dimension_is_a_provider_error():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"embeddings": [{"values": [1.0] * 10}]})

    provider, _ = _provider(handler)
    with pytest.raises(ProviderError, match="10 dimensions"):
        await provider.embed(["text"], kind="document")


async def test_missing_api_key_fails_without_any_network_call():
    def handler(request: httpx.Request) -> httpx.Response:
        raise AssertionError("must not be called")

    provider, _ = _provider(handler, api_key="")
    with pytest.raises(ProviderError, match="not configured"):
        await provider.embed(["text"], kind="document")


# ---------------------------------------------------------------- generation


def _answer(text: str = "An answer.", finish: str = "STOP") -> dict:
    return {"candidates": [{"content": {"parts": [{"text": text}]}, "finishReason": finish}]}


async def test_generate_sends_system_instruction_prompt_and_temperature_zero():
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json=_answer("The provider shall assess [Doc, 4.4.2.9]."))

    provider, _ = _provider(handler)
    answer = await provider.generate("the rules", "passages and question")

    assert answer == "The provider shall assess [Doc, 4.4.2.9]."
    (request,) = seen
    assert request.url.path.endswith("/models/gemini-3.5-flash-lite:generateContent")
    assert request.headers["x-goog-api-key"] == "test-key"
    body = json.loads(request.content)
    assert body["systemInstruction"] == {"parts": [{"text": "the rules"}]}
    assert body["contents"] == [{"role": "user", "parts": [{"text": "passages and question"}]}]
    assert body["generationConfig"]["temperature"] == 0


async def test_generate_joins_multi_part_answers_and_strips_whitespace():
    def handler(request: httpx.Request) -> httpx.Response:
        parts = [{"text": "  First part. "}, {"text": "Second part.\n"}]
        return httpx.Response(
            200, json={"candidates": [{"content": {"parts": parts}, "finishReason": "STOP"}]}
        )

    provider, _ = _provider(handler)
    assert await provider.generate("s", "p") == "First part. Second part."


async def test_generate_with_no_candidates_is_a_provider_error():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"promptFeedback": {"blockReason": "SAFETY"}})

    provider, _ = _provider(handler)
    with pytest.raises(ProviderError, match="no answer \\(SAFETY\\)"):
        await provider.generate("s", "p")


async def test_a_cut_off_answer_is_not_passed_off_as_complete():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=_answer("The provider shall", finish="MAX_TOKENS"))

    provider, _ = _provider(handler)
    with pytest.raises(ProviderError, match="cut off"):
        await provider.generate("s", "p")


async def test_an_empty_answer_is_a_provider_error():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200, json={"candidates": [{"content": {}, "finishReason": "MAX_TOKENS"}]}
        )

    provider, _ = _provider(handler)
    with pytest.raises(ProviderError, match="empty answer"):
        await provider.generate("s", "p")


async def test_interactive_calls_give_up_after_three_attempts():
    # A person is waiting on /v1/query: two quick retries, then fail, not minutes of backoff.
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        raise httpx.ReadTimeout("too slow", request=request)

    provider, slept = _provider(handler)
    with pytest.raises(ProviderError, match="after 3 attempts \\(ReadTimeout\\)"):
        await provider.generate("s", "p")
    assert calls == 3
    assert slept == [2.0, 4.0]

    calls = 0
    with pytest.raises(ProviderError, match="after 3 attempts"):
        await provider.embed(["a question"], kind="query")
    assert calls == 3


async def test_generate_recovers_from_one_overloaded_response():
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        if calls == 1:
            return httpx.Response(503, json={"error": {"message": "high demand"}})
        return httpx.Response(200, json=_answer("ok"))

    provider, slept = _provider(handler)
    assert await provider.generate("s", "p") == "ok"
    assert slept == [2.0]
