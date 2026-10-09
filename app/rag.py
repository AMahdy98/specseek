"""Query service: question -> embed -> search -> prompt -> generate -> answer + sources.

Knows nothing about HTTP (the evaluation script calls it directly). Raises domain errors.
"""

import asyncio
import logging
import time
from dataclasses import dataclass
from uuid import UUID

from psycopg_pool import AsyncConnectionPool

from app.errors import NotFound, ProviderError
from app.ingest.types import Strategy
from app.llm import Provider
from app.prompt import PROMPT_VERSION, REFUSAL, SYSTEM_PROMPT, build_prompt
from app.retrieval import TOP_K, RetrievedChunk, document_exists, search_chunks

logger = logging.getLogger("specseek.query")


@dataclass(frozen=True)
class QueryResult:
    answer: str
    refused: bool  # the model (or we) said the documents don't contain the answer
    sources: list[RetrievedChunk]  # the passages the model was given, best match first
    timings_ms: dict[str, int]  # how long each stage took: embed, search, generate


# The whole question must be answered or failed within this. It is deliberately below the
# UI's 60 s timeout (frontend/src/api.ts), so the user gets our error with a request ID
# instead of a client-side "took too long". Worst case without it: embed and generate each
# use 3 attempts x 15 s plus backoff, about 100 s.
QUERY_DEADLINE_SECONDS = 50.0


async def answer_question(
    question: str,
    pool: AsyncConnectionPool,
    provider: Provider,
    strategy: Strategy = "section_aware",
    document_id: UUID | None = None,
    query_vector: list[float] | None = None,
    deadline_seconds: float | None = None,  # None: QUERY_DEADLINE_SECONDS
) -> QueryResult:
    """Answer `question` from the ingested documents.

    `query_vector` lets a caller that asks the same question several times (the evaluation,
    once per chunking strategy) embed it once and pass the vector in.
    """
    if deadline_seconds is None:
        deadline_seconds = QUERY_DEADLINE_SECONDS
    try:
        # On expiry asyncio cancels whatever is awaited inside (the HTTP call or a retry
        # sleep), so no work continues for an answer nobody will receive.
        async with asyncio.timeout(deadline_seconds):
            return await _answer(question, pool, provider, strategy, document_id, query_vector)
    except TimeoutError:
        logger.error("query_deadline_exceeded", extra={"deadline_s": deadline_seconds})
        raise ProviderError(
            f"LLM provider did not answer within {deadline_seconds:.0f} seconds"
        ) from None


async def _answer(
    question: str,
    pool: AsyncConnectionPool,
    provider: Provider,
    strategy: Strategy,
    document_id: UUID | None,
    query_vector: list[float] | None,
) -> QueryResult:
    started = time.perf_counter()

    # 1. Embed the question (as a *query*, so it lands near passages that answer it).
    if query_vector is None:
        (query_vector,) = await provider.embed([question], kind="query")
    embedded_at = time.perf_counter()

    # 2. Retrieve. The connection goes back to the pool before the slow LLM call.
    async with pool.connection() as conn:
        if document_id is not None and not await document_exists(conn, document_id):
            raise NotFound(f"Document '{document_id}' not found")
        chunks = await search_chunks(conn, query_vector, strategy, document_id)
    searched_at = time.perf_counter()

    # 3. Generate, unless there is nothing to ground an answer on.
    if chunks:
        answer = await provider.generate(SYSTEM_PROMPT, build_prompt(question, chunks))
    else:
        answer = REFUSAL  # empty corpus: refusing costs no LLM call
    generated_at = time.perf_counter()

    refused = REFUSAL.lower() in answer.lower()
    timings_ms = {
        "embed": round((embedded_at - started) * 1000),
        "search": round((searched_at - embedded_at) * 1000),
        "generate": round((generated_at - searched_at) * 1000),
    }
    logger.info(
        "query_complete",
        extra={
            # The question text itself is not logged: users may type sensitive things.
            "question_chars": len(question),
            "strategy": strategy,
            "document_filter": document_id is not None,
            "prompt_version": PROMPT_VERSION,
            "top_k": TOP_K,
            "chunks": len(chunks),
            "top_score": round(chunks[0].score, 4) if chunks else None,
            "refused": refused,
            **{f"{stage}_ms": duration for stage, duration in timings_ms.items()},
        },
    )
    return QueryResult(answer=answer, refused=refused, sources=chunks, timings_ms=timings_ms)
