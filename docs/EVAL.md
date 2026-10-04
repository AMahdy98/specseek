# Evaluation log

**Status: method defined, not yet run in full, nothing graded.** No score below is real until this
line changes.

## Method
- **Questions:** 20, in `eval/questions.yaml`: 12 direct, 3 table, 3 cross-reference, 2 unanswerable;
  6 on NPR 7150.2D, 6 on NASA-STD-8739.8B, 3 on the FDA Premarket guidance, 3 on the FDA
  Off-The-Shelf guidance, 2 on topics outside the corpus.
- **Where the questions came from (disclosure):** the AI assistant proposed 40 candidates from the
  document text, each with its expected answer, clause and PDF page (`eval/candidates.yaml`).
  I chose 20 and verify each expected answer against the PDF (`verified: true` in the file).
  Weakness: the proposer had seen how the documents were chunked, so the set may favour passages
  that chunk cleanly; and the questions are not purely from my own domain knowledge.
- **What is compared:** the two chunking strategies, `naive` and `section_aware`. Everything else is
  held constant: same question, same query embedding (computed once and reused), top-k 5, prompt
  version, generation model, temperature 0.
- **Runner:** `eval/run_eval.py` calls the query service directly (no HTTP) and saves, per question
  and strategy, the answer, whether it was a refusal, and the five retrieved passages with scores
  (`eval/runs/<timestamp>.json`), plus a reading sheet (`-grading.md`).
- **Grading:** by me, by hand, into `eval/runs/<timestamp>-grades.yaml`, one of
  `correct` / `partial` / `wrong` / `correctly_refused`. A refusal on an answerable question is
  `wrong`; an answer to an unanswerable question is `wrong`.
- **Objective hint, not a grade:** "expected page retrieved" = a passage from the expected document
  and page (or the page before, since a chunk records the page it starts on) was among the five
  sources. It separates retrieval misses from generation faults.
- **Counting:** `python -m eval.run_eval tabulate <grades file>`.

## Results
| Strategy | Correct | Partial | Wrong | Correctly refused | Expected page retrieved |
|---|---|---|---|---|---|
| naive | – | – | – | – | – |
| section_aware | – | – | – | – | – |

Run: _(timestamp, git commit, prompt version, models: filled in from the run file's `meta`)_

## Failures by category
_(After grading: each non-correct answer with its category (table split, vocabulary mismatch,
near-duplicate chunks, hallucination, missed refusal, wrong refusal) and what I would change.)_

## Trial runs (not part of the results)
- 2026-10-04: one question (q05) run once to test the runner. Not graded, not counted.
