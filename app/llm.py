"""Embedding and text generation behind a small provider interface.

The rest of the app depends on `Provider`, never on Gemini directly, so the vendor can be
swapped and tests can use a fake. Gemini is called over plain HTTPS with httpx: no SDK.
"""

import asyncio
import logging
import math
from collections.abc import Awaitable, Callable
from typing import Literal, Protocol

import httpx

from app.errors import ProviderError

logger = logging.getLogger("specseek.provider")

EMBEDDING_DIM = 768  # must match `vector(768)` in app/schema.sql
EmbedKind = Literal["document", "query"]


class Provider(Protocol):
    async def embed(self, texts: list[str], kind: EmbedKind) -> list[list[float]]:
        """One unit-length vector of EMBEDDING_DIM floats per input text, in order."""
        ...

    async def generate(self, system: str, prompt: str) -> str:
        """The model's answer to `prompt`, following the instructions in `system`."""
        ...


_BASE_URL = "https://generativelanguage.googleapis.com/v1beta"
_BATCH_SIZE = 100  # texts per HTTP request
_MAX_BACKOFF_SECONDS = 60.0
_RETRYABLE_STATUS = {429, 500, 502, 503, 504}  # rate limited, or the provider's own fault
# Two retry budgets, because the caller's patience differs:
_BATCH_ATTEMPTS = 6  # ingestion is a background-style job: waiting minutes is fine
_INTERACTIVE_ATTEMPTS = 3  # a person is waiting for /v1/query: at most ~6 s of backoff
_MAX_OUTPUT_TOKENS = 2048
# Gemini embeds a passage and a question differently, so that a question lands near the
# passages that answer it rather than near other questions.
_TASK_TYPE = {"document": "RETRIEVAL_DOCUMENT", "query": "RETRIEVAL_QUERY"}


class GeminiProvider:
    def __init__(
        self,
        api_key: str,
        client: httpx.AsyncClient,
        embedding_model: str = "gemini-embedding-001",
        generation_model: str = "gemini-3.8-flash",
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,  # injectable for tests
    ) -> None:
        self._api_key = api_key
        self._client = client
        self._embedding_model = embedding_model
        self._generation_model = generation_model
        self._sleep = sleep

    async def embed(self, texts: list[str], kind: EmbedKind) -> list[list[float]]:
        attempts = _BATCH_ATTEMPTS if kind == "document" else _INTERACTIVE_ATTEMPTS
        vectors: list[list[float]] = []
        for start in range(0, len(texts), _BATCH_SIZE):
            batch = texts[start : start + _BATCH_SIZE]
            payload = {
                "requests": [
                    {
                        "model": f"models/{self._embedding_model}",
                        "content": {"parts": [{"text": text}]},
                        "taskType": _TASK_TYPE[kind],
                        "outputDimensionality": EMBEDDING_DIM,
                    }
                    for text in batch
                ]
            }
            path = f"models/{self._embedding_model}:batchEmbedContents"
            data = await self._post(path, payload, attempts)
            embeddings = data.get("embeddings", [])
            if len(embeddings) != len(batch):
                raise ProviderError("Embedding provider returned an unexpected number of vectors")
            vectors.extend(_unit_vector(item["values"]) for item in embeddings)
        return vectors

    async def generate(self, system: str, prompt: str) -> str:
        payload = {
            # The system instruction is sent separately from the user content, so the model
            # treats our rules as rules and the retrieved text + question as material.
            "systemInstruction": {"parts": [{"text": system}]},
            "contents": [{"role": "user", "parts": [{"text": prompt}]}],
            "generationConfig": {
                # temperature 0: always pick the most likely next token. Same question and
                # context -> (near-)identical answer, which the evaluation depends on.
                "temperature": 0,
                "maxOutputTokens": _MAX_OUTPUT_TOKENS,
            },
        }
        path = f"models/{self._generation_model}:generateContent"
        data = await self._post(path, payload, _INTERACTIVE_ATTEMPTS)
        return _answer_text(data)

    async def _post(self, path: str, payload: dict, max_attempts: int) -> dict:
        """POST with retries. Retries only what can succeed on a second try."""
        if not self._api_key:
            raise ProviderError("LLM provider is not configured (GEMINI_API_KEY is empty)")

        for attempt in range(1, max_attempts + 1):
            try:
                response = await self._client.post(
                    f"{_BASE_URL}/{path}",
                    json=payload,
                    # Key in a header, never in the URL: URLs end up in logs and proxies.
                    headers={"x-goog-api-key": self._api_key},
                )
            except httpx.TransportError as exc:  # timeouts, DNS, connection reset
                problem, delay = type(exc).__name__, _backoff(attempt)
            else:
                if response.status_code == 200:
                    return response.json()
                problem = f"HTTP {response.status_code}"
                if response.status_code not in _RETRYABLE_STATUS:
                    # 400/401/403/404: our request, key or model name is wrong; retrying
                    # cannot help.
                    logger.error("provider_rejected_request", extra=_error_fields(response))
                    raise ProviderError(f"LLM provider rejected the request ({problem})")
                requested = _retry_after(response)
                if requested is not None and requested > _MAX_BACKOFF_SECONDS:
                    # e.g. a daily quota: the provider says "come back in 4 hours".
                    # Retrying for a few minutes cannot succeed, so fail now and say why.
                    logger.error("provider_quota_exhausted", extra=_error_fields(response))
                    raise ProviderError(
                        "LLM provider quota exhausted; "
                        f"retry in about {math.ceil(requested / 60)} minutes"
                    )
                delay = requested or _backoff(attempt)

            if attempt == max_attempts:
                break
            logger.warning(
                "provider_retry",
                extra={"problem": problem, "attempt": attempt, "delay_s": delay},
            )
            await self._sleep(delay)

        logger.error("provider_unavailable", extra={"problem": problem, "attempts": max_attempts})
        raise ProviderError(f"LLM provider unavailable after {max_attempts} attempts ({problem})")


def _backoff(attempt: int) -> float:
    """Exponential backoff: 2, 4, 8, 16, 32 seconds (capped)."""
    return min(2.0**attempt, _MAX_BACKOFF_SECONDS)


def _retry_after(response: httpx.Response) -> float | None:
    """How long the provider asks us to wait, if it says: header first, then the error body."""
    header = response.headers.get("Retry-After", "")
    if header.isdigit():
        return float(header)
    try:
        details = response.json()["error"].get("details", [])
    except (ValueError, KeyError, AttributeError):
        return None
    for detail in details:
        delay = str(detail.get("retryDelay", ""))  # e.g. "34s"
        if delay.endswith("s") and delay[:-1].replace(".", "", 1).isdigit():
            return float(delay[:-1])
    return None


def _error_fields(response: httpx.Response) -> dict[str, object]:
    try:
        message = response.json()["error"]["message"]
    except (ValueError, KeyError, TypeError):
        message = response.text[:200]
    return {"status": response.status_code, "provider_message": message}


def _answer_text(data: dict) -> str:
    """Pull the answer out of a generateContent response, or explain why there is none."""
    candidates = data.get("candidates") or []
    if not candidates:
        # The provider's safety filter refused the *prompt*; there is no answer at all.
        reason = (data.get("promptFeedback") or {}).get("blockReason", "no candidates")
        raise ProviderError(f"LLM provider returned no answer ({reason})")

    candidate = candidates[0]
    parts = (candidate.get("content") or {}).get("parts") or []
    text = "".join(part.get("text", "") for part in parts).strip()
    finish_reason = candidate.get("finishReason", "")
    if not text:
        raise ProviderError(f"LLM provider returned an empty answer ({finish_reason})")
    if finish_reason == "MAX_TOKENS":
        # A cut-off answer may be missing its citations or end mid-sentence: don't pass it
        # off as complete.
        raise ProviderError("LLM provider's answer was cut off (output token limit)")
    return text


def _unit_vector(values: list[float]) -> list[float]:
    """Scale to length 1 (L2 normalisation).

    Gemini's 768-dim output is a truncation of its 3072-dim vector and is not unit length
    (measured: norm 0.58). With unit vectors, cosine similarity equals the dot product and
    scores are comparable between chunks.
    """
    if len(values) != EMBEDDING_DIM:
        raise ProviderError(f"Embedding provider returned {len(values)} dimensions")
    norm = math.sqrt(sum(value * value for value in values))
    if norm == 0:
        raise ProviderError("Embedding provider returned a zero vector")
    return [value / norm for value in values]
