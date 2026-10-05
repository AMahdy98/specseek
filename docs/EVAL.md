# Evaluation log

**Status: run complete; graded by me on 2026-10-05, then revised once the same day after a review
of my grading (see "Grading review").** The numbers below are my final grades.

## Method
- **Questions:** 20, in `eval/questions.yaml`: 12 direct, 3 table, 3 cross-reference, 2 unanswerable;
  6 on NPR 7150.2D, 6 on NASA-STD-8739.8B, 3 on the FDA Premarket guidance, 3 on the FDA
  Off-The-Shelf guidance, 2 on topics outside the corpus.
- **Where the questions came from (disclosure):** the AI assistant proposed 40 candidates from the
  document text, each with its expected answer, clause and PDF page (`eval/candidates.yaml`).
  I chose 20 and verified each expected answer against the PDF (`verified: true`).
  Weakness: the proposer had seen how the documents were chunked, so the set may favour passages
  that chunk cleanly; and the questions are not purely from my own domain knowledge.
- **What is compared:** the two chunking strategies, `naive` and `section_aware`. Everything else is
  held constant: same question, same query embedding (computed once and reused), top-k 5, prompt
  version, generation model, temperature 0.
- **Runner:** `eval/run_eval.py` calls the query service directly (no HTTP) and saves, per question
  and strategy, the answer, whether it was a refusal, and the five retrieved passages with scores.
- **Grading:** by me, by hand: `correct` / `partial` / `wrong` / `correctly_refused`. A refusal on an
  answerable question is `wrong`; an answer to an unanswerable question is `wrong`.
- **Objective hint, not a grade:** "expected page retrieved" = a passage from the expected document
  and page (or the page before) was among the five sources.

## Run
| | |
|---|---|
| Run file | `eval/runs/20261005T121102Z.json` (+ `-grading.md`, `-grades.yaml`) |
| Code | git `5d09480` at start; resumed once after a provider 429, under a logging-only change |
| Generation model | `gemini-3.5-flash-lite`, temperature 0 |
| Embedding model | `gemini-embedding-001`, 768 dimensions |
| Prompt version / top-k | v1 / 5 |
| Corpus | 4 documents, 225 pages, 956 naive chunks, 640 section-aware chunks |

## Results (final grades)
| Strategy | Correct | Partial | Wrong | Correctly refused | Expected page retrieved |
|---|---|---|---|---|---|
| naive | 10 | 3 | 5 | 2 | 14 of 18 |
| section_aware | 14 | 2 | 2 | 2 | 16 of 18 |

On the 18 answerable questions: naive 10 correct (56%), section-aware 14 correct (78%).
Both strategies refused both unanswerable questions.

| Type | Strategy | Correct | Partial | Wrong | Correctly refused |
|---|---|---|---|---|---|
| direct (12) | naive | 9 | 1 | 2 | – |
| direct (12) | section_aware | 10 | 1 | 1 | – |
| table (3) | naive | 0 | 2 | 1 | – |
| table (3) | section_aware | 2 | 0 | 1 | – |
| cross-reference (3) | naive | 1 | 0 | 2 | – |
| cross-reference (3) | section_aware | 2 | 1 | 0 | – |
| unanswerable (2) | naive | – | – | – | 2 |
| unanswerable (2) | section_aware | – | – | – | 2 |

## What the result does and does not show
- Section-aware was better on this set: 4 more correct answers, 3 fewer wrong ones.
- It is 20 questions, one run, one grader, one LLM. With 18 answerable questions each one is worth
  5.6 points, so "56% vs 78%" is a difference of four questions. It is evidence, not proof.
- Every failure of either strategy was a **refusal or an omission**, with one exception: one naive
  answer cited a page it had not been given (q11). No answer stated something false about a
  requirement.
- Section-aware lost once to naive (q09), for a reason that is specific to its design.

## Failures, with evidence from the saved sources
Evidence = searching the five passages that were actually given to the model for the text of the
expected answer. 12 answers were not fully correct: 8 naive, 4 section-aware.

| Q | Strategy | Grade | What happened | Category |
|---|---|---|---|---|
| q04 | naive | partial | The list item "(a) Category 1 projects" was in none of the five passages: the 512-character window ended mid-list. | chunk boundary cut a list |
| q05 | naive | wrong | Refused. The Appendix C page (p66) was not retrieved. | table: retrieval miss |
| q05 | section_aware | wrong | Refused, although the row (clause 3.9.2, p66) was retrieved, ranked 5th. The row is extracted one cell per line and the "Authority" column has no label inside the chunk. | table split |
| q09 | section_aware | partial | Gave who writes the plan (4.4.2.2) but not who concurs (4.4.2.3). The second clause is its own chunk and was not retrieved. Naive got both because they share a window. | answer spans two clauses |
| q11 | naive | partial | Content right, but it cites "[NASA-STD-8739.8B, page 5]" three times; page 5 was not among the passages (pages 31, 27, 34, 27, 31). | fabricated citation |
| q12 | naive | wrong | Refused. Section 1.4 (p6) was not retrieved. | cross-reference: retrieval miss |
| q12 | section_aware | partial | Covers section 4.5 (the SMA TA approves) but not the 1.4 half (Center TA per NPR 8715.3); 1.4 was not retrieved. | cross-reference: half retrieved |
| q14 | naive | partial | "objective pass/fail determination" was in none of the five passages: the window ended before it. | chunk boundary cut a sentence |
| q15 | naive | wrong | Refused. Two windows from the right page (p30) were retrieved, but neither contained the version-history text. | retrieval miss: vocabulary ("record of software versions" vs "Software Version History") |
| q15 | section_aware | wrong | Refused. No FDA passage was retrieved. The version-history text sits inside a 2,788-character chunk labelled `VI.2`, together with testing and anomalies, because this PDF's subsection headings carry no letter. | retrieval miss: chunk too coarse + vocabulary |
| q16 | naive | wrong | Refused although the III.A.1 list was among the passages (p7). The question says "third-party component", the text says "OTS software". | wrong refusal (generation) |
| q18 | naive | wrong | Refused. Section III.A.5 (p8) was not retrieved. | cross-reference: retrieval miss |

Split by where the fault lies:
- **9 of 12: retrieval or chunking.** The right text never reached the model, or reached it cut or
  only in part (q04, q05 naive, q09, q12 both, q14, q15 both, q18).
- **2 of 12: a refusal over text that was present** (q05 section-aware, q16 naive).
- **1 of 12: a fabricated citation** (q11 naive).

## Grading review (what changed and why)
After my first pass I asked the assistant to review my grading. It checked each failure against the
saved passages and raised six points. My decisions:
1. **q11 naive: correct → partial.** Accepted: citing a page that was never supplied is an error
   even when the content is right.
2. **q12 section-aware: correct → partial.** Accepted: half of the expected answer (section 1.4)
   is missing.
3. **q07 section-aware: stays correct.** It joins the two conditions with "or"; the source has two
   separate sentences and no connective. My expected answer says "and", which is equally an
   interpretation. I judged the answer faithful to the source. The expected answer's wording is a
   known imprecision in `eval/questions.yaml`.
4. **q04 category:** changed from "vocabulary mismatch" (evidence: chunk boundary).
5. **q14 category:** removed "table split" (evidence: chunk boundary; the answer came from body text).
6. **q15:** recorded as a retrieval failure for both strategies, not a wrong refusal.

First-pass totals, for the record: naive 11 / 2 / 5 / 2, section-aware 15 / 1 / 2 / 2.
A reviewer other than the grader changed two grades out of 40; a second independent grader would
be the next step for a more trustworthy number.

## What I would change, in order (none of it done yet; each needs a re-run to claim an effect)
1. **Retrieve neighbours:** when a clause is retrieved, also pass the next clause (fixes q09-type
   answers that span two short clauses).
2. **Contextual headers:** embed each chunk with its document title and heading in front, so
   "Software Version History" is part of what is embedded (targets q15).
3. **Finer FDA sections:** use the PDF bookmarks to split section VI into its subsections, which the
   text layer alone cannot do (targets q15).
4. **Table rows as rows:** rebuild "column: value" text for table rows (targets q05).
5. **Citation check:** verify in code that every cited page/clause is among the supplied passages,
   and flag or strip the ones that are not (targets q11).
6. **Synonyms in the question** (e.g. third-party ↔ off-the-shelf) need query rewriting or keyword
   search; hybrid search is on the do-not-build list, so this stays future work.

## Limitations of this evaluation
- 20 questions, one run, one grader; no confidence interval can honestly be put on the numbers.
- Question provenance as disclosed above.
- The page-level retrieval hint can say "yes" when the right page but the wrong window was
  retrieved (q15 naive); the failure table above uses text search in the passages instead.
- The LLM is a free-tier "lite" model. An earlier, incomplete run with `gemini-3.8-flash`
  (`eval/runs/20261004T184355Z`, 23 answers, hit that model's 20-requests/day limit) was **not
  graded and is not part of these results**.

## Trial runs (not part of the results)
- 2026-10-04: one question (q05) run once to test the runner. Not graded, not counted.
