"""Build AnalysisDocument adapters from a managed project."""

from __future__ import annotations

import re

from transcribe.analysis import ADAPTER_VERSION
from transcribe.analysis.document import (
    GRANULARITY_PAGE_V1,
    GRANULARITY_PARAGRAPH_V1,
    SPLIT_PAGE,
    SPLIT_PARAGRAPH_V1,
    AnalysisDocument,
    AnalysisDocumentError,
    AnalysisUnit,
    concatenate_document_text,
    is_whitespace_only,
    validate_analysis_document,
)
from transcribe.domain.models import PageIndex, Project
from transcribe.services.project import ProjectService

_BLANK_LINE_SPLIT = re.compile(r"\n{2,}")


def _unit_date(page: PageIndex) -> str | None:
    d = page.date
    if d is None or d.day is None or d.month is None:
        return None
    return f"{d.year:04d}-{d.month:02d}-{d.day:02d}"


def build_page_v1_document(
    project: Project,
    project_service: ProjectService,
) -> AnalysisDocument:
    """Canonical page_v1 adapter. Raises AnalysisDocumentError if empty after omission."""
    units: list[AnalysisUnit] = []
    emitted_order = 0
    for page in project.pages:
        if page.analysis_excluded:
            continue
        result = project_service.load_page_result(page.page_id)
        text = result.effective_text() if result else None
        if text is None or is_whitespace_only(text):
            continue
        units.append(
            AnalysisUnit(
                unit_id=page.page_id,
                text=text,
                order=float(emitted_order),
                date=_unit_date(page),
                source_ref={"kind": "page", "page_id": page.page_id},
            )
        )
        emitted_order += 1

    doc = AnalysisDocument(
        document_id=project.id,
        text=concatenate_document_text(units),
        units=units,
        granularity_version=GRANULARITY_PAGE_V1,
        split_profile=SPLIT_PAGE,
    )
    if not units:
        raise AnalysisDocumentError(
            "empty_document_text", "no analysis units after page_v1 omission"
        )
    return validate_analysis_document(doc)


def _paragraph_spans(text: str) -> list[tuple[int, int]]:
    """Blank-line split → half-open spans into ``text`` (analysis-document contract)."""
    if not text:
        return []
    spans: list[tuple[int, int]] = []
    last = 0
    for match in _BLANK_LINE_SPLIT.finditer(text):
        start, end = last, match.start()
        last = match.end()
        if start < end and not is_whitespace_only(text[start:end]):
            spans.append((start, end))
    if last < len(text) and not is_whitespace_only(text[last:]):
        spans.append((last, len(text)))
    if not spans and not is_whitespace_only(text):
        spans.append((0, len(text)))
    return spans


def build_paragraph_v1_document(
    project: Project,
    project_service: ProjectService,
) -> AnalysisDocument:
    """paragraph_v1 adapter with stable ``page_id/span:start-end`` unit ids."""
    units: list[AnalysisUnit] = []
    page_order = 0
    for page in project.pages:
        if page.analysis_excluded:
            continue
        result = project_service.load_page_result(page.page_id)
        text = result.effective_text() if result else None
        if text is None or is_whitespace_only(text):
            continue
        for start, end in _paragraph_spans(text):
            block = text[start:end]
            if is_whitespace_only(block):
                continue
            units.append(
                AnalysisUnit(
                    unit_id=f"{page.page_id}/span:{start}-{end}",
                    text=block,
                    order=float(page_order * 1_000_000 + start),
                    date=_unit_date(page),
                    source_ref={
                        "kind": "page_span",
                        "page_id": page.page_id,
                        "char_start": start,
                        "char_end": end,
                    },
                )
            )
        page_order += 1

    doc = AnalysisDocument(
        document_id=project.id,
        text=concatenate_document_text(units),
        units=units,
        granularity_version=GRANULARITY_PARAGRAPH_V1,
        split_profile=SPLIT_PARAGRAPH_V1,
    )
    if not units:
        raise AnalysisDocumentError(
            "empty_document_text", "no analysis units after paragraph_v1 omission"
        )
    return validate_analysis_document(doc)


__all__ = [
    "ADAPTER_VERSION",
    "build_page_v1_document",
    "build_paragraph_v1_document",
]
