# SpecSeek — RAG assistant for engineering standards

## Why this exists
I'm a software engineer with ~3 years of real-time C++/Python systems work (multi-threaded IPC, epoll, state machines, profiling, FDA validation testing). I'm pivoting to a Fullstack AI Engineer role (Python/asyncio, FastAPI, React/TS, GCP Cloud Run, RAG, agents, MCP). I have **zero** web, Docker, cloud or LLM experience. This project must be real, built by me, and defensible line by line in a technical interview.

My time: ~2–3 h on weekdays, a full day on weekends. Hard stop for the backend + eval is one week. React UI and the Cloud Run deploy come right after that.

## How you must work with me (most important section)
1. **Teach, then build.** Before each phase, give me a short explanation (≤10 bullets) of the concepts it needs, ordered from most to least important for the interview. Point out where my C++/systems background maps onto it. Example: the asyncio event loop is an epoll reactor, and a blocking call inside `async def` is the same bug as doing file I/O on the epoll thread.
2. **You (Claude) write all the code** — core logic included (changed 2026-09-29 at my request; I don't write code by hand). Tests come with the code. Because I must still defend every line in an interview, explain the core logic (chunker, retrieval query, prompt construction, query endpoint) in more depth: the key lines, why they're written that way, and the alternative you didn't choose.
3. **Explain every file you create and every new piece of logic.** For each file, say in 2–3 lines what it does and what could go wrong with it.
3a. **Explain every tool / library on first use** in 1–2 plain-language lines (what it is, why we use it). I'm new to fullstack and AI, so assume no prior knowledge of web, Docker, cloud or LLM tooling.
4. **End every session** with three things:
   - A list of "things you should now be able to explain out loud."
   - 3 interview-style check questions that I answer in chat. Correct me if I'm wrong.
   - The exact `git commit` messages I should use. **I commit, not you**, in small commits. The history has to look like real daily work, because it is.
5. **Keep three living docs in `docs/`:**
   - `DECISIONS.md`: every non-obvious choice, with the alternative I rejected and why (pgvector vs Chroma, chunk size, top-k, etc.).
   - `BUGS.md`: every real bug we hit, with symptom, root cause and fix. The interview question "what was the hardest bug?" gets answered from this file.
   - `EVAL.md`: the evaluation log (see below).
6. **Never fabricate** results, metrics, eval answers or bug stories. If something wasn't measured, it doesn't go in the docs.
7. **No scope creep.** If I or you want something on the "Do NOT build" list, say no and write it under "Future work" in `DECISIONS.md` instead.
8. Ask before adding any dependency that isn't in the stack below.
9. When I'm stuck for more than ~20 minutes on something that isn't core learning (tooling, env issues), just fix it and explain the fix.

## Environment
- I develop on **WSL2 Ubuntu** on Windows. Give me Linux/bash commands only, never PowerShell.
- The repo lives in the Linux filesystem (`~/...`), never under `/mnt/c`. Warn me if you see it there.
- Docker is used from inside WSL. If a Docker command fails, first check whether the daemon is reachable (Docker Desktop WSL integration or native engine) before debugging anything else.
- Install all tooling (uv, Node via nvm, gcloud CLI) inside WSL. If `which` shows a binary under `/mnt/c`, flag it: that's the Windows version leaking into PATH.
- I open the API and Vite dev server from a Windows browser at `localhost`. If Postgres port 5432 conflicts with something on the Windows side, map it to 5433 in Compose.

## Stack (fixed)
- Python 3.12, `uv` for env/deps, `ruff` for lint/format
- FastAPI (async endpoints only), Pydantic v2, uvicorn
- PDF parsing: PyMuPDF (`pymupdf`)
- Postgres 16 + pgvector, run via Docker Compose; async driver `psycopg` (v3) + `pgvector` python adapter
- Embeddings and LLM behind a small provider interface (`embed(texts) -> list[vector]`, `generate(prompt) -> str`), so the provider is swappable. Default: whichever provider I have keys for (ask me). Use one embedding model only and note its dimension in DECISIONS.md.
- HTTP client: `httpx.AsyncClient` (never `requests` inside async code)
- Tests: `pytest`, `pytest-asyncio`, FastAPI test client via httpx
- Frontend (phase 5): React + TypeScript + Vite, no framework, **TanStack Query** for data fetching (replaced plain fetch, 2026-09-30)
- Deploy (phase 6): Docker → GCP Artifact Registry → Cloud Run, config via env vars, API key via Secret Manager

## Architecture
All endpoints are mounted under `/v1` (API versioning).
- `POST /v1/ingest`: accepts a PDF (or a path to one in `data/`), parses, chunks, embeds, stores. **Idempotent** via SHA-256 content hash: re-ingesting the same file returns the existing document.
- `POST /v1/query`: body `{question, document_id?}`; embeds the question, top-5 cosine search (optional filter by document), builds a grounded prompt, returns `{answer, citations: [{clause_id, heading, document, snippet, score}]}`
- `GET /v1/documents`: lists ingested docs with chunk counts; **cursor** pagination; ETag / `If-None-Match` → 304 (optional)
- `GET /v1/health`: liveness + DB connectivity
- Errors: custom hierarchy `SpecSeekError` → `NotFound`, `IngestError`, `ProviderError`, … mapped to HTTP responses in one exception handler.
- Observability: structured JSON logs, a request ID per request, timing per stage (embed / search / generate).

Chunking has **two strategies**, both kept in code because the eval compares them:
- `naive`: fixed ~512-character windows, no structure
- `section_aware`: splits on numbered clause headings (e.g. `7.4.2`), ~800 tokens max with 100-token overlap, falls back to recursive splitting for oversized sections. Each chunk carries metadata: `document`, `clause_id`, `parent_heading`, `page`, `strategy`.

Generation system prompt: answer **only** from the provided context, cite clause IDs, preserve normative words exactly ("shall" / "should" / "may"), and say "I don't know based on these documents" when the context doesn't contain the answer.

Suggested layout:
```
specseek/
  app/  main.py  config.py  db.py  models.py
        ingest/ (parser.py, chunkers.py)  retrieval.py  llm.py  api/
  tests/  data/ (PDFs, gitignored if licensing requires)  eval/ (questions.yaml, run_eval.py)
  docs/  (DECISIONS.md, BUGS.md, EVAL.md, TOPICS.md, INTERVIEW.md, PERF.md)
  frontend/  Dockerfile  docker-compose.yml  README.md  CLAUDE.md
```

## Corpus
3–5 real standards documents that I can **legally obtain and use**. Help me choose. Good candidates are freely published specs with numbered clauses and requirements (e.g. AUTOSAR specifications, ECSS standards, NASA software standards). Paywalled ones (ISO 26262, some CiA docs) only if I actually have legitimate copies. Verify the licensing situation with me before we commit any PDF to the repo. Whatever corpus we end up with is what my CV will name.

## Evaluation (the most important artifact, never skip)
- `eval/questions.yaml`: 20 questions **I write** from my domain knowledge, each with the expected answer and the clause ID it lives in. Include some table-based questions, some cross-reference questions, and 2–3 unanswerable ones to test refusal.
- `eval/run_eval.py` runs all 20 against both chunking strategies and saves the raw answers. **I grade them manually** (correct / partially correct / wrong / correctly refused). The script can help tabulate, but a human judgment is final.
- `docs/EVAL.md` records per-strategy scores, and each remaining failure with its category (table split, vocabulary mismatch, near-duplicate chunks, hallucination, etc.) and what I'd change.

## Phases (each ends with a working, committed state)
Every phase also ends with: update `docs/TOPICS.md` and `docs/INTERVIEW.md`, and a 5-question drill on the topics built in that phase.
[ADD] = interview-driven addition. **P** = priority (build first if time runs short); **opt** = optional.

0. **Skeleton + FastAPI/asyncio fundamentals** (done): project setup, `/health`, `/documents` against an in-memory list, Pydantic models, dependency injection, pytest. Teach: ASGI/Starlette/uvicorn request lifecycle, async vs blocking, `run_in_executor` for CPU work.
1. **Docker + Postgres/pgvector**: Dockerfile (layer caching, why requirements are copied before source, multi-stage), Compose with the API and Postgres, schema with a vector column + index, `/health` checks the DB. Plus:
   - [ADD] Retrofit all routes under `/v1` (API versioning: URL vs header vs media type, retiring a version)
   - [ADD] Schema: UUID primary keys (v4 vs v7), unique `content_hash` column, B-tree indexes on `document_id` / `content_hash`
   - [ADD, P] Custom exception hierarchy + one exception handler (validation layers: API / service / data)
   - [ADD, P] Structured JSON logs with a request ID per request
   - [ADD] Graceful shutdown: lifespan opens/closes the DB pool; SIGTERM + draining in-flight requests
   - Raw parameterized SQL via psycopg (SQL injection: safe vs unsafe version; ORM vs raw SQL)
   - Teach: containers vs VMs, Docker vs Compose, relational vs non-relational / ACID
2. **Ingestion**: PDF parsing, both chunkers, embeddings, storage. Chunkers written **test-first (TDD)**: clause IDs preserved, nothing lost, overlap correct. PDF parsing + chunking run off the event loop (`run_in_executor`). Teach: what an embedding is geometrically, cosine similarity, why chunking strategy dominates RAG quality. Plus:
   - [ADD, P] Idempotent `POST /v1/ingest` via SHA-256 content hash (idempotent verbs, idempotency keys, 201 vs 200 on replay)
   - [ADD] `GET /v1/documents` from Postgres: written the naive N+1 way first, then fixed with one JOIN/GROUP BY
   - [ADD, P] Cursor pagination on `GET /v1/documents` (cursor vs offset)
   - [ADD, opt] ETag + `If-None-Match` → 304 on `GET /v1/documents`
   - `EXPLAIN ANALYZE` on real queries; vector index is approximate (junior depth)
3. **Retrieval + generation**: top-k search, grounded prompt, citations in the response, `/v1/query` endpoint + one API test with the LLM mocked. Teach: the main RAG failure modes, pgvector vs dedicated vector DBs. Plus:
   - [ADD, P] Per-stage timing in logs (embed / search / generate)
   - Error trace: LLM timeout → `ProviderError` → HTTP response (continued in the UI in phase 5)
   - [ADD, opt] In-memory token-bucket rate limiter on `/v1/query` (vs fixed/sliding window, multi-instance problem, fair queuing)
   - [ADD, opt] LLM response cache keyed by normalized question + doc set + prompt version, invalidated on re-ingest
   - Whiteboard drill after this phase
4. **Eval**: write questions, run both strategies, grade, fill in EVAL.md. Plus:
   - [ADD, P] Async load script measuring p50/p95 of `/v1/query` → `docs/PERF.md`; walk the "debug a slow endpoint" checklist on real data
5. **React UI**: question box, answer, citation list. Teach: components, `useState`, `useEffect`, CORS (preflight; what it does *not* protect against). Plus:
   - [CHANGE] TanStack Query instead of plain fetch (server vs client state, caching, retries with backoff, stale-while-revalidate)
   - State management comparison (Context / `useReducer` / Redux / TanStack Query); hooks (`useEffect` vs `useLayoutEffect`, cleanup, `useMemo`/`useCallback` with measurement)
   - Rendering experiments with React DevTools Profiler (StrictMode, re-renders, `key`); lazy loading, skeletons, Fragments
   - XSS-safe rendering of LLM output (no `dangerouslySetInnerHTML`); LLM-timeout error shown in the UI
   - JS/TS fundamentals exercises (`let`/`const`/`var`, closures / stale closure, `this`, JS event loop vs asyncio)
6. **Cloud Run deploy**: public URL, env vars, secret. Decide Cloud SQL vs another hosted Postgres with me and note the cost. Teach: scaling to zero, cold starts, request timeouts, SIGTERM on Cloud Run. Plus:
   - [ADD, opt] Cloud Storage: PDFs go to a GCS bucket (ephemeral filesystem); signed-URL upload vs upload through the API. Backend only — still no upload UI.
7. **README**: architecture diagram (Mermaid), setup steps a stranger can follow, eval summary. Finalize `docs/INTERVIEW.md`; final whiteboard drill.

Stretch (only if everything above is done): a retrieval relevance floor, so if the best score is below a threshold the model isn't called at all.

## Do NOT build
Auth, multi-user, rerankers, hybrid/BM25 search, conversation memory, streaming responses (that's the next project), an upload UI, any eval framework beyond the hand-written set, fine-tuning, Kubernetes, LangChain/LlamaIndex (I'm writing the pipeline myself to understand it), Next.js, a message queue, GraphQL (these stay study-only, see "Interview-driven learning" C).

## Current status (update at the end of every session)
- **2026-09-29, session 1:** Phase 0 done (`/health`, `/documents` on an in-memory repo, 7 tests green).
  Env: uv 0.12 + Python 3.12 in WSL; Docker Engine not yet installed (native engine + compose plugin chosen).
  Provider: Google Gemini free tier recommended (gemini-embedding-001 at 768 dims, called via raw httpx), awaiting API key.
  Corpus: NASA-STD-8739.8B + NPR 7150.2D proposed as public corpus (awaiting confirmation); CiA 301/402 local-only; IEC 62304 excluded (see DECISIONS.md).
  **Next:** Phase 1 (Docker + Postgres/pgvector).
- **2026-09-30, session 2:** Phase 1a done: Docker Engine in WSL, Compose (pgvector/pgvector:pg16 + api),
  multi-stage Dockerfile (262 MB), schema applied at startup (documents, chunks, vector(768), HNSW),
  async pool, `/v1` prefix, `/v1/health` 200/503, graceful shutdown verified. 10 tests green.
  User has a Gemini key; `.env` not yet created from `.env.example` (key never shared with Claude). Corpus confirmed: NASA-STD-8739.8B + NPR 7150.2D public;
  CiA 301/402 (+ user's ISO/IEC copies) local-only in `data/local/`.
  **Next:** Phase 1b: exception hierarchy + one handler, structured JSON logs with request ID; then explain-back + 5-question drill.
- **2026-10-02, session 3:** Phase 1b done: `app/errors.py` (HTTP-agnostic hierarchy), `app/api/error_handlers.py`
  (one status map, one error envelope incl. 422/404/405), `app/api/middleware.py` (pure-ASGI: request ID ContextVar,
  access log, last-resort 500), `app/logging_config.py` (JSON logs, uvicorn routed through it). 20 tests green, image 274 MB.
  `.env` exists. Phase 1 drill done: 3 correct, 1 partial, 1 wrong (see TOPICS.md drill log).
  Re-drill at the start of next session: why domain errors are HTTP-agnostic + 4xx vs 5xx families.
  **Next:** Phase 2 (ingestion).
- **2026-10-02, session 3 (cont.):** Phase 2a done: `app/ingest/` (types, parser, chunkers), 58 tests green.
  Public corpus fixed: NASA-STD-8739.8B, NPR-7150.2D, FDA Premarket Software Guidance 2023, FDA Off-The-Shelf Software
  Guidance 2023 (in `data/public/`, 225 pages → 956 naive / 640 section-aware chunks). Two real bugs logged in BUGS.md.
  Still open: decide whether to commit the public PDFs to git; phase-1 re-drill (domain errors vs HTTP, 4xx vs 5xx).
  **Next:** Phase 2b: Gemini embedding provider (raw httpx, 768 dims), storage, idempotent `POST /v1/ingest`
  (parse/chunk via `asyncio.to_thread`); then 2c: `/v1/documents` from Postgres (N+1 → JOIN, cursor pagination).
- **2026-10-02, session 3 (end):** Phase 2b + 2c done: `app/llm.py` (GeminiProvider, retries, quota fail-fast),
  `app/ingest/store.py` + `service.py` (idempotent ingest, one transaction), `POST /v1/ingest`, `app/repository.py`
  (Postgres, JOIN, keyset cursor), separate test DB `specseek_test`. 89 tests green. Image 371 MB. 4 bugs in BUGS.md.
  Dev DB holds 3 of 4 public docs (901 chunks). **NPR-7150.2D is NOT ingested yet**: Gemini free tier allows 1,000
  embedding texts/day per model and it needs 695; quota resets around 00:00 UTC on 2026-10-03. Public PDFs are un-ignored
  in git (user decided to commit them). ETag/304 skipped (optional).
  2026-10-03 02:09 UTC: NPR ingest attempted again, still 502 (daily quota exhausted, provider says ~21h50m).
  User stays on the free tier. Queries also need 1 embedding each, so live `/v1/query` checks wait for quota too.
  **Next:** (1) ingest NPR: `curl -X POST localhost:8000/v1/ingest -H 'Content-Type: application/json' -d '{"path": "public/NPR-7150.2D.pdf"}'`
  (2) re-drill: domain errors vs HTTP + 4xx/5xx; phase 2 five-question drill. (3) Phase 3: retrieval + generation, `/v1/query`. User must place PDFs in `data/public/` and `data/local/` first.

## First session
1. Save this brief to `CLAUDE.md`.
2. Ask me, in one message: whether Docker (and which setup), uv, Node and gcloud are already installed in WSL; which LLM/embedding API keys I have; which standards PDFs I already have access to. Then verify with commands (`docker --version`, `uv --version`, `node -v`, `which python3`) instead of taking my word for it.
3. Then start Phase 0 with the concept briefing, and give me the first skeleton to fill in.

## Interview-driven learning

### Goal
I'm preparing for Fullstack + AI engineer interviews. Besides building SpecSeek, I have to:
(a) learn the interview topics below through the project wherever possible, and
(b) be able to describe SpecSeek in full detail **without code access**: architecture, request flow, numbers, decisions, bugs, trade-offs, and 3 levels of follow-ups.

### Teaching rules for interview topics
1. When we build something that maps to an interview topic, say so explicitly: "Interview topic: Idempotency." Give a ≤6-bullet explanation of the general concept, then show exactly how it appears in our code.
2. For each topic, teach in this order: **what problem it solves → how it works → how we did it in SpecSeek → the trade-off / when you'd pick the alternative**. Interviewers mostly probe the last one.
3. **Explain-back before show:** for anything I built, ask me to explain it first, then correct me. Don't pre-empt with the answer.
4. Where my C++/real-time background maps onto a topic (event loop ≈ epoll, SSE ≈ non-blocking IPC, graceful shutdown ≈ safe state transitions, latency budgets ≈ FDA test criteria), point it out. These are my strongest interview answers.
5. Keep `docs/TOPICS.md`: one row per topic below, with status `built` / `studied` / `drilled` (drilled = I answered it correctly out loud in a mock) and a one-line pointer (file/function or doc section).

### Topic map

#### A. Built in SpecSeek
Backend / API
- RESTful resource design, correct verbs and status codes (201/202/404/409/422), PUT vs PATCH (explain even though we use neither yet) → our 4 endpoints
- API versioning [ADD]: mount everything under `/v1`; explain URL vs header vs media-type versioning, and when a version is retired
- Idempotency [ADD]: `POST /ingest` is idempotent via a SHA-256 content hash of the PDF. Re-ingesting the same file returns the existing document, not duplicates. Explain naturally idempotent verbs, idempotency keys, and why "everything is POST" loses caching + idempotency
- Pagination [ADD]: `GET /v1/documents` uses **cursor** pagination; explain cursor vs offset and why offset breaks under inserts
- ETags / HTTP caching [ADD]: ETag + `If-None-Match` → 304 on `GET /v1/documents`
- Validation layers: Pydantic at the edge; custom exception hierarchy [ADD] (`SpecSeekError` → `NotFound`, `IngestError`, `ProviderError`, …) mapped to HTTP responses in one exception handler. Explain which layer (API / service / data) validates and handles what
- Error handling, backend vs frontend: the same failure (LLM timeout) traced from provider → service → API → React UI message
- Parameterized queries, SQL injection: show why our psycopg queries are safe and what the unsafe version looks like
- CORS: we need it for Vite → API; explain the preflight and what CORS does *not* protect against (XSS, CSRF)
- Rate limiting [ADD, small]: an in-memory token bucket on `/v1/query` (LLM calls cost money). Explain token bucket vs fixed/sliding window, why in-memory breaks with multiple Cloud Run instances, and fair queuing for "one user sends 1000 req/min without starving others"
- LLM response cache [ADD, optional]: cache `/v1/query` answers keyed by normalized question + doc set + prompt version; explain invalidation on re-ingest
- Observability [ADD]: structured JSON logs with a request ID per request, and timing per stage (embed / search / generate)
- Performance [ADD]: a small async load script measuring p50/p95 latency of `/v1/query`, recorded in `docs/PERF.md`. Use it to walk the "debug a slow endpoint" checklist on our real data (network, DB, index, third-party LLM, caching)
- Graceful shutdown [ADD]: FastAPI lifespan opens and closes the DB pool; explain SIGTERM on Cloud Run and draining in-flight requests
- Event loop / asyncio: blocking vs non-blocking, `run_in_executor` for PDF parsing and chunking (CPU-bound)
- TDD: the chunkers are written test-first (the tests exist before the implementation)

Database
- Relational vs non-relational: why Postgres here, ACID, what Firestore (next project) trades away
- Indexes: B-tree on `document_id` / content hash, the vector index on embeddings (junior depth only: what it is and why it's approximate), `EXPLAIN ANALYZE` on our real queries
- N+1: `GET /documents` with chunk counts, written the naive way first so I can see it, then fixed with one JOIN/GROUP BY. This doubles as the "write a 2-table join" SQL question
- ID design: explain our choice of UUID (v4 vs v7) and how you'd guarantee uniqueness across services and DBs
- ORM vs raw SQL: we use raw parameterized SQL; explain ORM pros and cons and what I'd pick for a larger codebase

DevOps / Cloud
- Containers vs VMs, Dockerfile layers, Docker vs Docker Compose
- Cloud Run: containers, env vars, secrets, scaling to zero, cold starts, request timeouts
- Cloud Storage [ADD, phase 6]: Cloud Run's filesystem is ephemeral, so uploaded PDFs go to a GCS bucket. Explain signed-URL uploads vs uploading through the API
- Kubernetes and IaC: study only. When K8s is worth it vs Cloud Run, and what Terraform would manage for SpecSeek

AI
- RAG end to end: embeddings, cosine similarity, chunking trade-offs, top-k, grounding, refusal, failure modes, eval
- Vector database choice: pgvector vs dedicated vector DBs

Frontend (phase 5)
- [CHANGE] Use **TanStack Query** for data fetching instead of plain fetch. Teach: server state vs client state, caching, retries with backoff, stale-while-revalidate
- State management: `useState` for UI state; explain Context vs `useReducer` vs Redux/RTK vs TanStack Query and when each fits. Show where Redux would be overkill here
- Hooks: `useEffect` vs `useLayoutEffect`, dependency arrays, cleanup on unmount (cancelling an in-flight query), `useMemo` / `useCallback` with a real measurement, not a guess
- Rendering: run small experiments in our UI with React DevTools Profiler and `console.log` in components (StrictMode double render, re-renders on prop change, `key` and reconciliation). Explain render → reconcile → commit → paint
- Lazy loading and skeletons for the answer panel; Fragments
- Sanitization / XSS: the answer text comes from an LLM, so render it safely. Explain why we never inject it with `dangerouslySetInnerHTML`
- JS/TS fundamentals via small exercises in our frontend code: `let` / `const` / `var`, closures (the stale closure in `useEffect`), `this`, the JS event loop (compare with asyncio)

#### B. Covered later in TriageBot (note only, don't build now)
SSE and server interfaces (REST / gRPC / GraphQL / WebSocket / SSE comparison), event-driven architecture, MCP, agent patterns, Firestore/Firebase, message queues (enqueue agent runs → worker), dropped-connection resume. When a SpecSeek topic connects to these, add a note under "Carry over to TriageBot" in `docs/TOPICS.md`.

#### C. Study only (never build; 20–30 min sessions tied to SpecSeek)
For each topic, explain it and then answer: "if SpecSeek needed this, what would change and where?"
- SSR vs CSR vs SSG vs hybrid, how SSR serializes, hydration mismatches, React vs Next.js
- Design systems: tokens, Tailwind config overrides, atoms / molecules / organisms, CVA, micro-frontends / module federation
- AuthN vs AuthZ: JWT, sessions, OAuth2/OIDC, SSO; RBAC / ReBAC / ABAC; Keycloak, OpenFGA. Scenario: "add per-team document access to SpecSeek"
- CSRF and other web attacks beyond the ones we built for
- Message queues: Pub/Sub, SQS, RabbitMQ, Kafka (throughput, ack deadlines, dead-letter / redrive). Scenario: "make ingestion async for 500-page PDFs"
- GraphQL vs REST, gRPC
- DDD, SOLID, and the design patterns actually present in our code (the provider interface = strategy / dependency inversion)
- Agent protocol landscape: ADK, A2A, AG-UI, A2UI. Know what each is for at one-paragraph depth, and verify current details with a web search, since these change fast
- Deployment strategies: blue/green, canary, feature flags, and how you'd safely roll out a prompt or model change

### Being able to explain it without code
Maintain `docs/INTERVIEW.md` and update it at the end of every phase. It's my offline study guide and must be accurate to the actual code. It contains:
1. **90-second walkthrough** (spoken style, no jargon dump), revised as the project grows
2. **Architecture diagram** (Mermaid) plus a version I can draw on a whiteboard in 5 boxes
3. **Request traces:** `/v1/query` and `/v1/ingest` step by step, naming the module/function at each step and what can fail there
4. **Numbers to know cold:** chunk size/overlap, embedding model + dimension, top-k, corpus size (docs, pages, chunks), eval scores for both strategies, p50/p95 latency, cost per query (rough), Docker image size
5. **Decisions:** each with the rejected alternative and a one-line why (pulled from DECISIONS.md)
6. **Bugs:** the 3 best stories from BUGS.md in STAR form (situation, what I saw, root cause, fix)
7. **Known limitations and what I'd do next.** Honest, and volunteered before an interviewer finds them
8. **Follow-up ladders:** for each major component, the likely question, the follow-up, and the follow-up to that, with my answers

### Drills
- **End of each phase:** 5 questions from the topic map for things we built in that phase, asked one at a time. I answer from memory; you grade (correct / partial / wrong), fix gaps, and update TOPICS.md.
- **Mock interview mode.** When I type "mock interview", act as a senior interviewer on a Fullstack AI team. Rules:
  - Ask one question at a time and drill down at least 3 levels on each answer.
  - Mix project questions, category A and C topics, and one bridge question ("why move from robotics to AI?").
  - Don't help me mid-answer.
  - At the end, give a scorecard with weak spots and add them to the next session's drills.
- **Whiteboard drill** (after phase 3 and again at the end): I describe the architecture and the query path from memory in chat; you compare it against INTERVIEW.md and list what I missed or got wrong.

### Scope guard
Items marked [ADD] are small (≤1–2 h each). Order of priority if time runs short: idempotency, cursor pagination, exception hierarchy, structured logging, p50/p95 measurement come first. Rate limiter, ETag, LLM cache, GCS upload are optional. Never add auth, Kubernetes, Next.js, a message queue or GraphQL to SpecSeek. Those stay in category C.
