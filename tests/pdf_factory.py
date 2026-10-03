"""Builds small PDFs for tests, so no corpus file is needed."""

from pathlib import Path

import pymupdf

REGULAR, BOLD = "helv", "hebo"  # built-in Helvetica / Helvetica-Bold
Item = tuple[float, float, str, str]  # (x, y, text, fontname)


def make_pdf(path: Path, pages: list[list[Item]], title: str = "") -> Path:
    """pages[i] = the items to draw on page i."""
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
