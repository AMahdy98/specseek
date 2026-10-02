# Interview topics tracker

Status: `—` not started · `built` (in the code) · `studied` (explained, not built) · `drilled` (answered correctly out loud in a mock).
Partial means some of the topic exists; the pointer says which part.

## A. Built in SpecSeek

| Topic | Phase | Status | Pointer |
|---|---|---|---|
| RESTful design, verbs, status codes, PUT vs PATCH | 0–3 | built (partial: 2 GETs) | `app/api/routes.py` |
| API versioning (`/v1`) | 1 | built | `app/main.py` (`include_router(prefix="/v1")`) |
| Idempotency (SHA-256 content hash on ingest) | 2 | — | |
| Cursor pagination | 2 | — | |
| ETags / HTTP caching (opt) | 2 | — | |
| Validation layers + exception hierarchy | 1 | built (hierarchy + handlers; first real `raise` comes in phase 2) | `app/errors.py`, `app/api/error_handlers.py` |
| Error handling backend → frontend (LLM timeout) | 3, 5 | — | |
| Parameterized queries / SQL injection | 1 | built (partial: advisory-lock query only) | `app/db.py:apply_schema` |
| CORS | 5 | — | |
| Rate limiting, token bucket (opt) | 3 | — | |
| LLM response cache (opt) | 3 | — | |
| Observability: JSON logs, request ID, stage timing | 1, 3 | built (partial: logs + request ID + per-request duration; stage timing in phase 3) | `app/logging_config.py`, `app/api/middleware.py` |
| Performance: p50/p95, slow-endpoint checklist | 4 | — | `docs/PERF.md` |
| Graceful shutdown / lifespan | 1 | built | `app/main.py:lifespan`, Dockerfile `exec` CMD; verified exit code 0 on `docker compose stop` |
| Event loop / asyncio, `run_in_executor` | 0, 2 | built (partial: async endpoints; no executor use yet) | `app/api/routes.py` |
| Dependency injection | 0 | built | `app/repository.py:get_repository`, `tests/conftest.py:use_repo` |
| TDD (chunkers test-first) | 2 | built | `tests/test_chunkers.py` (23 tests red against stubs before `app/ingest/chunkers.py` was written) |
| Relational vs non-relational, ACID | 1 | — | |
| Indexes (B-tree, vector index, EXPLAIN ANALYZE) | 1, 2 | built (partial: indexes exist, no EXPLAIN yet) | `app/schema.sql` |
| N+1 → JOIN/GROUP BY | 2 | — | |
| ID design (UUID v4 vs v7) | 1 | built | `app/schema.sql`, DECISIONS.md |
| ORM vs raw SQL | 1 | — | |
| Containers vs VMs, Dockerfile layers, Compose | 1 | built | `Dockerfile`, `docker-compose.yml` |
| Cloud Run (scale to zero, cold starts, timeouts, SIGTERM) | 6 | — | |
| Cloud Storage / signed URLs (opt) | 6 | — | |
| Kubernetes & IaC (study only) | 6 | — | |
| RAG end to end | 2–4 | built (partial: parsing + both chunkers; no embeddings yet) | `app/ingest/parser.py`, `app/ingest/chunkers.py` |
| Vector DB choice (pgvector vs dedicated) | 3 | — | |
| TanStack Query, server vs client state | 5 | — | |
| State management comparison | 5 | — | |
| Hooks (effects, cleanup, memoization with measurement) | 5 | — | |
| Rendering (reconciliation, StrictMode, Profiler) | 5 | — | |
| Lazy loading, skeletons, Fragments | 5 | — | |
| XSS-safe rendering of LLM output | 5 | — | |
| JS/TS fundamentals (scope, closures, `this`, event loop) | 5 | — | |

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
