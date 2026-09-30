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

## Future work (explicitly out of scope)
- _(nothing yet)_
