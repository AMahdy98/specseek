# SpecSeek: interview study guide

Accurate to the code as of **Phase 0**. Sections fill in as phases land; nothing here describes
unbuilt features as if they exist.

## 1. 90-second walkthrough
_(Written after Phase 3, once there is a query path to describe.)_

## 2. Architecture
Current (Phase 0): one FastAPI app, uvicorn server, in-memory document repository.

```mermaid
flowchart LR
  Client -->|HTTP| Uvicorn --> FastAPI --> Routes["routes.py<br/>/health, /documents"]
  Routes -->|Depends| Repo["InMemoryDocumentRepository"]
```

## 3. Request traces
`GET /documents` (Phase 0):
1. uvicorn accepts the connection, parses HTTP, builds the ASGI `scope`.
2. FastAPI matches the route → resolves `Depends(get_repository)` → reads `app.state.repo` (set in the lifespan).
3. Handler `await`s `repo.list_documents()` → returns a copy of the list.
4. FastAPI validates the result against `response_model=list[DocumentSummary]` → JSON.
   Can fail: lifespan didn't run → `AttributeError` → 500; output doesn't match the model → 500.

## 4. Numbers to know cold
| Number | Value |
|---|---|
| Tests | 7 (Phase 0) |
| Chunk size / overlap | not built yet |
| Embedding model + dimension | not decided yet (Gemini `gemini-embedding-001` @ 768 proposed) |
| Top-k | 5 (planned) |
| Corpus size | not ingested yet |
| Eval scores | not measured |
| p50 / p95 latency | not measured |
| Cost per query | not measured |
| Docker image size | not built yet |

## 5. Decisions
See `DECISIONS.md`. Short form so far:
- Repo on WSL filesystem, not `/mnt/f` → I/O speed and inotify.
- uv + lockfile, not pip + requirements.txt → reproducible installs.
- Repository behind a Protocol → tests inject fakes, Postgres swaps in without touching routes.
- Ruff `ASYNC` rules → catches blocking calls in `async def` statically.
- Licensed PDFs never committed or served publicly → copyright.

## 6. Bugs (STAR)
_(None yet. Only real bugs from BUGS.md go here.)_

## 7. Known limitations
- Phase 0: no persistence; routes not yet under `/v1`.

## 8. Follow-up ladders
**Async endpoints**
- Q: What happens if you call `time.sleep(2)` in an `async def` endpoint?
  A: It blocks the event loop thread, so all requests serialize: 10 concurrent → last waits ~20 s.
- Follow-up: How do you fix it?
  A: Use an async API (`asyncio.sleep`, `httpx.AsyncClient`); for unavoidable blocking code, `asyncio.to_thread` / `run_in_executor`; or a plain `def` endpoint (FastAPI's threadpool, 40 threads by default).
- Follow-up: When would a thread pool not help?
  A: CPU-bound pure-Python work holds the GIL → use a process pool. Libraries that release the GIL in C code (e.g. PyMuPDF) are fine in threads.
