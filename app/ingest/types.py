"""Data passed between the ingestion stages: parser -> chunker -> (embedder -> storage)."""

from dataclasses import dataclass
from typing import Literal

Strategy = Literal["naive", "section_aware"]


@dataclass(frozen=True)
class Line:
    """One visual line of a PDF page, after the parser has cleaned it up."""

    text: str
    page: int  # 1-based, as a human would cite it
    bold: bool = False


@dataclass(frozen=True)
class ParsedDocument:
    title: str
    page_count: int
    lines: list[Line]


@dataclass(frozen=True)
class Chunk:
    """One retrievable unit. `document` is added at storage time (it's the DB row's ID)."""

    content: str
    page: int  # page where the chunk starts
    strategy: Strategy
    chunk_index: int  # position within (document, strategy)
    clause_id: str | None = None  # e.g. "3.1.2", "VI.C", "Appendix A"; None for naive
    parent_heading: str | None = None  # nearest titled heading at or above this clause
