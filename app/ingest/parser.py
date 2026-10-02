"""PDF -> clean lines. Synchronous and CPU-bound: call it via asyncio.to_thread.

What "clean" means here was decided by looking at the real corpus (see docs/DECISIONS.md):
  1. each line knows whether it is bold (the only way to tell a heading "A. Scope"
     from a list item "a. scope" or "1. Confirm that ...")
  2. running headers/footers ("NASA-STD-8739.8B", "7 of 70") are removed
  3. a marker that the PDF stores separately from its text ("4.4.2.9" and
     "The IV&V provider shall ...", or "I." and "Introduction", or a bullet and its
     item, on the same visual row) is joined back onto it
"""

import re
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

import pymupdf

from app.errors import IngestError
from app.ingest.types import Line, ParsedDocument

_BOLD_FLAG = 1 << 4  # PyMuPDF span flag bit for bold
_MARGIN_FRACTION = 0.10  # top/bottom 10% of the page counts as header/footer zone
_REPEATED_ON_FRACTION = 0.5  # ...and the line must recur on more than half the pages
_MIN_PAGES_FOR_HEADER_DETECTION = 4
_SAME_ROW_TOLERANCE = 3.0  # PDF points; bold and regular fonts sit ~1pt apart

# A line that is nothing but a marker whose text sits to its right on the same row:
#   clause numbers "4.1" "4.4.2.13" "C.1", outline markers "2." "IV." "A." "(1)" "a)",
#   and bullets. A bare "3" is deliberately excluded: usually a page number or table cell.
_MARKER_ONLY = re.compile(
    r"^(?:"
    r"\d{1,2}(?:\.\d{1,2})+\.?"  # 4.1  4.4.2.13
    r"|[A-Z](?:\.\d{1,2})+"  # C.1
    r"|\d{1,2}[.)]"  # 2.  1)
    r"|[IVX]{1,5}\."  # IV.
    r"|[A-Za-z][.)]"  # A.  a)
    r"|\((?:\d{1,2}|[A-Za-z])\)"  # (1)  (a)
    r"|[·•o§▪■◦–-]"  # bullets
    r")$"
)


@dataclass(frozen=True)
class _RawLine:
    text: str
    page: int
    bold: bool
    x: float
    top: float
    bottom: float
    page_height: float


def parse_pdf(path: Path) -> ParsedDocument:
    try:
        doc = pymupdf.open(path)
    except (pymupdf.FileDataError, pymupdf.EmptyFileError, pymupdf.FileNotFoundError) as exc:
        raise IngestError(f"'{path.name}' is not a readable PDF") from exc

    with doc:
        raw = [line for page in doc for line in _page_lines(page)]
        if not raw:
            # Typically a scanned document: pages are images, there is no text layer.
            raise IngestError(f"'{path.name}' contains no extractable text")

        raw = _drop_running_headers_and_footers(raw, doc.page_count)
        raw = _join_markers_to_their_text(raw)
        title = (doc.metadata or {}).get("title", "").strip() or path.stem
        return ParsedDocument(
            title=title,
            page_count=doc.page_count,
            lines=[Line(text=r.text, page=r.page, bold=r.bold) for r in raw],
        )


def _page_lines(page: pymupdf.Page) -> list[_RawLine]:
    lines = []
    # "dict" mode exposes blocks -> lines -> spans; a span is a run of text in one font.
    for block in page.get_text("dict")["blocks"]:
        for line in block.get("lines", []):
            text = _line_text(line["spans"])
            if not text:
                continue
            # Whitespace-only spans carry no font information worth trusting.
            spans = [span for span in line["spans"] if span["text"].strip()]
            x0, y0, _, y1 = line["bbox"]
            lines.append(
                _RawLine(
                    text=text,
                    page=page.number + 1,
                    bold=all(s["flags"] & _BOLD_FLAG or "Bold" in s["font"] for s in spans),
                    x=x0,
                    top=y0,
                    bottom=y1,
                    page_height=page.rect.height,
                )
            )
    return lines


def _line_text(spans: list[dict]) -> str:
    """Join a line's spans into text.

    Every span is joined, including whitespace-only ones: a heading can be stored as
    "III." + " " + "Scope", and dropping the middle span would glue it into "III.Scope".
    split() + join then collapses runs of spaces and non-breaking spaces; "­" is an
    invisible soft hyphen that would otherwise break word matching.
    """
    return " ".join("".join(span["text"] for span in spans).replace("­", "").split())


def _drop_running_headers_and_footers(lines: list[_RawLine], page_count: int) -> list[_RawLine]:
    if page_count < _MIN_PAGES_FOR_HEADER_DETECTION:
        return lines

    def in_margin(line: _RawLine) -> bool:
        return line.top < line.page_height * _MARGIN_FRACTION or line.bottom > line.page_height * (
            1 - _MARGIN_FRACTION
        )

    def key(line: _RawLine) -> str:
        return re.sub(r"\d+", "#", line.text)  # "7 of 70" and "8 of 70" -> "# of #"

    # Count pages (not occurrences) on which each margin line appears.
    pages_seen = Counter(k for k in {(key(line), line.page) for line in lines if in_margin(line)})
    per_key = Counter(k for k, _page in pages_seen)
    repeated = {k for k, n in per_key.items() if n > page_count * _REPEATED_ON_FRACTION}
    return [line for line in lines if not (in_margin(line) and key(line) in repeated)]


def _join_markers_to_their_text(lines: list[_RawLine]) -> list[_RawLine]:
    joined: list[_RawLine] = []
    i = 0
    while i < len(lines):
        line = lines[i]
        nxt = lines[i + 1] if i + 1 < len(lines) else None
        if (
            nxt is not None
            and _MARKER_ONLY.match(line.text)
            and nxt.page == line.page
            and abs(nxt.top - line.top) <= _SAME_ROW_TOLERANCE
            and nxt.x > line.x
        ):
            joined.append(
                _RawLine(
                    text=f"{line.text} {nxt.text}",
                    page=line.page,
                    bold=line.bold and nxt.bold,
                    x=line.x,
                    top=line.top,
                    bottom=line.bottom,
                    page_height=line.page_height,
                )
            )
            i += 2
        else:
            joined.append(line)
            i += 1
    return joined
