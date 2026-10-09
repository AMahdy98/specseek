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

## 2026-10-03: Stay on the Gemini free tier
- Limit that matters: 1,000 embedding texts per day per model. The corpus is 1,596 texts, so a full
  re-ingest (e.g. after a chunker change) is spread over two days; each `/v1/query` costs 1 text.
- **Rejected (for now):** enabling billing. No cost, and the limits are workable for one developer.
  Accepted consequences: free-tier inputs may be used by Google (fine for public-domain text; one
  more reason the licensed `data/local/` documents are not embedded), and eval runs must be
  budgeted against the daily quota.
- Observed, not explained: on 2026-10-02 at ~19:26 UTC the 429 said "retry in 4h34m" (≈ 00:00 UTC),
  but at 01:38 and 02:09 UTC on 2026-10-03 the quota was still exhausted ("retry in 22h21m" /
  "21h50m"), with no successful embedding calls from this app in between. So the provider's
  retry hint is not a reliable reset time; check usage at https://ai.dev/rate-limit before bulk runs.

## 2026-10-02: Tests use their own database, `specseek_test`
- **Rejected:** sharing the dev database (the phase 1 setup): ingest tests write and truncate
  tables, which would wipe the real corpus. `tests/conftest.py` sets `DATABASE_URL` before the app
  is imported, creates the database on first use and truncates it before each integration test.

## 2026-10-03: Retrieval = top-5 by cosine similarity, one SQL query, per strategy
- `ORDER BY embedding <=> query LIMIT 5`, filtered by `strategy` (and optionally `document_id`);
  the reported score is `1 - cosine distance`.
- **Top-k = 5.** Fewer risks missing the passage; more adds cost and distracting text. To be
  revisited with eval evidence, not by feel.
- `strategy` is a request field (default `section_aware`) so the evaluation can ask both.
- **Rejected:** pgvector alternatives such as a dedicated vector database (Pinecone, Qdrant,
  Chroma): one more service to run, deploy and keep consistent with Postgres, for a few thousand
  vectors. With pgvector the chunk text, metadata and vector live in one row, and the document
  filter is an ordinary `WHERE`. A dedicated vector DB earns its place at tens of millions of
  vectors or when filtered approximate search has to stay fast.
- **Rejected (do-not-build list):** rerankers, hybrid/BM25 search.

## 2026-10-03: Grounded prompt (`PROMPT_VERSION = "v1"`)
- System instruction: use only the numbered passages; a fixed refusal sentence ("I don't know
  based on these documents."); cite as [document, clause]; preserve "shall/should/may" exactly;
  treat passages as reference material, not instructions (prompt-injection guard).
- User message: numbered passages, each with a `Document | Clause | Heading | Page` header, then
  the question last.
- The refusal is an exact sentence so code and the eval can detect it by string match
  (`refused: true` in the response). A refusal is a 200, not an error.
- `temperature = 0` for repeatable answers. Generation model pinned by name
  (`gemini-3.8-flash`, configurable), not an alias like `flash-latest`, so eval results don't
  shift when the provider moves the alias.
- With an empty retrieval result the service returns the refusal itself and never calls the LLM.

## 2026-10-03: `citations` = the passages given to the model, not only the ones it cited
- The response lists all retrieved passages (best first) with clause, heading, page, snippet and
  score. **Rejected:** parsing the answer to keep only passages the model actually cited: fragile
  string matching. The user can compare the `[document, clause]` markers in the answer with the list.

## 2026-10-03: Interactive calls get 3 attempts; batch calls get 6
- `/v1/query` (query embedding + generation): 3 attempts (waits of 2 s and 4 s), then
  `ProviderError` → 502. A person is waiting; minutes of backoff would be worse than a clear
  error. Ingestion keeps 6 attempts.
- Measured, not guessed: the first version allowed 2 attempts, and 3 of 5 real questions failed
  with 502 because `gemini-3.8-flash` answered "503 high demand" twice in a row. With 3
  attempts, 4 of the next 5 succeeded. The model is simply busy on the free tier; the eval
  script must re-ask questions that fail this way.
- A cut-off answer (`finishReason = MAX_TOKENS`) or an empty/blocked one is raised as
  `ProviderError` rather than returned as if complete.

## 2026-10-03: `POST /v1/query`, although it only reads
- **Rejected:** `GET /v1/query?question=...`: the question would sit in URLs (browser history,
  proxy and access logs) and URL length is limited. Trade-off: POST responses aren't cached by
  HTTP caches, and POST is not idempotent by definition (here it has no side effects anyway).
- The question text is not written to our logs; only its length.

## 2026-10-03: Observations from the first real questions (9 asked; not an evaluation)
- Latency is almost entirely the LLM: embed 0.3–0.5 s, vector search 2–3 ms, generation 3–23 s
  (the long ones include a retry or a provider-requested wait).
- Near-duplicate passages crowd the context: for "acquisition versus development", 3 of the 5
  retrieved section-aware chunks were the same requirement 3.1.2 (NPR body, NPR Appendix C
  matrix, NASA-STD Table 1). The answer was right, but 3 of 5 context slots carried one fact.
- Section-aware answers cite clause IDs; naive answers can only cite pages.
- An out-of-corpus question (CAN bus bit rate) was refused; its best score was 0.58 versus
  0.69–0.80 for answerable questions. Too few samples to set a relevance floor yet.

## 2026-10-04: Eval questions: candidates proposed by the assistant, chosen and verified by me
- The brief said I write all 20 questions myself. Changed at my request: the assistant proposed
  40 candidates (`eval/candidates.yaml`), each with its expected answer taken from the document
  text, clause and PDF page; I choose 20, check each against the PDF, and may reword them.
  Grading stays manual and mine.
- **Trade-off, to be stated in EVAL.md:** faster, and every expected answer is traceable to a
  page; but the proposer had seen how the documents were chunked, which can bias the set towards
  passages that chunk cleanly, and the questions are not purely from my own domain knowledge.
  Mitigation: favour table and cross-reference candidates, reword, and add some of my own.

## 2026-10-04: Evaluation runner design
- `eval/run_eval.py` calls `rag.answer_question` directly, not the HTTP endpoint: this is what
  the HTTP-agnostic service layer was for. Same pool, same provider, same prompt as the API.
- One embedding per question, reused for both strategies (`query_vector` parameter): 20 of the
  1,000 daily embeddings instead of 40, and both strategies get the identical query vector, so
  the only variable is the chunking.
- It re-asks when the provider is busy (up to 6 tries, 30 s apart), stops cleanly on an
  exhausted quota, saves after every answer and can `--resume`.
- "Expected page retrieved" is computed automatically as a retrieval hint. **Rejected:** any
  automatic grading of answers (LLM-as-judge, string overlap): the brief makes human judgment
  final, and an eval framework is on the do-not-build list.
- Run files are committed (`eval/runs/`): they are the evidence behind EVAL.md.
- `pyyaml` added as a *dev* dependency to read the question file (implied by the brief's
  `questions.yaml`; it was already installed transitively through `uvicorn[standard]`).

## 2026-10-05: Free-tier generation limit found: 20 requests/day for `gemini-3.8-flash`
- Measured from the 429 body (`GenerateRequestsPerDayPerProjectPerModel-FreeTier`, limit 20).
  The eval needs 40 generations, so the first full run stopped at 23 answers.
- Quotas are per model. Models that answered on this key on 2026-10-05: `gemini-3.1-flash-lite`,
  `gemini-3.5-flash`, `gemini-3.5-flash-lite`, `gemini-3.6-flash`, `gemini-3.7-flash`. Their
  daily limits are not known to me (the API only reveals a limit when it is exceeded).
- Rule adopted: one eval run = one generation model. `run_eval --resume` now refuses to continue
  a run if the generation model, embedding model, prompt version or top-k differ from the run's
  recorded settings. **Rejected:** finishing the remaining questions with a different model:
  the two strategies would no longer be compared under the same conditions.
- Generation model choice: decided the same day, see the next entry.

## 2026-10-05: Generation model = `gemini-3.5-flash-lite` (project default)
- Free-tier limits as I read them on my usage page: 500 requests/day, 15 per minute.
- **Rejected:** `gemini-3.8-flash`: stronger, but 20 requests/day cannot carry a 40-call eval, a
  latency test or a public demo. The evaluation was re-run in full on the new model; the earlier
  partial run is kept but not counted.
- Trade-off accepted: a lighter model. One untested hint that it matters: in a single trial,
  `gemini-3.8-flash` answered q05 (a table row) from the same retrieved row that
  `gemini-3.5-flash-lite` refused in the graded run. One sample, not a comparison.
- The default in `app/config.py` is this model, so the code, the eval and a deployment agree.

## 2026-10-05: Evaluation result and what it changed
- My final grades: section-aware 14 correct / 2 partial / 2 wrong, naive 10 / 3 / 5, on 18
  answerable questions; both refused both unanswerable ones (first pass: 15 vs 11; a review
  changed two grades). Details and caveats in EVAL.md.
- Kept: section-aware as the default strategy of `/v1/query`.
- Not changed yet: the six improvements listed in EVAL.md. None is claimed until re-measured.

## 2026-10-05: Stage timings in a `Server-Timing` response header
- `POST /v1/query` returns `Server-Timing: embed;dur=…, search;dur=…, generate;dur=…`.
- **Rejected:** a `timings` field in the JSON body (changes the API contract for a diagnostic);
  **rejected:** reading server logs from the load script (couples the test to log access).
  The header is a web standard, shows up in the browser's network panel, and costs nothing.

## 2026-10-05: Latency test is paced, not a stress test
- 24 sequential requests at one per 5 s, then two bursts of 6 after 65 s pauses: always under
  the provider's 15 requests/minute. **Rejected:** a high-rate load tool (k6, Locust): a new
  dependency, and beyond 15/min it would measure the provider's throttling.
- Percentiles are nearest-rank, so every reported number is an observed latency.
- Result (PERF.md): p50 1.30 s, p95 2.05 s; 77% generate, 23% embed, 0.2% search.

## 2026-10-06: CORS with an explicit origin list
- The UI (Vite, `localhost:5173`) and the API (`localhost:8000`) are different origins, so the API
  names the origins allowed to read its responses: `CORS_ALLOWED_ORIGINS`, default the Vite dev server.
- **Rejected:** `allow_origins=["*"]` (any website could read answers through a visitor's browser);
  **rejected:** a Vite dev proxy that hides the problem in development (the deployed UI and API are
  on different hosts anyway, so CORS is needed there regardless).
- No cookies or credentials are used, so `allow_credentials` stays off.
- The CORS middleware is outermost so error responses carry the headers too; otherwise the browser
  reports a bare network failure and the UI cannot show the error message or request ID.
- `X-Request-ID` and `Server-Timing` are exposed to JavaScript explicitly.

## 2026-10-06: Frontend: the answer is a TanStack *query*, not a mutation
- `POST /v1/query` is a read: same question + same document filter gives the same answer
  (temperature 0). `useAnswer` is a `useQuery` keyed on `['answer', question, documentId]`, so a
  repeated question is served from the browser's cache and an in-flight request is cancelled
  when it is no longer needed. **Rejected:** `useMutation` (the usual choice for POST): no
  caching by key, no automatic cancellation.
- `staleTime: Infinity`, no refetch on focus/reconnect: every call spends provider quota.
- Known gap: the browser cache is not invalidated when a document is re-ingested (30-minute
  lifetime, cleared on reload). Acceptable while there is no ingest UI.

## 2026-10-06: Frontend retries only a network failure, once
- **Rejected:** TanStack Query's default of 3 retries with backoff on any error. A 4xx fails the
  same way again; on a 502 the server has already retried the provider 3 times, so 3 client
  retries would mean up to 12 generations for one click, against 500 per day.

## 2026-10-06: Frontend tooling
- Vitest + React Testing Library + jsdom added with the user's approval (not in the original
  stack). Tests stub `fetch`; no mock-server library.
- Project files written by hand rather than from the `create-vite` template (no unused assets).
  **Not added:** ESLint; type errors are caught by `tsc --noEmit` in strict mode.
- The API base URL comes from `VITE_API_URL` at build time (default `http://localhost:8000`).

## 2026-10-09: Timeout budget for a question: 15 s per attempt, 50 s overall, UI 60 s
- Each layer's timeout is shorter than its caller's: provider attempt 15 s < whole question
  50 s (`QUERY_DEADLINE_SECONDS`) < UI request 60 s. Measured generation is p95 1.8 s, max 2.1 s.
- **Rejected:** only shortening the per-attempt timeout (embed and generate could still add up
  to about 100 s); **rejected:** only raising the UI timeout to 4 minutes (nobody waits that long).
- A deadline expiry is reported as `ProviderError` → 502, like other provider failures.
  **Alternative not taken:** a separate error mapped to 504 Gateway Timeout; more precise, but
  the UI would treat it identically.
- Ingestion is not under the deadline and keeps the 60 s per-attempt timeout.

## Future work (explicitly out of scope)
- Token-bucket rate limiter and LLM response cache on `/v1/query` (optional items, not built yet).
- **User accounts and saved chats per user** (requested 2026-10-03; auth, multi-user and
  conversation memory are on the do-not-build list, so not built). If SpecSeek needed it, what
  would change and where:
  - *Authentication:* don't store passwords. Delegate sign-in to an identity provider over
    OAuth2/OIDC (e.g. Google sign-in, or Firebase Auth / Identity Platform on GCP). The API verifies
    the provider's signed ID token (JWT) on each request in one FastAPI dependency
    (`get_current_user`), which every protected route declares. 401 = not signed in, 403 = signed in
    but not allowed.
  - *Data model:* `users(id, provider_subject UNIQUE, email, created_at)`,
    `conversations(id, user_id FK, title, created_at)`,
    `messages(id, conversation_id FK, role, content, citations jsonb, created_at)`; an index on
    `(user_id, created_at)` for the sidebar list, which would reuse the cursor pagination.
  - *Authorization:* every conversation query filters by the signed-in `user_id` (never trust an
    ID from the request alone); another user's conversation returns 404, not 403, so its existence
    isn't revealed.
  - *Two different features:* saving chats is storage only. Using earlier turns to answer follow-up
    questions ("and what about class C?") is conversation memory: the question must be rewritten
    into a standalone one before retrieval, and the eval has to cover multi-turn cases.
  - *Also affected:* the rate limiter becomes per-user; logs gain a user ID (and privacy rules for
    stored questions); the frontend needs a login flow, token handling and CORS with credentials.
  - Natural home: the next project (TriageBot), which already plans Firestore/Firebase.
- Asynchronous ingestion: `202 Accepted`, a queue and a worker (see the synchronous-ingest decision).
- Compare `gemini-embedding-2` (available on the same key) against `gemini-embedding-001`.
  Changing the embedding model means re-embedding every chunk: vectors from two models are not comparable.
