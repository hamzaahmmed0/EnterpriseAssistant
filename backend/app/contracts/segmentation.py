"""Clause-level segmentation of uploaded contracts (ADR-009).

Structure-first (headings and numbering), with an LLM classification fallback for documents the
structural pass cannot segment. Segmentation quality is reported separately in
docs/EVALUATION.md, because verdict accuracy over badly segmented input means nothing.

The fallback triggers when the structural pass yields fewer than two clauses, or when any single
structural clause exceeds ``settings.segmentation_max_clause_chars`` -- the second condition
catches the common failure where one heading matches and the rest of the contract lands in a
single blob.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from app.config import get_settings
from app.generation import prompts
from app.generation.llm import LLMError, complete_json
from app.ingestion.parsers import ParsedPage
from app.observability import log_error

#: Heading patterns the structural pass recognises. Anchored to line starts.
_HEADING_PATTERNS = (
    re.compile(r"^(?P<num>\d{1,2}\.\d{1,2}(?:\.\d{1,2})?)\s+(?P<title>\S.*)$"),  # 4.2 Payment
    re.compile(r"^(?P<num>\d{1,2}\.)\s+(?P<title>\S.*)$"),  # 4. Payment
    re.compile(r"^(?P<num>ARTICLE\s+[IVXLC\d]+)\.?\s*(?P<title>.*)$", re.IGNORECASE),
    re.compile(r"^(?P<num>SECTION\s+[\dIVXLC]+)\.?\s*(?P<title>.*)$", re.IGNORECASE),
)

STRUCTURAL = "structural"
LLM_FALLBACK = "llm_fallback"


@dataclass(frozen=True)
class Clause:
    """One segmented contract clause."""

    clause_index: int
    heading: str
    text: str
    page: int
    segmentation_path: str


def _match_heading(line: str) -> str | None:
    """Return the normalised heading if this line starts a clause, else None."""
    stripped = line.strip()
    if not stripped or len(stripped) > 200:
        return None
    for pattern in _HEADING_PATTERNS:
        match = pattern.match(stripped)
        if match:
            title = (match.group("title") or "").strip()
            number = match.group("num").strip()
            return f"{number} {title}".strip()
    return None


def segment_structural(text_by_page: list[tuple[int, str]]) -> list[Clause]:
    """Segment on numbered headings. Returns an empty list when no structure is found.

    A clause crossing a page boundary reports the page where it starts (ADR-012).
    """
    headings: list[tuple[str, int]] = []
    bodies: list[list[str]] = []
    preamble: list[str] = []

    for page_number, page_text in text_by_page:
        for line in page_text.splitlines():
            heading = _match_heading(line)
            if heading is not None:
                headings.append((heading, page_number))
                bodies.append([])
            elif headings:
                bodies[-1].append(line)
            else:
                preamble.append(line)

    clauses: list[Clause] = []
    for index, ((heading, page), body) in enumerate(zip(headings, bodies, strict=True)):
        text = "\n".join([heading, *body]).strip()
        if text:
            clauses.append(
                Clause(
                    clause_index=index,
                    heading=heading,
                    text=text,
                    page=page,
                    segmentation_path=STRUCTURAL,
                )
            )
    return clauses


def should_use_fallback(structural_clauses: list[Clause]) -> bool:
    """Decide whether the structural result is good enough to keep (ADR-009)."""
    if len(structural_clauses) < 2:
        return True
    limit = get_settings().segmentation_max_clause_chars
    return any(len(clause.text) > limit for clause in structural_clauses)


def segment_with_llm(text_by_page: list[tuple[int, str]]) -> list[Clause]:
    """Segment via LLM classification, for contracts without usable structure.

    A single bounded pass -- no retry loop here; an unbounded repair loop is the same bug as an
    unbounded retrieval loop.
    """
    joined = "\n\n".join(text for _, text in text_by_page).strip()
    first_page = text_by_page[0][0] if text_by_page else 1
    if not joined:
        return []

    try:
        reply = complete_json(
            prompts.segmentation_prompt(joined),
            prompts.segmentation_system_prompt(),
            purpose="segment",
        )
    except LLMError as exc:
        log_error("segmentation_fallback_failed", error=str(exc))
        return []

    clauses: list[Clause] = []
    for index, item in enumerate(reply.get("clauses", []) or []):
        text = str(item.get("text", "")).strip()
        if not text:
            continue
        clauses.append(
            Clause(
                clause_index=index,
                heading=str(item.get("heading", "")).strip(),
                text=text,
                page=_page_for_text(text_by_page, text, default=first_page),
                segmentation_path=LLM_FALLBACK,
            )
        )
    return clauses


def _page_for_text(text_by_page: list[tuple[int, str]], clause_text: str, default: int) -> int:
    """Locate the page a fallback-produced clause starts on, by matching its opening line."""
    probe = clause_text.strip().splitlines()[0][:60] if clause_text.strip() else ""
    if probe:
        for page_number, page_text in text_by_page:
            if probe in page_text:
                return page_number
    return default


def segment_contract(text_by_page: list[tuple[int, str]]) -> list[Clause]:
    """Segment a parsed contract into clauses, choosing the structural or fallback path.

    Args:
        text_by_page: ``(page_number, cleaned_text)`` in document order.

    Returns:
        Clauses in document order. An empty or unparseable contract returns an empty list rather
        than raising -- that is a reportable result, not a crash.
    """
    if not text_by_page:
        return []

    structural = segment_structural(text_by_page)
    if not should_use_fallback(structural):
        return structural

    fallback = segment_with_llm(text_by_page)
    if fallback:
        return fallback

    # The fallback failed too. Return whatever structure we found rather than nothing, so the
    # reviewer can still produce Needs Legal Review verdicts a human can act on.
    return structural


def pages_from_parsed(pages: list[ParsedPage]) -> list[tuple[int, str]]:
    """Adapt parser output to the (page, text) pairs this module works in."""
    return [(page.page, page.text) for page in pages]
