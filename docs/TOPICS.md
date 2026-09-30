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
| Validation layers + exception hierarchy | 1 | built (partial: Pydantic at the edge only) | `app/models.py` |
| Error handling backend → frontend (LLM timeout) | 3, 5 | — | |
| Parameterized queries / SQL injection | 1 | built (partial: advisory-lock query only) | `app/db.py:apply_schema` |
| CORS | 5 | — | |
| Rate limiting, token bucket (opt) | 3 | — | |
| LLM response cache (opt) | 3 | — | |
| Observability: JSON logs, request ID, stage timing | 1, 3 | — | |
| Performance: p50/p95, slow-endpoint checklist | 4 | — | `docs/PERF.md` |
| Graceful shutdown / lifespan | 1 | built | `app/main.py:lifespan`, Dockerfile `exec` CMD; verified exit code 0 on `docker compose stop` |
| Event loop / asyncio, `run_in_executor` | 0, 2 | built (partial: async endpoints; no executor use yet) | `app/api/routes.py` |
| Dependency injection | 0 | built | `app/repository.py:get_repository`, `tests/conftest.py:use_repo` |
| TDD (chunkers test-first) | 2 | — | |
| Relational vs non-relational, ACID | 1 | — | |
| Indexes (B-tree, vector index, EXPLAIN ANALYZE) | 1, 2 | built (partial: indexes exist, no EXPLAIN yet) | `app/schema.sql` |
| N+1 → JOIN/GROUP BY | 2 | — | |
| ID design (UUID v4 vs v7) | 1 | built | `app/schema.sql`, DECISIONS.md |
| ORM vs raw SQL | 1 | — | |
| Containers vs VMs, Dockerfile layers, Compose | 1 | built | `Dockerfile`, `docker-compose.yml` |
| Cloud Run (scale to zero, cold starts, timeouts, SIGTERM) | 6 | — | |
| Cloud Storage / signed URLs (opt) | 6 | — | |
| Kubernetes & IaC (study only) | 6 | — | |
| RAG end to end | 2–4 | — | |
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
