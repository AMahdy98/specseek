# Bugs

Real bugs only. Template:

```
## YYYY-MM-DD: short title
- Symptom:
- Root cause:
- How I found it:
- Fix:
- What I'd do to catch it earlier:
```

## 2026-10-02: FDA headings glued together ("III.Scope"), so most of the document had no clause ID
- **Symptom:** after the first run of the section-aware chunker on the real corpus, 66% of the
  text of the FDA Premarket guidance (and 29% of the Off-The-Shelf guidance) had `clause_id = None`.
  Only `VII`, `Appendix A` and `Appendix B` were detected; `I`–`VI` and all `A.`/`B.` subsections
  were missing. All 23 chunker unit tests were green.
- **Root cause:** the PDF stores a heading as three spans: `'III.'`, `' '`, `'Scope '`. The parser
  filtered out whitespace-only spans *before* joining span text, which deleted the space and
  produced `III.Scope`. The heading rule requires "marker, whitespace, title", so it never matched.
  `VII.` was stored as a single span, which is why that one heading still worked.
- **How I found it:** ran the chunker on the corpus and printed per-document stats (share of text
  without a clause ID, list of detected IDs). Then dumped the raw spans of lines starting with a
  roman numeral and saw the separate `' '` span.
- **Fix:** `parser._line_text` joins *all* spans for the text; only the bold check ignores
  whitespace-only spans. Regression test: `test_line_text_keeps_the_space_stored_as_its_own_span`.
  Text without a clause ID after the fix: Premarket 66% → 16%, Off-The-Shelf 29% → 7%. After the
  later marker-joining change (`I.` + `Introduction` on one row): Premarket 7%, Off-The-Shelf 8%
  (what remains is cover pages and contents).
- **What I'd do to catch it earlier:** the unit tests used hand-built lines, so they could not see
  a parser/PDF interaction. Running on real documents and looking at an aggregate
  ("% of text with no clause ID") caught it in minutes. That check should be part of ingest.

## 2026-10-02: Five minutes of pointless retries against an exhausted daily quota
- **Symptom:** ingesting the fourth document (NPR 7150.2D) logged `provider_retry` six times over
  five minutes, then returned 502. Earlier documents had recovered from HTTP 429 after one wait.
  A single-text request sent by hand at the same moment succeeded.
- **Root cause:** two different limits answer with the same status code. The earlier 429s were the
  per-minute limit ("retry in 23s"). This one was the free tier's daily limit of 1,000 texts per
  model (`EmbedContentRequestsPerDay...FreeTier`); the error body said `retryDelay: 16464s`. My
  code clamped any requested delay to 60 s, so it slept 60 s and retried a request that could not
  succeed for 4.5 hours. About 905 texts had been used; the batch of 100 crossed the limit.
- **How I found it:** the retry pattern in the JSON logs looked different (attempts 1 to 5 on one
  batch), so I sent the same batch by hand and read the full error body.
- **Fix:** if the provider asks for a wait longer than our maximum backoff, raise `ProviderError`
  immediately with the wait in the message ("quota exhausted; retry in about 274 minutes").
  Verified: the same request now fails in 0.8 s. Regression test:
  `test_a_long_requested_wait_fails_immediately_instead_of_retrying`.
- **What held up:** no partial data. The document row and chunks are written in one transaction
  after embedding, so the failed ingest left nothing behind and can simply be re-sent.
- **What I'd do to catch it earlier:** read the provider's rate-limit page for *all* limits (per
  minute and per day) before the first bulk run, and size the batch job against them: the corpus
  is 1,596 texts, more than one day of free quota.

## 2026-10-02: API container crashed on start: `ModuleNotFoundError: No module named 'httpx'`
- **Symptom:** after adding the embedding provider, all 79 tests passed locally, but the rebuilt
  container exited with code 1 immediately; `curl` got no response. Container log: the import of
  `httpx` in `app/main.py` failed.
- **Root cause:** in phase 0 `httpx` was added with `uv add --dev` because only the tests used it.
  The Dockerfile installs with `uv sync --no-dev`, so the image had no `httpx` once application
  code started importing it. My local environment has the dev group installed, which hid it.
- **How I found it:** `docker compose ps -a` (Exited (1)) then `docker compose logs api`.
- **Fix:** `uv remove --dev httpx && uv add httpx` (now a runtime dependency).
- **What I'd do to catch it earlier:** run the test suite, or at least an import smoke test,
  inside the production image in CI. "Tests pass on my machine" only proved the dev environment.

## 2026-10-02: Table-of-contents entries became 75 one-line "clauses"
- **Symptom:** NPR 7150.2D produced 391 section-aware chunks, 75 of them under 80 characters,
  e.g. `P.1 Purpose`, `3.1 Software Life Cycle Planning`; 134 clause IDs appeared on more than one chunk.
- **Root cause:** the decimal-clause rule ("a line starting with `3.1` + uppercase text starts a
  clause") is also true of every contents-page entry, so each entry became a section containing
  only its own title. The real section later in the document then duplicated the ID.
- **How I found it:** same corpus stats: count of tiny chunks and of repeated clause IDs.
- **Fix:** `_demote_contents_entries`: a one-line, non-bold, title-like section (doesn't end like
  a sentence) whose clause ID appears again later is a contents entry; its line is merged into the
  preceding section. A real one-line requirement ends with `.` or `]`, so it keeps its ID even
  when a mapping table repeats it later (tested). Companion rule `_promote_untitled_headings` for
  non-bold table section rows. After: 341 chunks, 19 under 80 chars (all real one-line clauses).
- **What I'd do to catch it earlier:** include a contents page in the synthetic fixtures; I only
  modelled body pages.
