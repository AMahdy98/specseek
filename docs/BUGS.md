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
