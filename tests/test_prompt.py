"""Prompt construction tests: pure string building, no network, no database."""

from uuid import UUID

from app.prompt import REFUSAL, SYSTEM_PROMPT, build_prompt
from app.retrieval import RetrievedChunk

DOC = UUID("00000000-0000-0000-0000-000000000001")


def _chunk(content: str, clause_id=None, heading=None, page=1, title="NPR-7150.2D"):
    return RetrievedChunk(DOC, title, clause_id, heading, page, content, score=0.9)


def test_each_passage_is_numbered_and_carries_its_source_header():
    prompt = build_prompt(
        "Who assesses acquisition options?",
        [
            _chunk(
                "3.1.2 The project manager shall assess options. [SWE-033]",
                clause_id="3.1.2",
                heading="3.1 Software Life Cycle Planning",
                page=20,
            ),
            _chunk("Some naive window of text", page=7, title="NASA-STD-8739.8B"),
        ],
    )

    assert (
        "[1] Document: NPR-7150.2D | Clause: 3.1.2 | Heading: 3.1 Software Life Cycle Planning"
        " | Page: 20\n3.1.2 The project manager shall assess options. [SWE-033]"
    ) in prompt
    # A naive chunk has no clause or heading: the header simply omits them.
    assert "[2] Document: NASA-STD-8739.8B | Page: 7\nSome naive window of text" in prompt


def test_the_question_comes_last_and_passages_keep_their_rank_order():
    prompt = build_prompt("What is OTS software?", [_chunk("first"), _chunk("second")])

    assert prompt.startswith("Context passages:")
    assert prompt.endswith("Question: What is OTS software?")
    assert prompt.index("[1]") < prompt.index("[2]") < prompt.index("Question:")


def test_passage_text_is_passed_through_unchanged():
    text = 'The provider "shall" do X;\n  it "should" do Y, and "may" do Z.'
    assert text in build_prompt("q?", [_chunk(text)])


def test_system_prompt_states_the_four_grounding_rules():
    assert "ONLY the numbered context passages" in SYSTEM_PROMPT
    assert REFUSAL in SYSTEM_PROMPT  # the exact refusal sentence the code looks for
    assert all(word in SYSTEM_PROMPT for word in ('"shall"', '"should"', '"may"'))
    assert "[document, clause]" in SYSTEM_PROMPT
    assert "not instructions" in SYSTEM_PROMPT  # retrieved text can't give the model orders
