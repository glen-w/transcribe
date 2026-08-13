"""Review needs-attention queue helpers (usability-wave U3.1)."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from typing import Literal

from transcribe.domain.models import PageResult, Project

ReviewFilter = Literal["all", "needs_date", "no_text", "failed_ocr"]

REVIEW_FILTER_LABELS: dict[ReviewFilter, str] = {
    "all": "All pages",
    "needs_date": "Needs date approval",
    "no_text": "No text",
    "failed_ocr": "Failed OCR",
}


def unapproved_date_page_ids(project: Project) -> list[str]:
    """Pages with a suggested date that is not yet human-approved."""
    return [
        page.page_id for page in project.pages if page.date is not None and not page.date_approved
    ]


def empty_text_page_ids(
    project: Project,
    load_page_result: Callable[[str], PageResult | None],
) -> list[str]:
    """Pages whose effective transcription is empty or whitespace-only."""
    out: list[str] = []
    for page in project.pages:
        result = load_page_result(page.page_id)
        text = result.effective_text() if result is not None else None
        if not (text or "").strip():
            out.append(page.page_id)
    return out


def failed_ocr_page_ids(
    project: Project,
    load_page_result: Callable[[str], PageResult | None],
) -> list[str]:
    """Pages whose active attempt status is failed."""
    out: list[str] = []
    for page in project.pages:
        result = load_page_result(page.page_id)
        if result is not None and result.status == "failed":
            out.append(page.page_id)
    return out


def filter_review_page_ids(
    project: Project,
    *,
    filter_key: ReviewFilter,
    base_page_ids: Sequence[str],
    load_page_result: Callable[[str], PageResult | None],
) -> list[str]:
    """Return ``base_page_ids`` restricted to the selected needs-attention filter."""
    base = [pid for pid in base_page_ids if any(p.page_id == pid for p in project.pages)]
    if filter_key == "all":
        return list(base)
    if filter_key == "needs_date":
        wanted = set(unapproved_date_page_ids(project))
    elif filter_key == "no_text":
        wanted = set(empty_text_page_ids(project, load_page_result))
    elif filter_key == "failed_ocr":
        wanted = set(failed_ocr_page_ids(project, load_page_result))
    else:
        return list(base)
    return [pid for pid in base if pid in wanted]
