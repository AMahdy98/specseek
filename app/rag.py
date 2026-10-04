"""Query service: question -> embed -> search -> prompt -> generate -> answer + sources.

Knows nothing about HTTP (the evaluation script calls it directly). Raises domain errors.
"""

import logging
import time
from dataclasses import dataclass
from uuid import UUID

from psycopg_pool import AsyncConnectionPool

from app.errors import NotFound
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


async def answer_question(
    question: str,
    pool: AsyncConnectionPool,
    provider: Provider,
    strategy: Strategy = "section_aware",
    document_id: UUID | None = None,
) -> QueryResult:
    started = time.perf_counter()

    # 1. Embed the question (as a *query*, so it lands near passages that answer it).
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
            "embed_ms": round((embedded_at - started) * 1000),
            "search_ms": round((searched_at - embedded_at) * 1000),
            "generate_ms": round((generated_at - searched_at) * 1000),
        },
    )
    return QueryResult(answer=answer, refused=refused, sources=chunks)
