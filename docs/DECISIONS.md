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

## Future work (explicitly out of scope)
- _(nothing yet)_
