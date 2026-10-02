"""Chunking strategies: turn a document's lines into retrievable chunks.

Two strategies are kept on purpose, because the evaluation compares them:
  - naive:          fixed-size character windows, blind to structure (the baseline)
  - section_aware:  one chunk per numbered clause, carrying clause ID and heading

Pure functions on plain data: no I/O, no PDF library. That keeps them fast to test.
"""

import re
from bisect import bisect_right
from collections import Counter
from dataclasses import dataclass, field

from app.ingest.types import Chunk, Line

NAIVE_WINDOW_CHARS = 512
# No tokenizer in the stack: approximate 1 token ~= 4 characters of English text.
CHARS_PER_TOKEN = 4
SECTION_MAX_CHARS = 800 * CHARS_PER_TOKEN
SECTION_OVERLAP_CHARS = 100 * CHARS_PER_TOKEN


# =============================================================== naive


def chunk_naive(lines: list[Line], window: int = NAIVE_WINDOW_CHARS) -> list[Chunk]:
    """Cut the whole text every `window` characters. May split mid-word, mid-clause, mid-table."""
    text, page_at = _join_lines(lines)
    return [
        Chunk(
            content=text[start : start + window],
            page=page_at(start),
            strategy="naive",
            chunk_index=index,
        )
        for index, start in enumerate(range(0, len(text), window))
    ]


def _join_lines(lines: list[Line]):
    """Join lines with newlines; also return a function mapping a char offset to its page."""
    text = "\n".join(line.text for line in lines)
    starts: list[int] = []  # starts[i] = offset in `text` where lines[i] begins
    offset = 0
    for line in lines:
        starts.append(offset)
        offset += len(line.text) + 1  # +1 for the "\n"

    def page_at(char_offset: int) -> int:
        # bisect_right finds the last line that starts at or before the offset: O(log n).
        return lines[bisect_right(starts, char_offset) - 1].page

    return text, page_at


# =============================================================== section-aware: headings

# Decimal clause numbers: "3.1.2", "4.4.2.13", appendix style "C.1", preface style "P.3".
# - at least two components, so a bare "3" or "1." never matches here
# - each component at most 2 digits, so document numbers like "7150.2" don't match
# - must be followed by an uppercase letter or a digit: wrapped references such as
#   "3.7.1 of this document" or "5.1.9 (see ...)" are rejected
_DECIMAL = re.compile(r"^((?:\d{1,2}|[A-Z])(?:\.\d{1,2}){1,5})\.?\s+(?=[A-Z0-9])")

# Outline markers. These look exactly like list items ("1. Confirm that ..."), so they
# count as headings only when the line is bold.
_APPENDIX = re.compile(r"^(Appendix|Annex|Chapter)\s+([A-Z]|\d{1,2})\b", re.IGNORECASE)
_ROMAN = re.compile(r"^([IVX]{1,5})\.\s+\S")
_LETTER = re.compile(r"^([A-Z])\.\s+\S")
_NUMBER = re.compile(r"^(?:(\d{1,2})\.|\((\d{1,2})\))\s+\S")

_MAX_TITLE_CONTINUATION_LINES = 2


@dataclass
class _Section:
    clause_id: str | None
    heading: str | None  # nearest titled heading at or above this clause
    lines: list[Line] = field(default_factory=list)
    title_line_count: int = 0  # >0 when the section starts with its own bold title

    @property
    def is_heading_only(self) -> bool:
        return self.title_line_count > 0 and len(self.lines) == self.title_line_count


class _Outline:
    """Tracks where we are in an I. / A. / 1. outline to build IDs like "IV.B.1"."""

    def __init__(self) -> None:
        self._levels: list[str | None] = [None, None, None]  # roman, letter, number

    def enter(self, level: int, token: str) -> str:
        self._levels[level] = token
        for deeper in range(level + 1, len(self._levels)):
            self._levels[deeper] = None  # a new "B." ends the previous "(1)", "(2)", ...
        return ".".join(part for part in self._levels[: level + 1] if part)

    def detect(self, text: str) -> str | None:
        """Return the clause ID if `text` (already known to be bold) is an outline heading."""
        if match := _APPENDIX.match(text):
            return self.enter(0, f"{match[1].capitalize()} {match[2]}")
        if (match := _LETTER.match(text)) and self._continues_letter_sequence(match[1]):
            return self.enter(1, match[1])
        if match := _ROMAN.match(text):
            return self.enter(0, match[1])
        if match := _LETTER.match(text):
            return self.enter(1, match[1])
        if match := _NUMBER.match(text):
            return self.enter(2, match[1] or match[2])
        return None

    def _continues_letter_sequence(self, letter: str) -> bool:
        # "I.", "V." and "X." are ambiguous: roman numeral or letter? They are letters
        # only when they directly follow the previous letter of the alphabet (H. -> I.).
        previous = self._levels[1]
        return previous is not None and ord(letter) == ord(previous) + 1


def _split_into_sections(lines: list[Line]) -> list[_Section]:
    sections: list[_Section] = []
    current = _Section(clause_id=None, heading=None)  # text before the first heading
    outline = _Outline()
    last_title: str | None = None
    title_lines_left = 0

    for line in lines:
        decimal = _DECIMAL.match(line.text)
        clause_id = decimal[1] if decimal else (outline.detect(line.text) if line.bold else None)

        if clause_id is None:
            if title_lines_left and line.bold and line.page == current.lines[-1].page:
                # A bold line right after a bold heading is the wrapped rest of its title.
                last_title = f"{last_title} {line.text}"
                current.heading = last_title
                current.title_line_count += 1
                title_lines_left -= 1
            else:
                title_lines_left = 0
            current.lines.append(line)
            continue

        sections.append(current)
        if line.bold:  # a titled heading: "3.1 Software Life Cycle Planning"
            last_title = line.text
            current = _Section(clause_id, heading=last_title, lines=[line], title_line_count=1)
            title_lines_left = _MAX_TITLE_CONTINUATION_LINES
        else:  # a numbered paragraph: "3.1.2 The project manager shall ..."
            current = _Section(clause_id, heading=last_title, lines=[line])
            title_lines_left = 0

    sections.append(current)
    sections = _demote_contents_entries([s for s in sections if s.lines])
    _promote_untitled_headings(sections)
    return [s for s in sections if not s.is_heading_only]


def _is_bare_title(section: _Section) -> bool:
    """One non-bold line that reads like a title, not a sentence: "3.1 Software Planning"."""
    if section.clause_id is None or section.title_line_count or len(section.lines) != 1:
        return False
    return not section.lines[0].text.endswith((".", "]", ":", ";", ")"))


def _demote_contents_entries(sections: list[_Section]) -> list[_Section]:
    """A bare title whose clause ID shows up again later is a table-of-contents entry.

    It is not a clause, so it gets no chunk of its own: its line is appended to the
    section before it (nothing is lost).
    """
    remaining = Counter(s.clause_id for s in sections)
    kept: list[_Section] = []
    for section in sections:
        remaining[section.clause_id] -= 1
        if kept and _is_bare_title(section) and remaining[section.clause_id] > 0:
            kept[-1].lines.extend(section.lines)
        else:
            kept.append(section)
    return kept


def _promote_untitled_headings(sections: list[_Section]) -> None:
    """A bare title directly followed by its own sub-clause is a heading that isn't bold.

    Seen in table section rows: "3.1 Software Life Cycle Planning" then "3.1.2 ...".
    Treat it like a bold heading: no chunk of its own, and its sub-clauses cite it.
    """
    for i, section in enumerate(sections[:-1]):
        if not _is_bare_title(section):
            continue
        child_prefix = f"{section.clause_id}."
        if not (sections[i + 1].clause_id or "").startswith(child_prefix):
            continue
        inherited, title = section.heading, section.lines[0].text
        section.heading = title
        section.title_line_count = 1  # now heading-only, so it is filtered out
        for later in sections[i + 1 :]:
            if not (later.clause_id or "").startswith(child_prefix):
                break
            if later.heading == inherited:
                later.heading = title


# =============================================================== section-aware: chunks


def chunk_section_aware(
    lines: list[Line],
    max_chars: int = SECTION_MAX_CHARS,
    overlap_chars: int = SECTION_OVERLAP_CHARS,
) -> list[Chunk]:
    """One chunk per clause; clauses longer than `max_chars` are split with overlap."""
    chunks: list[Chunk] = []
    for section in _split_into_sections(lines):
        text, page_at = _join_lines(section.lines)
        # Reserve room for the overlap so that overlap + piece never exceeds max_chars.
        pieces = split_recursive(text, max_chars - overlap_chars)

        offset = 0
        previous = ""
        for piece in pieces:
            chunks.append(
                Chunk(
                    content=_overlap_tail(previous, overlap_chars) + piece,
                    page=page_at(offset),
                    strategy="section_aware",
                    chunk_index=len(chunks),
                    clause_id=section.clause_id,
                    parent_heading=section.heading,
                )
            )
            offset += len(piece)
            previous = piece
    return chunks


def _overlap_tail(previous: str, overlap_chars: int) -> str:
    """The last <= overlap_chars of the previous piece, starting on a word boundary."""
    if not previous or overlap_chars <= 0:
        return ""
    tail = previous[-overlap_chars:]
    if len(tail) < len(previous):  # we cut into the piece: don't start mid-word
        first_space = re.search(r"\s", tail)
        if first_space and first_space.end() < len(tail):
            tail = tail[first_space.end() :]
    return tail


_SEPARATORS = ("\n", ". ", " ")  # line, then sentence, then word


def split_recursive(text: str, max_chars: int) -> list[str]:
    """Split `text` into pieces of at most `max_chars`; "".join(pieces) == text.

    Tries the coarsest boundary first (lines), and only falls back to finer ones
    (sentences, words, finally a hard cut) for a part that is still too long.
    """
    if len(text) <= max_chars:
        return [text] if text else []

    for separator in _SEPARATORS:
        parts = _split_keeping_separator(text, separator)
        if len(parts) == 1:
            continue  # this separator doesn't occur; try a finer one
        small_enough: list[str] = []
        for part in parts:
            small_enough.extend(split_recursive(part, max_chars))
        return _pack(small_enough, max_chars)

    # No boundary at all (one giant token): hard cut.
    return [text[i : i + max_chars] for i in range(0, len(text), max_chars)]


def _split_keeping_separator(text: str, separator: str) -> list[str]:
    """Like str.split, but each part keeps its trailing separator, so nothing is lost."""
    parts = text.split(separator)
    with_separator = [part + separator for part in parts[:-1]] + [parts[-1]]
    return [part for part in with_separator if part]


def _pack(pieces: list[str], max_chars: int) -> list[str]:
    """Greedily merge neighbouring pieces while they still fit in `max_chars`."""
    packed: list[str] = []
    for piece in pieces:
        if packed and len(packed[-1]) + len(piece) <= max_chars:
            packed[-1] += piece
        else:
            packed.append(piece)
    return packed
