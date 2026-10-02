"""Parser tests. Each builds a tiny PDF in a temp folder, so no corpus file is needed."""

from pathlib import Path

import pymupdf
import pytest

from app.errors import IngestError
from app.ingest.parser import _line_text, parse_pdf

REGULAR, BOLD = "helv", "hebo"  # built-in Helvetica / Helvetica-Bold


def _make_pdf(
    path: Path, pages: list[list[tuple[float, float, str, str]]], title: str = ""
) -> Path:
    """pages[i] = list of (x, y, text, fontname) to draw on page i."""
    doc = pymupdf.open()
    for items in pages:
        page = doc.new_page(width=612, height=792)
        for x, y, text, font in items:
            page.insert_text((x, y), text, fontname=font, fontsize=12)
    if title:
        doc.set_metadata({"title": title})
    doc.save(path)
    doc.close()
    return path


def test_extracts_lines_with_page_numbers_and_bold_flag(tmp_path):
    pdf = _make_pdf(
        tmp_path / "doc.pdf",
        [
            [
                (72, 100, "4.2 Safety-Critical Software", BOLD),
                (72, 130, "Body text here.", REGULAR),
            ],
            [(72, 100, "Second page text.", REGULAR)],
        ],
    )
    parsed = parse_pdf(pdf)

    assert parsed.page_count == 2
    assert [(line.text, line.page, line.bold) for line in parsed.lines] == [
        ("4.2 Safety-Critical Software", 1, True),
        ("Body text here.", 1, False),
        ("Second page text.", 2, False),
    ]


def test_title_comes_from_metadata_else_from_the_filename(tmp_path):
    page = [[(72, 100, "text", REGULAR)]]
    with_meta = _make_pdf(tmp_path / "a.pdf", page, title="Off-the-Shelf Software Use")
    without = _make_pdf(tmp_path / "NPR-7150.2D.pdf", page)

    assert parse_pdf(with_meta).title == "Off-the-Shelf Software Use"
    assert parse_pdf(without).title == "NPR-7150.2D"


def test_joins_a_clause_number_stored_separately_from_its_text(tmp_path):
    # As in NASA-STD-8739.8B: the number at x=81 and the text at x=135, same row.
    pdf = _make_pdf(
        tmp_path / "doc.pdf",
        [
            [
                (81, 100, "4.4.2.9", REGULAR),
                (135, 100, "The IV&V provider shall assess results.", REGULAR),
                (81, 114, "performance against the software plans.", REGULAR),
                (72, 200, "2.", BOLD),
                (117, 200, "APPLICABLE DOCUMENTS", BOLD),
            ]
        ],
    )
    lines = parse_pdf(pdf).lines

    assert [line.text for line in lines] == [
        "4.4.2.9 The IV&V provider shall assess results.",
        "performance against the software plans.",
        "2. APPLICABLE DOCUMENTS",
    ]
    assert [line.bold for line in lines] == [False, False, True]


def test_joins_outline_markers_and_bullets_to_the_text_on_their_row(tmp_path):
    # As in the FDA Premarket guidance: "I." and "Introduction" are separate lines.
    pdf = _make_pdf(
        tmp_path / "doc.pdf",
        [
            [
                (72, 100, "I.", BOLD),
                (108, 100, "Introduction", BOLD),
                (72, 130, "o", REGULAR),
                (90, 130, "first bullet item", REGULAR),
                (72, 160, "(a)", REGULAR),
                (108, 160, "A set of activities", REGULAR),
            ]
        ],
    )
    lines = parse_pdf(pdf).lines
    assert [(line.text, line.bold) for line in lines] == [
        ("I. Introduction", True),
        ("o first bullet item", False),
        ("(a) A set of activities", False),
    ]


def test_does_not_join_a_bare_number_or_lines_on_different_rows(tmp_path):
    pdf = _make_pdf(
        tmp_path / "doc.pdf",
        [
            [
                (72, 100, "3", REGULAR),  # a table cell or page number, not a clause
                (117, 100, "Software Management", REGULAR),
                (72, 200, "4.1", REGULAR),  # next line is on a different row
                (72, 230, "Unrelated paragraph.", REGULAR),
            ]
        ],
    )
    assert [line.text for line in parse_pdf(pdf).lines] == [
        "3",
        "Software Management",
        "4.1",
        "Unrelated paragraph.",
    ]


def test_removes_running_headers_and_footers_but_keeps_body_numbers(tmp_path):
    pages = [
        [
            (245, 40, "NASA-STD-8739.8B", BOLD),  # header, identical on every page
            (72, 300, f"Body of page {n}.", REGULAR),
            (72, 330, "033", REGULAR),  # a number in the body must survive
            (286, 760, f"{n} of 6", REGULAR),  # footer, differs only by digits
        ]
        for n in range(1, 7)
    ]
    lines = parse_pdf(_make_pdf(tmp_path / "doc.pdf", pages)).lines

    texts = [line.text for line in lines]
    assert "NASA-STD-8739.8B" not in texts
    assert not any("of 6" in t for t in texts)
    assert texts.count("033") == 6
    assert texts[0] == "Body of page 1."


def test_short_documents_keep_their_margin_lines(tmp_path):
    # With 2 pages we can't tell a running header from real content: keep everything.
    pages = [[(72, 40, "Cover line", REGULAR), (72, 300, "Body.", REGULAR)] for _ in range(2)]
    texts = [line.text for line in parse_pdf(_make_pdf(tmp_path / "doc.pdf", pages)).lines]
    assert texts.count("Cover line") == 2


def test_collapses_repeated_spaces(tmp_path):
    pdf = _make_pdf(tmp_path / "doc.pdf", [[(72, 100, "2.   What  are the specs?", BOLD)]])
    assert parse_pdf(pdf).lines[0].text == "2. What are the specs?"


def test_line_text_keeps_the_space_stored_as_its_own_span():
    # Regression (docs/BUGS.md, 2026-10-02): FDA headings are stored as "III." + " " + "Scope".
    spans = [{"text": "III."}, {"text": " "}, {"text": "Scope "}]
    assert _line_text(spans) == "III. Scope"


def test_line_text_removes_soft_hyphens_and_non_breaking_spaces():
    assert _line_text([{"text": "Information ­ Regulatory  Use"}]) == ("Information Regulatory Use")


def test_a_file_that_is_not_a_pdf_raises_ingest_error(tmp_path):
    fake = tmp_path / "notes.pdf"
    fake.write_text("this is not a pdf")
    with pytest.raises(IngestError, match="not a readable PDF"):
        parse_pdf(fake)


def test_a_pdf_without_text_raises_ingest_error(tmp_path):
    blank = _make_pdf(tmp_path / "scan.pdf", [[]])
    with pytest.raises(IngestError, match="no extractable text"):
        parse_pdf(blank)
