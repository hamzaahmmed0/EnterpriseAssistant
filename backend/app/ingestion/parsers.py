"""PDF and DOCX text extraction, plus cleanup of extraction artifacts.

Page numbers survive parsing: the ground-truth Q&A set labels expected sources as
(document_id, page), so a parser that loses page boundaries makes recall@5 unmeasurable.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class ParsedPage:
    """One page of extracted text."""

    page: int
    text: str


def parse_document(path: str) -> list[ParsedPage]:
    """Extract text page by page from a PDF or DOCX file.

    Args:
        path: Path to the source document.

    Raises:
        UnsupportedFormatError: If the extension is neither .pdf nor .docx.
    """
    raise NotImplementedError


def parse_pdf(path: str) -> list[ParsedPage]:
    """Extract per-page text from a PDF."""
    raise NotImplementedError


def parse_docx(path: str) -> list[ParsedPage]:
    """Extract text from a DOCX, synthesising page numbers where the format has none."""
    raise NotImplementedError


def clean_text(text: str) -> str:
    """Remove headers, footers, and extraction artifacts; normalise whitespace and encoding."""
    raise NotImplementedError


class UnsupportedFormatError(Exception):
    """Raised for a file type the ingestion pipeline does not handle."""


# TODO:
#  1. Implement parse_pdf() with pypdf, one ParsedPage per physical page.
#  2. Decide how DOCX pagination maps to page numbers (DOCX has no fixed pages) and document the
#     rule -- the eval labels depend on it being stable. Section index is an acceptable answer.
#  3. Implement clean_text(): collapse whitespace, strip repeated header/footer lines that occur
#     on every page, normalise unicode.
#  4. Test clean_text against a real extracted page from the synthetic corpus, not a synthetic
#     string -- artifacts are the point.
#  5. Log and skip zero-text pages rather than emitting empty chunks.
