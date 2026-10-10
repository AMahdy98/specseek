# Interview topics tracker

Status: `—` not started · `built` (in the code) · `studied` (explained, not built) · `drilled` (answered correctly out loud in a mock).
Partial means some of the topic exists; the pointer says which part.

## A. Built in SpecSeek

| Topic | Phase | Status | Pointer |
|---|---|---|---|
| RESTful design, verbs, status codes, PUT vs PATCH | 0–3 | built (4 endpoints; PUT/PATCH explained only) | `app/api/routes.py` |
| API versioning (`/v1`) | 1 | built | `app/main.py` (`include_router(prefix="/v1")`) |
| Idempotency (SHA-256 content hash on ingest) | 2 | built | `app/ingest/service.py:ingest_pdf`, `store.insert_document` (ON CONFLICT), `tests/test_ingest.py` |
| Cursor pagination | 2 | built | `app/repository.py` (keyset on `created_at, id`), `tests/test_documents.py` (cursor vs OFFSET under inserts) |
| ETags / HTTP caching (opt) | 2 | — (optional; skipped so far) | |
| Validation layers + exception hierarchy | 1 | built | `app/errors.py`, `app/api/error_handlers.py`; raised by `parser.py`, `service.py` (path guard), `llm.py` |
| Error handling backend → frontend (LLM timeout) | 3, 5 | built (partial: timeout → retries → `ProviderError` → 502 envelope; UI in phase 5) | `app/llm.py:_post`, `tests/test_query.py:test_llm_timeout_becomes_a_502_error_envelope` |
| Parameterized queries / SQL injection | 1 | built | `app/ingest/store.py` (every value is a `%s` parameter) |
| CORS | 5 | drilled | `app/main.py` (CORSMiddleware, outermost), `app/config.py` (`CORS_ALLOWED_ORIGINS`), `tests/test_cors.py` |
| Rate limiting (token bucket) | 3 (built 2026-10-10) | built | `app/rate_limit.py` (`TokenBucket.take`), `routes.query`, `tests/test_rate_limit.py`; DECISIONS.md 2026-10-10 |
| LLM response cache (opt) | 3 | — (optional; not built) | |
| Observability: JSON logs, request ID, stage timing | 1, 3 | built | `app/logging_config.py`, `app/api/middleware.py`; `query_complete` (embed/search/generate ms) in `app/rag.py`, `ingest_complete` in `app/ingest/service.py` |
| Performance: p50/p95, slow-endpoint checklist | 4 | built | `eval/load_test.py`, `docs/PERF.md` (measured p50 1.30 s / p95 2.05 s; checklist walked on real data) |
| Graceful shutdown / lifespan | 1 | built | `app/main.py:lifespan`, Dockerfile `exec` CMD; verified exit code 0 on `docker compose stop` |
| Event loop / asyncio, `run_in_executor` | 0, 2 | built | `app/ingest/service.py`: hashing, parsing, chunking via `asyncio.to_thread` |
| Dependency injection | 0 | built | `app/api/routes.py` (`get_pool`, `get_provider`, `get_repository`), fakes in `tests/conftest.py`, `tests/test_ingest.py` |
| TDD (chunkers test-first) | 2 | built | `tests/test_chunkers.py` (23 tests red against stubs before `app/ingest/chunkers.py` was written) |
| Relational vs non-relational, ACID | 1 | — | |
| Indexes (B-tree, vector index, EXPLAIN ANALYZE) | 1, 2 | built | `app/schema.sql`; measured plans in DECISIONS.md ("What EXPLAIN ANALYZE showed") |
| N+1 → JOIN/GROUP BY | 2 | built | `app/repository.py:_SELECT`; `tests/test_documents.py:test_n_plus_one_versus_one_join` (11 queries vs 1) |
| ID design (UUID v4 vs v7) | 1 | built | `app/schema.sql`, DECISIONS.md |
| ORM vs raw SQL | 1 | — | |
| Containers vs VMs, Dockerfile layers, Compose | 1 | built | `Dockerfile`, `docker-compose.yml` |
| Cloud Run (scale to zero, cold starts, timeouts, SIGTERM) | 6 | studied (not built: no deploy, see DECISIONS.md 2026-10-10) | INTERVIEW.md, "Deployment: studied, not done" |
| Cloud Storage / signed URLs (opt) | 6 | studied (not built: no deploy, see DECISIONS.md 2026-10-10) | INTERVIEW.md, "Deployment: studied, not done" |
| Kubernetes & IaC (study only) | 6 | — | |
| RAG end to end | 2–4 | built and evaluated (EVAL.md) | `app/ingest/`, `app/llm.py`, `app/retrieval.py`, `app/prompt.py`, `app/rag.py` |
| Vector DB choice (pgvector vs dedicated) | 3 | studied | DECISIONS.md, "Retrieval = top-5 by cosine similarity" |
| TanStack Query, server vs client state | 5 | drilled | `frontend/src/hooks.ts` (`useDocuments`, `useAnswer`, `shouldRetry`); client state in `QuestionForm.tsx`, `App.tsx` |
| State management comparison | 5 | studied | DECISIONS.md 2026-10-09; INTERVIEW.md frontend ladder |
| Hooks (effects, cleanup, memoization with measurement) | 5 | built (`useEffect` + cleanup; memoization measured and not used); `useLayoutEffect` studied only | `useElapsedSeconds` in `hooks.ts`; PERF.md frontend section |
| Rendering (reconciliation, StrictMode, Profiler) | 5 | built (Profiler measurement, render-count test); user's own DevTools experiments pending | PERF.md frontend section; `render.test.tsx` |
| Lazy loading, skeletons, Fragments | 5 | built (lazy measured: no gain here) | `AnswerSkeleton` in `AnswerPanel.tsx`, `<>` in `CitationList.tsx` |
| XSS-safe rendering of LLM output | 5 | built | `AnswerPanel.tsx` (text node, no `dangerouslySetInnerHTML`); test "renders HTML in the model output as plain text" |
| JS/TS fundamentals (scope, closures, `this`, event loop) | 5 | in progress: stale closure shown in `useElapsedSeconds`; 4 predict-the-output exercises asked 2026-10-09 | `hooks.ts` |

## C. Study only

| Topic | Status | Notes |
|---|---|---|
| SSR / CSR / SSG / hydration, React vs Next.js | — | |
| Design systems, micro-frontends | — | |
| AuthN/AuthZ, JWT, OAuth2/OIDC, RBAC/ReBAC/ABAC | — | |
| CSRF and other web attacks | — | |
| Message queues (Pub/Sub, SQS, RabbitMQ, Kafka) | — | |
| GraphQL vs REST, gRPC | — | |
| DDD, SOLID, patterns in our code | — | |
| Agent protocols (ADK, A2A, AG-UI, A2UI) | — | |
| Deployment strategies (blue/green, canary, flags) | — | |

## Carry over to TriageBot
- _(nothing yet)_

## Drill log
- 2026-09-30, Phase 0 check questions (not a full 5-question drill):
  blocking in `async def`: partial (right cause and fixes, wrong wait time: 20 s, not 8 s);
  missing `await`: partial (missed "500 at request time via response validation");
  422 vs 500: partial (didn't separate invalid input → 422 from invalid output → 500).
- 2026-10-01, Phase 1a explain-back:
  `db` vs `localhost`: partial (missed: published port 5432 makes `localhost` work from WSL;
  inside a container `localhost` is the container itself);
  SIGTERM + `exec`: partial (missed: uvicorn drains in-flight requests + lifespan closes pool;
  without `exec`, `sh` is PID 1 and doesn't forward SIGTERM → SIGKILL after 10 s → exit 137);
  deps copied before source: correct (add: a changed layer invalidates every layer after it).
- 2026-10-02, Phase 1 drill (5 questions, one at a time):
  1. Finding one user's failed request in the logs: correct (request ID + time; add: where the user
     finds the ID, what the log lines show, and the fallback when they have no ID).
  2. Composite index / leftmost prefix: correct (add: the planner also skips a *usable* index on a
     small table or when the query returns a large share of the rows; `EXPLAIN ANALYZE` shows it).
  3. Crash mid-ingest / atomicity: correct on outcome and property; partial on mechanism (missed:
     it only holds if all inserts share ONE transaction; no COMMIT → Postgres rolls back when the
     connection drops; in autocommit mode 150 chunks would remain).
  4. Why `NotFound` instead of `HTTPException(404)`: wrong (said 404 is a server error that we hide
     from the client; actually 4xx = client error and the client DOES get a 404. Real reason: the
     service layer stays HTTP-agnostic; the status is decided in `error_handlers._STATUS_BY_ERROR`).
     Confused with the unhandled-exception case, where internals are hidden behind a generic 500.
     → Re-drill next session.
  5. Pool size × instances vs DB connection limit: partial (right arithmetic, 200 > 100, and two valid
     fixes: raise the limit, shrink each pool; missed the symptom: Postgres refuses connections with
     "too many connections", so instances fail at startup or requests time out waiting for the pool;
     and the standard fixes: cap max instances, put a pooler such as PgBouncer in front).
  Score: 3 correct, 1 partial, 1 wrong. Re-drill: Q4 (domain errors vs HTTP), status-code families.
- 2026-10-02, Phase 2a explain-back:
  1. Decimal vs outline heading rules: correct (add the third guard: next char uppercase/digit;
     and the reason: a multi-part number never looks like a list item, "A."/"1." always does).
  2. Splitting a 5,000-char clause: partial (right idea and right purpose of overlap; wrong sizes:
     the limit is 3,200 *including* overlap, so pieces are ≤2,800 → chunks of ~2,800 and ~2,600).
  3. Green tests, 66% without clause ID: partial (missed the cause: the tests fed hand-built lines
     straight to the chunker, bypassing the parser where the bug was; and what caught it: an
     aggregate statistic on real documents, not a per-heading comparison).
- 2026-10-03, Phase 2 check questions:
  1. Two simultaneous ingests of one new PDF: partial (right outcome, wrong mechanism: there is no
     mutex in our code. Both miss the pre-check and both embed; the UNIQUE index makes the second
     INSERT wait for the first transaction, then DO NOTHING; the loser returns the winner's document
     with 200. Cost: the embedding is paid twice).
  2. LEFT JOIN + COUNT(c.id): partial (missed COUNT(*) vs COUNT(c.id): with LEFT JOIN a document
     with no chunks becomes one row of NULLs, so COUNT(*) would say 1; COUNT(c.id) skips NULLs → 0.
     A plain JOIN would drop that document entirely).
  3. Re-drill, domain error vs HTTPException: correct (was wrong on 2026-10-02).
- 2026-10-04, Phase 3 explain-back:
  1. Diagnosing a wrong answer: partial (right instinct to look at citations; but the test is
     "is the passage containing the answer among the 5 citations?", not the score, and empty
     citations is not a missed refusal: it means an empty corpus, where we refuse without the LLM).
  2. Why an exact refusal sentence: correct.
  3. What section-aware bought in the example: correct (clause citations; one example proves
     nothing about accuracy; the eval decides).
- 2026-10-04, whiteboard drill #1 (after phase 3):
  Architecture: correct skeleton (Compose, API, Postgres+pgvector, async pool, HTTPS to the models,
  read-only PDF mount). Missed: the ingestion pipeline (parse → chunk → embed → store) and the two
  chunking strategies, which are the centre of the project; model names; what a chunk row holds.
  Query path: correct order (validate → embed → search → generate → respond). Missed: prompt
  construction (the whole step between search and generate), top-5 / cosine / strategy filter,
  the document filter and its 404, the no-passages refusal without an LLM call, what the response
  contains (answer, refused, citations), and what fails where (422 / 404 / 502 after 3 attempts).
  Re-drill: say the numbers (5, 768, temperature 0, 3 attempts) and the failure at each step.
- 2026-10-04, Phase 3 drill (5 questions, one at a time):
  1. Table answer wrongly refused: correct (retrieval vs generation, decided by whether the passage
     is in the citations; add the table-specific causes: a row split across chunks or read in a
     scrambled cell order, and the model refusing over a passage it can't interpret).
  2. Cosine distance and score: correct (precision: score 0 = perpendicular, i.e. unrelated;
     score -1 = opposite; score 1 = same direction, not necessarily identical text).
  3. Temperature 0 and pinned model: partial (right on both in outline; missed that temperature
     works per token, not per answer; that without it the same question gives different answers
     run to run so a grade can't be reproduced; and that the danger of an alias is that it changes
     silently, with no code change on our side).
  4. Retry budgets: partial (3 vs 6 attempts correct; the no-retry case was wrong: it is the
     exhausted daily quota, a 429 whose requested wait exceeds our 60 s maximum, so we fail at once.
     A cut-off answer is a different thing: a 200 response with finishReason MAX_TOKENS).
  5. Releasing the DB connection before the LLM call: correct (add the knock-on effects: with the
     connection held, only 10 questions could be in flight; the 11th waits, `/v1/health`'s 2 s ping
     times out and reports 503 although nothing is broken, and `/v1/documents` stalls too).
  Score: 3 correct, 2 partial. Re-drill: temperature/pinned model (why, in eval terms); the
  quota fail-fast rule; query path with numbers and failure points.
- 2026-10-05/06, Phase 4 drill (5 questions, one at a time):
  1. "Section-aware is 22 points better, ship it": partial (right: 20 questions and one grader give
     no confidence interval; missed: say counts, 14 vs 10 of 18, a gap of 4 questions; it is a paired
     comparison, so name which questions flipped and why; one corpus/model/prompt; the larger
     context section-aware sends. Per-type breakdown is a second sentence: the slices are 3 questions).
  2. Why `--resume` refuses a changed model: correct (model, prompt version, top-k; add: mixing
     models confounds the one variable under test; say "retrieved passages", not "citations").
  3. Which measurement is p95 of 24, and why not the average: partial (why-half correct; missed:
     nearest-rank, ceil(0.95 × 24) = 23rd smallest, i.e. the second-slowest request, always an
     observed value; one retry outlier drags a mean but not a median).
  4. Six concurrent requests in 2 s, not 8: partial (right direction; missed the mechanism: waits
     overlap on one thread; a blocking call serializes them into a staircase 1.3 s … 8 s and
     freezes `/v1/health` too; same bug as blocking I/O on the epoll thread).
  5. Why the latency test was paced: partial (right cause: the provider's 15 requests/minute;
     missed what cannot be claimed: throughput, behaviour under heavy load, the breaking point,
     and that beyond 15/min the test would measure 429s and retries, not SpecSeek).
  Score: 1 correct, 4 partial. Pattern: the first half of a two-part question is answered, the
  second half is dropped. Re-drill: p95 by rank; the blocking-call staircase; limits of the
  latency claim; stating the eval result in counts.
- 2026-10-09, Phase 5 first-pass check questions:
  1. Preflight and whether curl is stopped: correct (add: the preflight is triggered by
     `Content-Type: application/json`; CORS is enforced by browsers only).
  2. UI retries on a 502: correct (zero; the server already tried 3 times; add: one retry only
     when no response arrived at all).
  3. Repeated question and the cache: correct (one request; stale answer after a re-ingest; add:
     the same staleness after a prompt or model change on the server).
  Both parts answered on all three. User asked for deeper explanations of the component code,
  hooks/TanStack Query, CORS, server vs client state and the timeout path (given in chat).
- 2026-10-09, JS fundamentals, 4 predict-the-output exercises (user has no prior JS/TS):
  1. var vs let in a loop with setTimeout: not answered. 2. Stale closure in the timer: partial
  (right that the callback sees the first render's 0; missed that the counter therefore sticks
  at 1). 3. Sync / microtask / task order: not answered. 4. Lost this: not answered.
  All four explained in chat with C++ mappings (capture by reference, call-site this).
  Re-drill all four before the Phase 5 drill; StrictMode double render explained on request.
- 2026-10-10, JS follow-up checks: 1. let in a loop gives each closure its own variable (0, 10):
  correct. 2. Which value handleSubmit sees: correct on the value (the latest), the reason not
  given (the function is re-created on every render, so it closes over that render's values; a
  closure goes stale only when it is created once and kept, as in an effect with []).
- 2026-10-10, Phase 5 drill (5 questions, one at a time):
  1. Which tool holds the document list vs the typed text, and why: correct (TanStack Query vs
     `useState`; say "ownership", not "location": the server owns the list, so the copy can go stale).
  2. `<img onerror>` in the answer: partial (right: shown as plain text; missed the API that would
     make it an attack, `dangerouslySetInnerHTML`, and the name XSS).
  3. `useEffect` cleanup: correct (runs when the component leaves; without it timers pile up; add:
     also runs before the effect re-runs when dependencies change).
  4. Why `useQuery` for a POST: partial (right: a read, cacheable by key; missed the settings:
     `enabled`, `staleTime: Infinity`, no refetch on focus/reconnect, `retry: shouldRetry`).
  5. 404 without CORS headers, and reading the request ID: correct (browser withholds the response;
     add: the UI then shows "could not reach the server" and retries once; the header is
     `Access-Control-Expose-Headers`; the preflight is cached, the response headers are not).
  Score: 3 correct, 2 partial. Re-drill: `dangerouslySetInnerHTML` / XSS; the `useAnswer` settings.
- 2026-10-10, rate limiter check questions:
  1. 10 at once against 6 burst / 12 per minute: correct (6 answered, next token after 5 s).
  2. Why 12 when the provider allows 15, and what is unprotected: correct (retries count; daily quota).
  3. Three instances: correct on the burst (18) and on capping to one instance; add: the rate also
     triples (36/min), and a shared store works for any number of instances if the check-and-take
     is atomic (one UPDATE ... WHERE tokens >= 1, or Redis).
- 2026-10-10, deployment (study-only) check questions:
  1. Scale to zero in the morning: correct (cold-start latency; minimum of one instance; add: that
     costs money all day, and a sleeping database adds its own wake-up).
  2. SIGTERM: partial (right: stops accepting new requests; missed: in-flight requests are
     finished, then the lifespan closes the HTTP client and the pool, then exit. If ignored: after
     about 10 s the platform sends SIGKILL and in-flight requests are cut off mid-response, they
     do not "time out").
  3. Secret vs env var: correct (add: rotation without a rebuild, and an access log).

