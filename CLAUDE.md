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
- Frontend (phase 5): React + TypeScript + Vite, no framework, plain fetch
- Deploy (phase 6): Docker → GCP Artifact Registry → Cloud Run, config via env vars, API key via Secret Manager

## Architecture
- `POST /ingest`: accepts a PDF (or a path to one in `data/`), parses, chunks, embeds, stores
- `POST /query`: body `{question, document_id?}`; embeds the question, top-5 cosine search (optional filter by document), builds a grounded prompt, returns `{answer, citations: [{clause_id, heading, document, snippet, score}]}`
- `GET /documents`: lists ingested docs with chunk counts
- `GET /health`: liveness + DB connectivity

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
  docs/  (DECISIONS.md, BUGS.md, EVAL.md)
  frontend/  Dockerfile  docker-compose.yml  README.md  CLAUDE.md
```

## Corpus
3–5 real standards documents that I can **legally obtain and use**. Help me choose. Good candidates are freely published specs with numbered clauses and requirements (e.g. AUTOSAR specifications, ECSS standards, NASA software standards). Paywalled ones (ISO 26262, some CiA docs) only if I actually have legitimate copies. Verify the licensing situation with me before we commit any PDF to the repo. Whatever corpus we end up with is what my CV will name.

## Evaluation (the most important artifact, never skip)
- `eval/questions.yaml`: 20 questions **I write** from my domain knowledge, each with the expected answer and the clause ID it lives in. Include some table-based questions, some cross-reference questions, and 2–3 unanswerable ones to test refusal.
- `eval/run_eval.py` runs all 20 against both chunking strategies and saves the raw answers. **I grade them manually** (correct / partially correct / wrong / correctly refused). The script can help tabulate, but a human judgment is final.
- `docs/EVAL.md` records per-strategy scores, and each remaining failure with its category (table split, vocabulary mismatch, near-duplicate chunks, hallucination, etc.) and what I'd change.

## Phases (each ends with a working, committed state)
0. **Skeleton + FastAPI/asyncio fundamentals**: project setup, `/health`, `/documents` against an in-memory list, Pydantic models, dependency injection, one pytest. Teach: ASGI/Starlette/uvicorn request lifecycle, async vs blocking, `run_in_executor` for CPU work.
1. **Docker + Postgres/pgvector**: Dockerfile (layer caching, why requirements are copied before source, multi-stage), Compose with the API and Postgres, schema with a vector column + index, `/health` checks the DB.
2. **Ingestion**: PDF parsing, both chunkers, embeddings, storage. Unit tests for the chunkers (clause IDs preserved, nothing lost, overlap correct). Teach: what an embedding is geometrically, cosine similarity, why chunking strategy dominates RAG quality.
3. **Retrieval + generation**: top-k search, grounded prompt, citations in the response, `/query` endpoint + one API test with the LLM mocked. Teach: the main RAG failure modes.
4. **Eval**: write questions, run both strategies, grade, fill in EVAL.md.
5. **React UI**: question box, answer, citation list. Teach: components, `useState`, `useEffect`, fetching, CORS.
6. **Cloud Run deploy**: public URL, env vars, secret. Decide Cloud SQL vs another hosted Postgres with me and note the cost.
7. **README**: architecture diagram (Mermaid), setup steps a stranger can follow, eval summary.

Stretch (only if everything above is done): a retrieval relevance floor, so if the best score is below a threshold the model isn't called at all.

## Do NOT build
Auth, multi-user, rerankers, hybrid/BM25 search, conversation memory, streaming responses (that's the next project), an upload UI, any eval framework beyond the hand-written set, fine-tuning, Kubernetes, LangChain/LlamaIndex (I'm writing the pipeline myself to understand it).

## Current status (update at the end of every session)
- **2026-09-29, session 1:** Phase 0 done (`/health`, `/documents` on an in-memory repo, 7 tests green).
  Env: uv 0.12 + Python 3.12 in WSL; Docker Engine not yet installed (native engine + compose plugin chosen).
  Provider: Google Gemini free tier recommended (gemini-embedding-001 at 768 dims, called via raw httpx), awaiting API key.
  Corpus: NASA-STD-8739.8B + NPR 7150.2D proposed as public corpus (awaiting confirmation); CiA 301/402 local-only; IEC 62304 excluded (see DECISIONS.md).
  **Next:** Phase 1 (Docker + Postgres/pgvector).

## First session
1. Save this brief to `CLAUDE.md`.
2. Ask me, in one message: whether Docker (and which setup), uv, Node and gcloud are already installed in WSL; which LLM/embedding API keys I have; which standards PDFs I already have access to. Then verify with commands (`docker --version`, `uv --version`, `node -v`, `which python3`) instead of taking my word for it.
3. Then start Phase 0 with the concept briefing, and give me the first skeleton to fill in.
