# Decisions

Format: **Decision** / Alternative rejected / Why. Only choices actually made go here.

## 2026-09-29: Repo lives in the WSL filesystem (`~/specseek`)
- **Rejected:** keeping it on the Windows drive (`/mnt/f/...`).
- **Why:** crossing the WSL/Windows boundary makes file I/O much slower (9P), inotify events are
  unreliable there (breaks `uvicorn --reload` and Vite HMR), and the old path had spaces.

## 2026-09-29: `uv` for Python env and dependencies, with a lockfile (`uv.lock`) committed
- **Rejected:** pip + venv + requirements.txt.
- **Why:** it's fixed in the stack; a lockfile gives reproducible installs in Docker and CI.

## 2026-09-29: Storage behind a `DocumentRepository` Protocol, in-memory first
- **Rejected:** writing routes directly against Postgres from day one.
- **Why:** routes depend on an interface, so tests inject a fake through `dependency_overrides`
  and Phase 1 swaps in Postgres without touching route code.

## 2026-09-29: Ruff rule set includes `ASYNC`
- **Why:** it statically flags blocking calls (e.g. `time.sleep`, sync HTTP) inside `async def`,
  the #1 asyncio bug.

## 2026-09-29: Corpus licensing policy
- **Public corpus (commit, demo, CV):** only documents with no copyright restriction, e.g. US
  federal government works (candidates: NASA-STD-8739.8B, NPR 7150.2D; final pick pending).
- **CiA 301 / CiA 402 (free download from CiA):** local-only. PDFs stay gitignored and are never
  served by the public deployment, because `/query` returns verbatim snippets (= redistribution).
  Must re-read CiA's download terms before use.
- **IEC 62304:** excluded unless a copy from an official IEC/national-body source is confirmed;
  IEC does not publish it for free.
- **Rejected:** committing whatever PDFs are at hand. **Why:** copyright; the repo is public.

## 2026-09-30: Frontend data fetching with TanStack Query (phase 5)
- **Rejected:** plain `fetch` + `useEffect` (the original plan).
- **Why:** interview coverage of server vs client state, caching, retries, stale-while-revalidate;
  it also removes hand-written loading/error/cancellation boilerplate.

## 2026-09-30: All routes under `/v1` (retrofit at the start of phase 1)
- **Rejected:** unversioned paths. **Why:** a breaking change can ship as `/v2` without breaking
  existing clients; URL versioning is the most visible and cache-friendly option.

## 2026-09-30: Embedding provider = Google Gemini, 768 dimensions
- **Model:** `gemini-embedding-001` (confirm the current name when wiring it in phase 2), requested at
  768 dims via `output_dimensionality`; vectors L2-normalized by us (truncated outputs aren't).
- **Rejected:** the default 3072 dims. **Why:** pgvector's HNSW index supports at most 2000 dims on
  `vector`; 768 also means 4× less storage and faster search.
- **Rejected:** OpenAI (no free tier), Anthropic (no embeddings API), local Ollama (slow on CPU,
  can't run cheaply on Cloud Run).

## 2026-09-30: Licensed docs live in `data/local/` (gitignored), public ones in `data/public/`
- CiA 301/402 and any ISO/IEC copies are ingested into the **local** DB only. No per-row "public"
  flag: the cloud DB simply never ingests `data/local/`.
- Caveat noted: embedding licensed text sends it to Google; free-tier inputs may be used by Google.

## 2026-09-30: Schema applied by the app at startup (`app/schema.sql`, all `IF NOT EXISTS`)
- **Rejected:** Postgres image's `/docker-entrypoint-initdb.d/` — runs only on an empty volume and
  doesn't exist on managed Postgres (Cloud SQL). **Rejected:** Alembic — not in the stack; one
  evolving schema doesn't need versioned migrations yet.
- A transaction-scoped advisory lock stops two starting instances from racing on the DDL.
- Limitation: `IF NOT EXISTS` can't *alter* a table. The first column change needs a real migration.

## 2026-09-30: UUID v4 primary keys (`gen_random_uuid()`)
- **Rejected:** `bigserial` — guessable, and IDs from two DBs collide. **Rejected (for now):** UUID v7
  (time-ordered, better B-tree locality) — Postgres 16 has no built-in generator and Python 3.12's
  `uuid` module has none. At our row counts, v4's random inserts don't matter.

## 2026-09-30: No separate index on `chunks.document_id`
- `UNIQUE (document_id, strategy, chunk_index)` already creates a B-tree whose leftmost column is
  `document_id`, which serves `WHERE document_id = ?`. A second index would only slow inserts.

## 2026-09-30: `/v1/health` returns 503 when the DB is unreachable
- **Rejected:** always 200 with a status field. **Why:** monitors and load balancers read status
  codes, not bodies. Caveat for phase 6: don't use this as a Cloud Run *liveness* probe, or a DB
  outage would restart healthy containers in a loop.

## 2026-09-30: Config from `os.environ` in a frozen dataclass
- **Rejected:** `pydantic-settings` — not in the stack; two variables don't justify a dependency.

## 2026-09-30: Dockerfile: multi-stage, uv, non-root, `exec` in CMD
- Builder stage installs deps from `uv.lock`; runtime stage copies only `.venv` + `app/`.
- `CMD ["sh", "-c", "exec uvicorn ..."]` so uvicorn is PID 1 and gets SIGTERM (needed for `$PORT`
  expansion on Cloud Run). **Rejected:** shell-form CMD — `sh` would be PID 1 and swallow SIGTERM.

## 2026-10-02: Domain exceptions are HTTP-agnostic; status codes mapped in one handler
- `app/errors.py` classes carry only a `code` and a message. `app/api/error_handlers.py` owns the
  table `NotFound→404, IngestError→422, ProviderError→502, SpecSeekError→500`.
- **Rejected:** a `status_code` attribute on each exception, or raising `HTTPException` from
  service code. **Why:** the same service code must be callable from non-HTTP callers
  (`eval/run_eval.py`, tests); only the API layer should know HTTP.

## 2026-10-02: One error envelope for every non-2xx response
- `{"error": {"code", "message", "request_id", "details?"}}` for domain errors, validation errors
  (422), framework errors (404/405) and unhandled exceptions (500).
- **Rejected:** FastAPI's defaults (`{"detail": ...}` with three different shapes).
  **Why:** the frontend gets one error-parsing path, and every error carries the request ID.
- Unhandled exceptions return a generic message; the stack trace goes to the log only.

## 2026-10-02: Structured logs with stdlib `logging` + a small JSON formatter
- **Rejected:** `structlog` / `python-json-logger` — not in the stack; ~40 lines of formatter do it.
- Field name `severity` (not `level`) because Cloud Logging parses it from JSON on stdout.
- uvicorn's access log is disabled; our middleware writes one line per request with
  `request_id`, `method`, `path`, `status`, `duration_ms`.

## 2026-10-02: Request ID in a ContextVar, set by a pure-ASGI middleware
- **Rejected:** Starlette `BaseHTTPMiddleware` — it runs the route in a separate task, so context
  set in the middleware isn't reliably visible downstream. **Rejected:** passing `request_id` as a
  parameter through every function.
- An incoming `X-Request-ID` is reused only if it matches `^[A-Za-z0-9_-]{1,64}$` (it is written to
  our logs, so unvalidated input would allow log injection); otherwise we generate a UUID.

## 2026-10-02: Public corpus = 4 US-government documents (225 pages)
- NASA-STD-8739.8B (70 p), NPR 7150.2D (89 p), FDA "Content of Premarket Submissions for Device
  Software Functions" 2023 (46 p, downloaded from fda.gov/media/153781), FDA "Off-The-Shelf
  Software Use in Medical Devices" 2023 (20 p). US federal works: no copyright restriction.
- FDA guidance added because it is my professional domain (eval questions from real experience)
  and it uses a different numbering scheme (I. / A. / 1.), which stresses the chunker.
- `data/local/` (CiA 301, CiA DSP 402, vendor manuals, IEC 62304 copies): local experiments only.
  The IEC 62304 PDF carries another organisation's licence watermark; not used for anything public.

## 2026-10-02: Parser output is "lines with a bold flag", cleaned in three steps
- Evidence (surveyed the corpus before designing): a naive "number + text" heading pattern matched
  475 lines in NASA-STD-8739.8B, almost all list items inside tables; NASA-STD stores a clause
  number and its text as separate lines on one row; FDA headings differ from list items only by
  being bold.
- So `parse_pdf` (1) keeps a `bold` flag per line, (2) drops lines in the top/bottom 10% of the page
  that repeat on >50% of pages (digits normalised, so "7 of 70" matches "8 of 70"), (3) joins a
  marker-only line ("4.4.2.9", "I.", a bullet) with the text on the same row (within 3 pt).
- **Rejected:** `page.get_text()` plain text (loses bold and row position). **Rejected:**
  `pymupdf4llm` / `unstructured` (new dependencies, and I couldn't explain their heuristics).
  **Rejected:** PDF bookmarks as the heading source (two of four documents have none).

## 2026-10-02: Heading rules for `section_aware`
- **Decimal clause numbers** (`3.1.2`, `C.1`, `P.3`) start a clause on any line, bold or not,
  because in standards the numbered *paragraph* is the citable unit. Guards: ≥2 components, each
  ≤2 digits (rejects "7150.2"), followed by an uppercase letter or digit (rejects wrapped
  references like "3.7.1 of this document").
- **Outline markers** (`IV.`, `A.`, `1.`, `(1)`, `Appendix A`, `Chapter 3`) count only on bold
  lines, and build hierarchical IDs (`IV.B.1`). `I.`/`V.`/`X.` are letters only right after the
  previous letter of the alphabet.
- Heading-only sections produce no chunk; their title lives on as `parent_heading` of the
  sub-clauses. Contents-page entries are merged into the preceding text.
- **Rejected:** merging small neighbouring clauses up to the size limit: it would blur clause IDs,
  and exact citations are the point of this strategy.

## 2026-10-02: Chunk sizes: naive 512 chars; section-aware ≤3200 chars with 400 overlap
- "800 tokens / 100 overlap" is implemented as characters with 1 token ≈ 4 chars.
  **Rejected:** a real tokenizer (`tiktoken` is OpenAI's vocabulary, not Gemini's; Gemini's
  `countTokens` is a network call per chunk). The limit only needs to stay safely under the
  embedding model's input limit, so an approximation is enough.
- Oversized clauses are split recursively: by line, then sentence, then word, then a hard cut;
  each later piece is prefixed with the tail (≤400 chars, word-aligned) of the previous one.
- Naive has no overlap: it is the deliberately structure-blind baseline.

## 2026-10-02: Known chunking limitations (kept for the eval to measure, not fixed blind)
- FDA Premarket guidance: the subsection letters `A.`–`J.` are not in the PDF's text layer, so
  everything under section VI is cited as `VI` (or `VI.1`…), not `VI.C`.
- Table cells are read in the PDF's own order; a row is not reconstructed as a row.
- Contents pages remain as unlabelled (or `Chapter N`-labelled) chunks: retrieval noise.
- A clause ID is not unique in a document: NPR 7150.2D repeats each requirement in its Appendix C
  matrix, and NASA-STD Table 1 uses NPR section numbers that collide with its own (`3.1`, `3.2`).

## 2026-10-02: Idempotent ingest keyed on the SHA-256 of the file's bytes
- Flow: hash the file → look the hash up (cheap early exit, skips parsing and paid embedding) →
  parse, chunk, embed → one transaction: `INSERT ... ON CONFLICT (content_hash) DO NOTHING
  RETURNING id`, then the chunks. New document → **201**; known content → **200** with the
  existing document and `created: false`.
- The early lookup is only an optimisation. Correctness comes from the UNIQUE constraint: two
  concurrent ingests of one file can both pass the lookup, but only one INSERT returns an ID.
- **Rejected:** check-then-insert in application code (race condition). **Rejected:** a
  client-supplied `Idempotency-Key` header: it needs key storage and client cooperation, and here
  the content itself is a natural key. Limitation: a re-saved PDF with identical text has
  different bytes and counts as a new document.

## 2026-10-02: `POST /v1/ingest` takes a path inside the data directory, not an upload
- **Rejected:** multipart file upload: needs the `python-multipart` dependency (not in the stack),
  and an upload UI is on the do-not-build list.
- Because the path comes from the client, `resolve_data_path` resolves it and rejects anything
  outside `DATA_DIR` (path traversal), anything that isn't `.pdf`, and missing files (404).

## 2026-10-02: Ingest is synchronous; no DB connection is held while embedding
- Measured on the Gemini free tier: 143 chunks took 94 s, almost all of it waiting out two HTTP 429
  rate-limit responses. A request that long is acceptable for a one-off admin action, not for users.
- The scalable design is `202 Accepted` + a job on a queue + a worker. A message queue is on the
  do-not-build list, so this is recorded here and under "Future work".
- The pool connection is released before the embedding call and re-acquired for the write, so a
  slow provider can't exhaust the 10-connection pool.

## 2026-10-02: Embedding details
- Provider interface is `embed(texts, kind)` with `kind` = `document` or `query`: Gemini embeds
  passages and questions differently (`RETRIEVAL_DOCUMENT` / `RETRIEVAL_QUERY`).
- Vectors are L2-normalised by us: measured norm of the 768-dim output was 0.58, not 1. Cosine
  distance doesn't strictly need it, but unit vectors keep scores comparable and make
  dot product = cosine if the index operator ever changes.
- Retries: only for 429/5xx and transport errors, up to 6 attempts, waiting what the provider asks
  (`Retry-After` header or `retryDelay` in the error body) or 2/4/8/16/32 s. 4xx is not retried.
- The raw chunk text is embedded, with no title/heading prefix, for both strategies, so the eval
  compares chunking alone. **Rejected for now:** prefixing each chunk with its document title and
  heading ("contextual headers"); it is a candidate improvement to measure after the first eval.
- API key is sent in the `x-goog-api-key` header, never in the URL, and is excluded from
  `Settings`' repr.

## 2026-10-02: `GET /v1/documents`: one JOIN, cursor (keyset) pagination
- Chunk counts come from a single `LEFT JOIN ... GROUP BY` query. **Rejected:** one count query per
  document (N+1): a test runs both and measures 11 queries vs 1 for 10 documents.
- Pagination is keyset: `ORDER BY created_at DESC, id DESC`, next page =
  `WHERE (created_at, id) < (last seen)`. The cursor is that pair, base64-encoded, so it is opaque.
  The page size is 1–100 (default 20); the query fetches `limit + 1` rows to know if more exist.
- **Rejected:** `LIMIT/OFFSET`. A test shows the failure: with a new document inserted between
  page 1 and page 2, OFFSET returns a row twice, the cursor does not. OFFSET also gets slower with
  depth (the database reads and discards the skipped rows). Trade-off: a cursor can't jump to
  "page 7" and gives no total count.
- A cursor we did not issue → 422 `invalid_cursor` (it is client input, so it is validated).
- ETag / 304 for this endpoint (optional in the plan): not built.

## 2026-10-02: What `EXPLAIN ANALYZE` showed on the real data (3 documents, 901 chunks)
- Documents listing: sequential scans + hash join + hash aggregate, 0.8 ms. No index is used and
  that is correct: with 3 documents and 901 chunks, reading everything is cheapest.
- Lookup by `content_hash`: sequential scan over 3 rows, 0.05 ms, despite the unique index.
  Same reason. The index exists for correctness (uniqueness) first, speed later.
- Top-5 nearest chunks, unfiltered: **index scan on the HNSW index, 0.5 ms**; the same query with
  index scans disabled (exact search): 3.4 ms.
- Top-5 filtered by `strategy`: the planner chose a sequential scan + top-N sort (exact search over
  the 299 matching rows), 1.6 ms, and did not use the HNSW index. Consequence: at this size
  filtered retrieval is *exact*, not approximate. To revisit if the corpus grows (options: a
  partial HNSW index per strategy, or pgvector's iterative scan).

## 2026-10-02: Tests use their own database, `specseek_test`
- **Rejected:** sharing the dev database (the phase 1 setup): ingest tests write and truncate
  tables, which would wipe the real corpus. `tests/conftest.py` sets `DATABASE_URL` before the app
  is imported, creates the database on first use and truncates it before each integration test.

## Future work (explicitly out of scope)
- Asynchronous ingestion: `202 Accepted`, a queue and a worker (see the synchronous-ingest decision).
- Compare `gemini-embedding-2` (available on the same key) against `gemini-embedding-001`.
  Changing the embedding model means re-embedding every chunk: vectors from two models are not comparable.
