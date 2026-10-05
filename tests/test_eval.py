"""Tests for the evaluation helpers: loading, the retrieval hint, the sheets, the counting.

No provider and no database: only the pure functions.
"""

from pathlib import Path

import pytest

from eval.run_eval import (
    expected_page_retrieved,
    grades_template,
    grading_sheet,
    load_questions,
    settings_mismatch,
    tabulate,
)

QUESTION = {
    "id": "q01",
    "type": "direct",
    "question": "How thoroughly must safety-critical code be tested?",
    "expected": "100 percent MC/DC coverage.",
    "document": "NPR-7150.2D",
    "clause": "3.7.4",
    "page": 26,
}
UNANSWERABLE = {**QUESTION, "id": "q02", "type": "unanswerable", "document": "none", "page": 0}


def _source(document="NPR-7150.2D", page=26, clause_id="3.7.4"):
    return {
        "document": document,
        "clause_id": clause_id,
        "page": page,
        "score": 0.8,
        "content": "x",
    }


def _run() -> dict:
    def answer(text, refused, hit):
        return {
            "answer": text,
            "refused": refused,
            "expected_page_retrieved": hit,
            "sources": [_source()],
        }

    return {
        "meta": {"started_at": "20261004T120000Z"},
        "results": [
            {
                "question": QUESTION,
                "answers": {
                    "naive": answer("Some answer [NPR, page 26].", False, True),
                    "section_aware": answer("100 percent MC/DC [NPR, 3.7.4].", False, True),
                },
            },
            {
                "question": UNANSWERABLE,
                "answers": {
                    "naive": answer("I don't know based on these documents.", True, None),
                    "section_aware": answer("MISRA says ...", False, None),
                },
            },
        ],
    }


def test_the_real_question_file_is_valid_and_has_twenty_questions():
    questions = load_questions(Path("eval/questions.yaml"))
    assert len(questions) == 20
    assert [q["id"] for q in questions] == [f"q{n:02d}" for n in range(1, 21)]


@pytest.mark.parametrize(
    ("broken", "message"),
    [
        ({**QUESTION, "type": "essay"}, "unknown type"),
        ({**QUESTION, "document": "ISO-26262"}, "unknown document"),
        ({k: v for k, v in QUESTION.items() if k != "expected"}, "missing fields"),
    ],
)
def test_load_questions_rejects_malformed_entries(tmp_path, broken, message):
    import yaml

    path = tmp_path / "q.yaml"
    path.write_text(yaml.safe_dump({"questions": [broken]}))
    with pytest.raises(ValueError, match=message):
        load_questions(path)


def test_load_questions_rejects_duplicate_ids(tmp_path):
    import yaml

    path = tmp_path / "q.yaml"
    path.write_text(yaml.safe_dump({"questions": [QUESTION, QUESTION]}))
    with pytest.raises(ValueError, match="duplicate"):
        load_questions(path)


def test_expected_page_retrieved_needs_the_right_document_and_page():
    assert expected_page_retrieved(QUESTION, [_source(page=26)]) is True
    assert expected_page_retrieved(QUESTION, [_source(page=25)]) is True  # chunk began a page early
    assert expected_page_retrieved(QUESTION, [_source(page=27)]) is False
    assert expected_page_retrieved(QUESTION, [_source(document="NASA-STD-8739.8B")]) is False
    assert expected_page_retrieved(QUESTION, []) is False


def test_expected_page_retrieved_maps_short_names_to_database_titles():
    fda = {**QUESTION, "document": "FDA-OTS", "page": 9}
    title = "Off-the-Shelf Software Use in Medical Devices"
    assert expected_page_retrieved(fda, [_source(document=title, page=9)]) is True


def test_expected_page_retrieved_is_not_applicable_to_unanswerable_questions():
    assert expected_page_retrieved(UNANSWERABLE, [_source()]) is None


def test_grading_sheet_puts_expected_answer_next_to_both_answers():
    sheet = grading_sheet(_run())
    assert "## q01 (direct)" in sheet
    assert "**Expected** (NPR-7150.2D, clause 3.7.4, p.26): 100 percent MC/DC coverage." in sheet
    assert "### naive (refused: False; expected page retrieved: yes)" in sheet
    assert "100 percent MC/DC [NPR, 3.7.4]." in sheet
    assert "### section_aware (refused: False; expected page retrieved: n/a)" in sheet


def test_grades_template_has_an_empty_slot_per_question_and_strategy():
    template = grades_template(_run())
    assert template.count("naive: \n") == 2
    assert template.count("section_aware: \n") == 2
    assert "- id: q01" in template and "- id: q02" in template


def test_tabulate_counts_grades_per_strategy_and_per_type():
    grades = [
        {"id": "q01", "naive": "partial", "section_aware": "correct"},
        {"id": "q02", "naive": "correctly_refused", "section_aware": "wrong"},
    ]
    table = tabulate(grades, _run())

    # columns: correct | partial | wrong | correctly_refused | ungraded | expected page retrieved
    assert "| naive | 0 | 1 | 0 | 1 | 0 | 1 of 1 |" in table
    assert "| section_aware | 1 | 0 | 1 | 0 | 0 | 1 of 1 |" in table
    assert "| unanswerable | naive | 0 | 0 | 0 | 1 |" in table
    assert "| direct | section_aware | 1 | 0 | 0 | 0 |" in table


def test_tabulate_reports_ungraded_and_rejects_unknown_grades():
    assert "| naive | 0 | 0 | 0 | 0 | 1 |" in tabulate([{"id": "q01", "naive": None}], _run())
    with pytest.raises(ValueError, match="unknown grade"):
        tabulate([{"id": "q01", "naive": "great", "section_aware": "correct"}], _run())


def test_resuming_with_a_different_model_or_prompt_is_detected():
    meta = {
        "generation_model": "gemini-3.8-flash",
        "embedding_model": "gemini-embedding-001",
        "prompt_version": "v1",
        "top_k": 5,
    }
    assert settings_mismatch(meta, dict(meta)) == []
    changed = {**meta, "generation_model": "gemini-3.5-flash-lite", "prompt_version": "v2"}
    assert settings_mismatch(meta, changed) == [
        "generation_model: run has 'gemini-3.8-flash', current is 'gemini-3.5-flash-lite'",
        "prompt_version: run has 'v1', current is 'v2'",
    ]
