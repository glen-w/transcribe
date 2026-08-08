"""Build page_v1 AnalysisDocument from a managed project."""

from __future__ import annotations

from transcribe.analysis import ADAPTER_VERSION
from transcribe.analysis.document import (
    GRANULARITY_PAGE_V1,
    SPLIT_PAGE,
    AnalysisDocument,
    AnalysisDocumentError,
    AnalysisUnit,
    concatenate_document_text,
    is_whitespace_only,
    validate_analysis_document,
)
from transcribe.domain.models import PageIndex, Project
from transcribe.services.project import ProjectService


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


__all__ = ["ADAPTER_VERSION", "build_page_v1_document"]
