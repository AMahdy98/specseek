"""Chunker tests, written before the implementation (TDD).

The three properties the project brief demands: clause IDs preserved, nothing lost,
overlap correct. Inputs are hand-built `Line` lists modelled on real lines from the
corpus, so these run in milliseconds with no PDF.
"""

from app.ingest.chunkers import (
    chunk_naive,
    chunk_section_aware,
    split_recursive,
)
from app.ingest.types import Line


def L(text: str, page: int = 1, bold: bool = False) -> Line:
    return Line(text=text, page=page, bold=bold)


# ---------------------------------------------------------------- naive


def test_naive_loses_nothing_and_respects_window():
    lines = [L(f"line {i} " + "x" * 40, page=1 + i // 10) for i in range(60)]
    chunks = chunk_naive(lines, window=512)

    assert "".join(c.content for c in chunks) == "\n".join(line.text for line in lines)
    assert all(len(c.content) == 512 for c in chunks[:-1])
    assert 0 < len(chunks[-1].content) <= 512


def test_naive_metadata():
    lines = [L("a" * 600, page=1), L("b" * 600, page=2)]
    chunks = chunk_naive(lines, window=512)

    assert [c.chunk_index for c in chunks] == list(range(len(chunks)))
    assert all(c.strategy == "naive" and c.clause_id is None for c in chunks)
    assert chunks[0].page == 1
    assert chunks[-1].page == 2  # page of the chunk's first character


def test_naive_empty_document():
    assert chunk_naive([]) == []


# ---------------------------------------------------------------- section-aware: clause IDs

# Modelled on NPR 7150.2D p.20: a bold section title, then numbered requirement paragraphs.
NPR_LINES = [
    L("3.1 Software Life Cycle Planning", page=20, bold=True),
    L("3.1.1 Software life cycle planning covers the software aspects of a project.", page=20),
    L("It is an organizing process that considers the software as a whole.", page=20),
    L("3.1.2 The project manager shall assess options for software acquisition", page=20),
    L("versus development. [SWE-033]", page=20),
    L("3.1.3 The project manager shall develop, maintain, and execute software plans.", page=21),
]


def test_decimal_clauses_become_one_chunk_each_with_their_id():
    chunks = chunk_section_aware(NPR_LINES)

    assert [c.clause_id for c in chunks] == ["3.1.1", "3.1.2", "3.1.3"]
    assert "[SWE-033]" in chunks[1].content
    assert chunks[1].content.startswith("3.1.2 The project manager shall")
    assert [c.page for c in chunks] == [20, 20, 21]
    assert all(c.strategy == "section_aware" for c in chunks)
    assert [c.chunk_index for c in chunks] == [0, 1, 2]


def test_paragraph_clauses_inherit_the_nearest_titled_heading():
    chunks = chunk_section_aware(NPR_LINES)
    assert all(c.parent_heading == "3.1 Software Life Cycle Planning" for c in chunks)


def test_heading_only_sections_produce_no_chunk():
    # "3.1 Software Life Cycle Planning" has no body of its own: it survives as the
    # parent_heading of its children, not as a useless one-line chunk.
    chunks = chunk_section_aware(NPR_LINES)
    assert not any(c.clause_id == "3.1" for c in chunks)


def test_titled_section_with_body_keeps_its_own_heading():
    lines = [
        L("4.2 Safety-Critical Software Determination", bold=True),
        L("Software is classified as safety-critical if it meets one of the criteria."),
    ]
    (chunk,) = chunk_section_aware(lines)
    assert chunk.clause_id == "4.2"
    assert chunk.parent_heading == "4.2 Safety-Critical Software Determination"
    assert chunk.content.startswith("4.2 Safety-Critical Software Determination\nSoftware is")


def test_wrapped_bold_heading_title_is_joined():
    lines = [
        L("4. SOFTWARE ASSURANCE AND SOFTWARE SAFETY", bold=True),
        L("REQUIREMENTS", bold=True),
        L("4.1 Software Assurance Description", bold=True),
        L("The Software Assurance activities provide a level of confidence."),
    ]
    (chunk,) = chunk_section_aware(lines)
    assert chunk.clause_id == "4.1"
    assert chunk.parent_heading == "4.1 Software Assurance Description"


def test_text_before_the_first_heading_is_kept_without_a_clause_id():
    lines = [L("NASA TECHNICAL STANDARD"), L("Approved: 2022-09-08"), *NPR_LINES]
    chunks = chunk_section_aware(lines)
    assert chunks[0].clause_id is None
    assert chunks[0].content == "NASA TECHNICAL STANDARD\nApproved: 2022-09-08"
    assert chunks[1].clause_id == "3.1.1"


def test_appendix_clause_ids():
    lines = [
        L("Appendix C. Requirements Mapping Matrix", bold=True),
        L("C.1 The rationale for the requirements is contained in the handbook."),
        L("C.2 The Requirements Mapping Matrix documents the mappings."),
    ]
    chunks = chunk_section_aware(lines)
    assert [c.clause_id for c in chunks] == ["C.1", "C.2"]
    assert chunks[0].parent_heading == "Appendix C. Requirements Mapping Matrix"


def test_table_of_contents_entries_are_not_clauses():
    # Found on NPR 7150.2D: its contents page lists "3.1 Software Life Cycle Planning",
    # and the same ID appears again later as the real section.
    lines = [
        L("TABLE OF CONTENTS", page=2),
        L("3.1 Software Life Cycle Planning", page=2),
        L("3.2 Software Cost Estimation", page=2),
        L("3.1 Software Life Cycle Planning", page=20, bold=True),
        L("3.1.1 Planning covers the software aspects of a project.", page=20),
        L("3.2 Software Cost Estimation", page=23, bold=True),
        L("3.2.1 The project manager shall establish cost estimates. [SWE-015]", page=23),
    ]
    chunks = chunk_section_aware(lines)

    assert [c.clause_id for c in chunks] == [None, "3.1.1", "3.2.1"]
    assert chunks[0].content == (
        "TABLE OF CONTENTS\n3.1 Software Life Cycle Planning\n3.2 Software Cost Estimation"
    )


def test_one_line_requirement_keeps_its_id_even_if_the_id_repeats_later():
    # A real one-line clause ends like a sentence; it must not be mistaken for a contents
    # entry just because a mapping table repeats its number later.
    lines = [
        L("3.3.1 The project manager shall document a schedule. [SWE-016]"),
        L("3.3.2 The project manager shall track progress."),
        L("3.3.1 SWE-016 The project manager shall document a schedule.", page=60),
    ]
    assert [c.clause_id for c in chunk_section_aware(lines)] == ["3.3.1", "3.3.2", "3.3.1"]


def test_non_bold_title_followed_by_its_sub_clause_acts_as_a_heading():
    # Table section rows in NASA-STD-8739.8B Table 1 are not bold.
    lines = [
        L("4.3 Requirements", bold=True),
        L("The applicable requirements are defined in Table 1."),
        L("3.1 Software Life Cycle Planning"),
        L("3.1.2 033"),
        L("The project manager shall assess options."),
        L("3.1.3 013"),
        L("The project manager shall develop software plans."),
    ]
    chunks = chunk_section_aware(lines)

    assert [c.clause_id for c in chunks] == ["4.3", "3.1.2", "3.1.3"]
    assert chunks[1].parent_heading == "3.1 Software Life Cycle Planning"
    assert chunks[2].parent_heading == "3.1 Software Life Cycle Planning"


# ---------------------------------------------------------------- section-aware: look-alikes


def test_numbered_list_items_are_not_headings():
    # The trap found in NASA-STD-8739.8B: 475 lines look like "1. Confirm that ...".
    # Only bold lines may be outline headings.
    lines = [
        L("4.3 Software Assurance Requirements", bold=True),
        L("The project manager shall ensure the following:"),
        L("1. Confirm that the options have been evaluated."),
        L("2. Confirm the flow down of applicable requirements."),
        L("a. Acquire an off-the-shelf software product."),
    ]
    (chunk,) = chunk_section_aware(lines)
    assert chunk.clause_id == "4.3"
    assert "2. Confirm the flow down" in chunk.content


def test_document_numbers_and_wrapped_references_are_not_headings():
    lines = [
        L("2.1 Applicable Documents", bold=True),
        L("NPR"),
        L("7150.2 NASA Software Engineering Requirements"),  # component > 2 digits
        L("See Table 1,"),
        L("3.7.1 of this document for more details."),  # lowercase continuation
        L("5.1.9 (“Software configuration management planning”), clause 6"),  # wrapped ref
        L("specific version levels (such as"),
        L("4.1, 5.0, etc.) and a complete list of any patches."),
    ]
    chunks = chunk_section_aware(lines)
    assert [c.clause_id for c in chunks] == ["2.1"]


# ---------------------------------------------------------------- section-aware: FDA outline

# Modelled on the FDA guidance documents: I. / A. / 1. or (1), headings are bold.
FDA_LINES = [
    L("IV. OTS Software in Marketing Applications", bold=True),
    L("This section describes the documentation to provide."),
    L("A. Master Files for Devices (MAFs)", bold=True),
    L("An OTS software vendor may submit a device master file."),
    L("B. OTS Software Changes requiring a 510(k)", bold=True),
    L("For medical devices where the OTS software represents a minor level of concern."),
    L("(1) Basic Documentation Level", bold=True),
    L("A summary of the configuration management plan."),
    L("V. Additional Information", bold=True),
    L("See the references."),
    L("A. References", bold=True),
    L("FDA guidance documents are listed here."),
]


def test_outline_headings_build_hierarchical_clause_ids():
    chunks = chunk_section_aware(FDA_LINES)
    assert [c.clause_id for c in chunks] == ["IV", "IV.A", "IV.B", "IV.B.1", "V", "V.A"]
    assert chunks[3].parent_heading == "(1) Basic Documentation Level"


def test_outline_letter_i_after_h_is_a_letter_not_a_roman_numeral():
    lines = [L("II. Scope", bold=True), L("Text.")]
    for letter in "ABCDEFGHIJ":
        lines += [L(f"{letter}. Topic {letter}", bold=True), L(f"Body of {letter}.")]
    ids = [c.clause_id for c in chunk_section_aware(lines)]
    assert ids == ["II"] + [f"II.{letter}" for letter in "ABCDEFGHIJ"]


# ---------------------------------------------------------------- oversized sections


def _long_section(n_sentences: int) -> list[Line]:
    body = [
        L(f"Sentence number {i} of the requirement text goes here.") for i in range(n_sentences)
    ]
    return [L("5.1 A Very Long Clause", bold=True), *body]


def test_oversized_section_is_split_and_every_piece_keeps_the_clause_id():
    chunks = chunk_section_aware(_long_section(120), max_chars=800, overlap_chars=100)

    assert len(chunks) > 1
    assert all(c.clause_id == "5.1" for c in chunks)
    assert all(c.parent_heading == "5.1 A Very Long Clause" for c in chunks)
    assert all(len(c.content) <= 800 for c in chunks)


def test_overlap_is_a_real_suffix_of_the_previous_chunk_and_bounded():
    chunks = chunk_section_aware(_long_section(120), max_chars=800, overlap_chars=100)

    for prev, cur in zip(chunks, chunks[1:], strict=False):
        overlap = _common_overlap(prev.content, cur.content)
        assert 0 < len(overlap) <= 100


def test_nothing_lost_when_overlaps_are_removed():
    lines = _long_section(120)
    chunks = chunk_section_aware(lines, max_chars=800, overlap_chars=100)

    rebuilt = chunks[0].content
    for prev, cur in zip(chunks, chunks[1:], strict=False):
        rebuilt += cur.content[len(_common_overlap(prev.content, cur.content)) :]
    assert rebuilt == "\n".join(line.text for line in lines)


def test_small_document_loses_nothing():
    chunks = chunk_section_aware(NPR_LINES)
    produced = "\n".join(c.content for c in chunks)
    for line in NPR_LINES[1:]:  # all but the heading-only line, which lives on in metadata
        assert line.text in produced


def test_section_aware_empty_document():
    assert chunk_section_aware([]) == []


def _common_overlap(prev: str, cur: str) -> str:
    """Longest string that is both a suffix of `prev` and a prefix of `cur`."""
    for size in range(min(len(prev), len(cur)), 0, -1):
        if prev.endswith(cur[:size]):
            return cur[:size]
    return ""


# ---------------------------------------------------------------- recursive splitter


def test_split_recursive_is_lossless_and_bounded():
    text = "\n".join(f"Paragraph {i}. It has two sentences. " + "word " * 30 for i in range(40))
    pieces = split_recursive(text, max_chars=300)
    assert "".join(pieces) == text
    assert all(0 < len(p) <= 300 for p in pieces)


def test_split_recursive_prefers_line_then_sentence_then_word_boundaries():
    text = "First line here.\nSecond line here.\nThird line here."
    assert split_recursive(text, max_chars=20) == [
        "First line here.\n",
        "Second line here.\n",
        "Third line here.",
    ]
    # One line too long for the limit: fall back to sentence boundaries.
    assert split_recursive("Aaa bbb. Ccc ddd. Eee fff.", max_chars=10) == [
        "Aaa bbb. ",
        "Ccc ddd. ",
        "Eee fff.",
    ]


def test_split_recursive_hard_cuts_a_single_giant_token():
    pieces = split_recursive("x" * 25, max_chars=10)
    assert pieces == ["x" * 10, "x" * 10, "x" * 5]


def test_split_recursive_short_text_is_untouched():
    assert split_recursive("short", max_chars=100) == ["short"]
