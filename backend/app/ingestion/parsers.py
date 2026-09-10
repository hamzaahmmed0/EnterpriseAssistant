"""PDF and DOCX text extraction, plus cleanup of extraction artifacts.

Page numbers survive parsing: the ground-truth Q&A set labels expected sources as
(document_id, page), so a parser that loses page boundaries makes recall@5 unmeasurable.

DOCX has no fixed pagination, so per ADR-012 this module emits one ParsedPage per top-level
section -- a heading paragraph (Word "Heading 1"/"Heading 2" style, or an explicit page break)
starts a new page. That mapping is stable across runs, which is what the eval labels require.
"""

from __future__ import annotations

import re
import unicodedata
from collections import Counter
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class ParsedPage:
    """One page of extracted text."""

    page: int
    text: str


class UnsupportedFormatError(Exception):
    """Raised for a file type the ingestion pipeline does not handle."""


def parse_document(path: str | Path) -> list[ParsedPage]:
    """Extract text page by page from a PDF or DOCX file, cleaned.

    Args:
        path: Path to the source document.

    Returns:
        Cleaned pages in document order. Pages that extract to nothing are dropped, so a
        14-page PDF with two blank pages yields 12 ParsedPage objects with their original
        page numbers preserved.

    Raises:
        UnsupportedFormatError: If the extension is neither .pdf nor .docx.
        FileNotFoundError: If the path does not exist.
    """
    resolved = Path(path)
    if not resolved.exists():
        raise FileNotFoundError(f"document not found: {resolved}")

    suffix = resolved.suffix.lower()
    if suffix == ".pdf":
        raw_pages = parse_pdf(resolved)
    elif suffix == ".docx":
        raw_pages = parse_docx(resolved)
    else:
        raise UnsupportedFormatError(
            f"unsupported document type {suffix!r}; ingestion handles .pdf and .docx"
        )

    repeated = _repeated_lines(raw_pages)
    cleaned: list[ParsedPage] = []
    for page in raw_pages:
        text = clean_text(page.text, repeated_lines=repeated)
        if text:
            cleaned.append(ParsedPage(page=page.page, text=text))
    return cleaned


def parse_pdf(path: str | Path) -> list[ParsedPage]:
    """Extract per-page text from a PDF. One ParsedPage per physical page, 1-indexed."""
    from pypdf import PdfReader  # imported lazily so unit tests need no PDF stack

    reader = PdfReader(str(path))
    return [
        ParsedPage(page=index, text=(page.extract_text() or ""))
        for index, page in enumerate(reader.pages, start=1)
    ]


def parse_docx(path: str | Path) -> list[ParsedPage]:
    """Extract text from a DOCX, synthesising page numbers per ADR-012.

    A new page starts at a paragraph styled as a heading or containing an explicit page break.
    Numbering is 1-indexed and stable for a given file.
    """
    import docx  # python-docx; imported lazily

    document = docx.Document(str(path))
    pages: list[list[str]] = [[]]

    for paragraph in document.paragraphs:
        style = (paragraph.style.name or "").lower() if paragraph.style else ""
        is_heading = style.startswith("heading") or style == "title"
        has_break = "<w:br" in paragraph._p.xml and 'w:type="page"' in paragraph._p.xml

        if (is_heading or has_break) and pages[-1]:
            pages.append([])
        if paragraph.text.strip():
            pages[-1].append(paragraph.text)

    for table in document.tables:
        rows = [
            " | ".join(cell.text.strip() for cell in row.cells if cell.text.strip())
            for row in table.rows
        ]
        rows = [row for row in rows if row]
        if rows:
            pages[-1].extend(rows)

    return [
        ParsedPage(page=index, text="\n".join(lines))
        for index, lines in enumerate(pages, start=1)
        if lines
    ]


def _repeated_lines(pages: list[ParsedPage], threshold: float = 0.6) -> set[str]:
    """Identify running headers and footers: short lines present on most pages."""
    if len(pages) < 3:
        return set()

    counts: Counter[str] = Counter()
    for page in pages:
        seen = {line.strip() for line in page.text.splitlines() if line.strip()}
        counts.update(line for line in seen if len(line) <= 90)

    cutoff = max(2, int(len(pages) * threshold))
    return {line for line, count in counts.items() if count >= cutoff}


def clean_text(text: str, repeated_lines: set[str] | None = None) -> str:
    """Remove extraction artifacts and normalise whitespace and encoding.

    Args:
        text: Raw extracted page text.
        repeated_lines: Lines occurring on most pages of the document, treated as running
            headers/footers and dropped. Computed by parse_document across the whole file,
            because a header cannot be identified from a single page.
    """
    if not text:
        return ""

    text = unicodedata.normalize("NFKC", text)
    text = text.replace("­", "")  # soft hyphens from justified PDF text
    text = text.replace("﻿", "")

    drop = repeated_lines or set()
    lines: list[str] = []
    for raw_line in text.splitlines():
        line = re.sub(r"[ \t ]+", " ", raw_line).strip()
        if not line or line in drop:
            continue
        if re.fullmatch(r"(page\s*)?\d+(\s*(/|of)\s*\d+)?", line, flags=re.IGNORECASE):
            continue  # bare page numbers
        lines.append(line)

    # Rejoin hyphenated words split across lines, then collapse blank runs.
    joined = "\n".join(lines)
    joined = re.sub(r"(\w)-\n(\w)", r"\1\2", joined)
    return re.sub(r"\n{3,}", "\n\n", joined).strip()
