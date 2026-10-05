# Performance log

## What was measured, and what was not
- **Measured:** latency of `POST /v1/query`, end to end over HTTP against the Compose stack on my
  machine, and broken down per stage from the `Server-Timing` response header.
- **Not measured:** throughput or behaviour under heavy load. The free-tier LLM allows 15 requests
  per minute, so pushing harder would measure the provider's throttling, not this system.
- Script: `eval/load_test.py`. Raw samples: `eval/perf/20261005T135100Z.json`.

## Setup (2026-10-05)
| | |
|---|---|
| Client | the script, on the WSL host, to `localhost:8000` |
| Server | `api` container (uvicorn, 1 process) + `db` container (Postgres 16, pgvector 0.8.6) |
| Corpus | 4 documents, 1,596 chunks; default strategy `section_aware`, top-k 5 |
| Models | `gemini-embedding-001` (768 dims), `gemini-3.5-flash-lite`, temperature 0 |
| Questions | the 18 answerable evaluation questions, cycled |
| Plan | 24 requests one at a time, one every 5 s; then, after 65 s pauses, two bursts of 6 simultaneous requests |

## Results
36 of 36 requests returned 200. The provider logged no retries during the test.

| Phase | Requests | Metric | p50 ms | p95 ms | min ms | max ms |
|---|---|---|---|---|---|---|
| one at a time | 24 | **total** | **1300** | **2049** | 827 | 2366 |
| one at a time | 24 | embed | 283 | 390 | 265 | 422 |
| one at a time | 24 | search | 2 | 4 | 1 | 4 |
| one at a time | 24 | generate | 980 | 1766 | 541 | 2082 |
| 6 at once | 12 | **total** | **1694** | **2042** | 1270 | 2042 |
| 6 at once | 12 | embed | 497 | 568 | 436 | 568 |
| 6 at once | 12 | search | 1 | 3 | 1 | 3 |
| 6 at once | 12 | generate | 1183 | 1496 | 806 | 1496 |

Percentiles are nearest-rank (always an observed value). With 24 samples, p95 is the 23rd
smallest; with 12 samples it is the largest. These are small samples: read them as "about 1.3 s
typical, about 2 s for the slow ones", not to the millisecond.

### Where the time goes (one at a time)
| Stage | Share of total time |
|---|---|
| generate (LLM call) | 76.8% |
| embed (embedding call) | 22.9% |
| search (Postgres vector query) | 0.2% |
| everything else (HTTP, validation, JSON, middleware) | about 3 ms per request (median 2.9, max 3.8) |

99.7% of the latency is two calls to an external provider. The part I wrote and the database
together are a few milliseconds.

### Under concurrency (6 at once)
- All six were answered in 1.3–2.0 s, i.e. concurrently, not one after another: six sequential
  requests would have taken about 8 s. This is the async design doing its job: while one request
  waits on the provider, the event loop serves the others.
- Median total rose from 1300 to 1694 ms. Most of that is the embed stage (283 → 497 ms).
  **Hypothesis, not verified:** the shared HTTP client has one warm connection to the provider;
  six simultaneous requests need five new TLS connections, and the handshake is paid in the
  first provider call of each request, which is the embedding. To verify: log connection reuse,
  or warm the pool and re-run.
- Search stayed at 1–3 ms: no sign of contention for database connections at this level.

## Prompt size and cost per query
From the graded evaluation run (`eval/runs/20261005T121102Z.json`), characters of retrieved
context sent to the LLM per question:

| Strategy | Median | Min | Max |
|---|---|---|---|
| naive | 2,560 | 2,560 | 2,560 |
| section_aware | 3,626 | 1,126 | 13,792 |

- Naive is always 5 × 512 characters. Section-aware varies with clause length: up to 5 chunks of
  3,200 characters, about 4,000 tokens at 4 characters per token.
- Median answer: 260 characters (naive), 408 (section-aware).
- Rough tokens per section-aware query: about 900 of context + about 300 of system prompt and
  question in, about 100 out (medians; estimated at 4 chars/token, not counted by a tokenizer).
- **Cost in money: zero on the free tier; not measured for a paid tier.** I have not looked up
  current prices, so there is no dollar figure here.
- Cost in quota: 1 embedding (of 1,000/day) and 1 generation (of 500/day, 15/minute) per question.
  The binding limit for a public demo is **15 questions per minute**.

## Earlier observation, for comparison
With `gemini-3.8-flash` (2026-10-03, 9 hand-run questions, not a load test) generation took
3–23 s including retries on "503 high demand". The model, not the code, moved typical latency
from several seconds to about 1.3 s.

## "This endpoint is slow": the checklist, walked on this data
1. **Measure before guessing: where is the time?** `Server-Timing` on any response, or the
   `query_complete` log line: embed / search / generate. Here: 77% generate, 23% embed.
2. **Is it every request or the tail?** p50 1.3 s vs p95 2.0 s: a mild tail, all of it in the
   generate stage (980 → 1766 ms). No retries were logged, so it is the provider's own variance
   (answer length varies).
3. **Network / client side?** Total measured by the client minus the server's three stages is
   about 3 ms: nothing lost outside the server.
4. **Is the server blocking its event loop?** Six simultaneous requests finished together in under
   2.1 s. A blocking call would have serialized them.
5. **Database: slow query, missing index, pool exhaustion?** Search is 1–4 ms and did not grow
   under concurrency. (`EXPLAIN ANALYZE` in DECISIONS.md: exact scan over the filtered rows.)
6. **Third-party dependency?** Yes: this is the answer. Both dominant stages are provider calls.
7. **Payload size?** Up to about 14,000 characters of context in the worst case; generation time
   grows with input and, mostly, output length.
8. **Can it be cached?** Identical question + same documents + same prompt version would give the
   same answer at temperature 0. A response cache would turn a repeat question from 1.3 s into a
   few milliseconds. Not built (optional item).

## What would make it faster, in order of expected effect (none done; each needs re-measuring)
1. **Cache answers** for repeated questions (removes both provider calls on a hit).
2. **Cache question embeddings** (removes 23% on a repeat even when the answer is not cached).
3. **Shorter context:** fewer or smaller passages (lower top-k) reduces LLM input; it trades
   against answer quality, so it must be checked with the evaluation, not just timed.
4. **Warm provider connections** if the concurrency hypothesis above holds.
5. **Streaming the answer** would cut *perceived* latency (first words sooner), not total time. It is
   on the do-not-build list for this project.

## Limits of this measurement
- One machine, one run, 36 requests, a provider whose latency varies by time of day.
- No sustained or high-concurrency load; no failure injection.
- The burst phase has 12 samples.
