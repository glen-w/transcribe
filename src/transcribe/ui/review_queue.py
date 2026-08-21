"""Review needs-attention queue helpers (usability-wave U3.1 + OCR workbench)."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from typing import Literal

from transcribe.domain.models import PageResult, Project

ReviewFilter = Literal[
    "all",
    "needs_attention",
    "unreviewed",
    "reviewed",
    "skipped",
    "high_disagreement",
    "needs_date",
    "no_text",
    "failed_ocr",
]

REVIEW_FILTER_LABELS: dict[ReviewFilter, str] = {
    "all": "All pages",
    "needs_attention": "Needs attention",
    "unreviewed": "Unreviewed",
    "reviewed": "Reviewed",
    "skipped": "Skipped",
    "high_disagreement": "High disagreement",
    "needs_date": "Needs date approval",
    "no_text": "No text",
    "failed_ocr": "Failed OCR",
}

REVIEW_FILTER_ORDER: list[ReviewFilter] = [
    "unreviewed",
    "needs_attention",
    "high_disagreement",
    "needs_date",
    "no_text",
    "failed_ocr",
    "reviewed",
    "skipped",
    "all",
]

HIGH_DISAGREEMENT_MIN = 3


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


def review_status_page_ids(project: Project, status: str) -> list[str]:
    """Pages whose stored review_status matches (missing → unreviewed)."""
    wanted = status or "unreviewed"
    return [
        page.page_id for page in project.pages if (page.review_status or "unreviewed") == wanted
    ]


def not_reviewed_page_ids(project: Project) -> list[str]:
    """Pages that are not marked ``reviewed`` (includes skipped / needs attention)."""
    return [
        page.page_id for page in project.pages if (page.review_status or "unreviewed") != "reviewed"
    ]


RerunOcrScope = Literal["this_page", "all_pages", "not_reviewed"]


def rerun_ocr_page_ids(
    project: Project,
    *,
    scope: RerunOcrScope,
    page_id: str,
) -> list[str]:
    """Notebook page ids for a Review re-run OCR scope."""
    if scope == "this_page":
        if any(page.page_id == page_id for page in project.pages):
            return [page_id]
        return []
    if scope == "all_pages":
        return [page.page_id for page in project.pages]
    return not_reviewed_page_ids(project)


def source_disagreement_count(result: PageResult | None) -> int:
    """Cached count when present; otherwise align current merge-input vision texts."""
    if result is None:
        return 0
    if result.source_disagreement_count is not None:
        return int(result.source_disagreement_count)
    from transcribe.services.ocr_alignment import align_ocr
    from transcribe.services.ocr_composite_state import merge_input_vision_attempts

    sources = {
        attempt.attempt_id: attempt.raw_text or ""
        for attempt in merge_input_vision_attempts(result)
    }
    if len(sources) < 2:
        return 0
    return align_ocr(sources).source_disagreement_count


def high_disagreement_page_ids(
    project: Project,
    load_page_result: Callable[[str], PageResult | None],
    *,
    minimum: int = HIGH_DISAGREEMENT_MIN,
) -> list[str]:
    out: list[str] = []
    for page in project.pages:
        result = load_page_result(page.page_id)
        if source_disagreement_count(result) >= minimum:
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
    elif filter_key == "high_disagreement":
        wanted = set(high_disagreement_page_ids(project, load_page_result))
    elif filter_key in {"unreviewed", "needs_attention", "reviewed", "skipped"}:
        wanted = set(review_status_page_ids(project, filter_key))
    else:
        return list(base)
    return [pid for pid in base if pid in wanted]


def review_filter_count(
    project: Project,
    *,
    filter_key: ReviewFilter,
    base_page_ids: Sequence[str],
    load_page_result: Callable[[str], PageResult | None],
) -> int:
    """Number of pages matching ``filter_key`` within ``base_page_ids``."""
    return len(
        filter_review_page_ids(
            project,
            filter_key=filter_key,
            base_page_ids=base_page_ids,
            load_page_result=load_page_result,
        )
    )


def available_review_filters(
    project: Project,
    *,
    base_page_ids: Sequence[str],
    load_page_result: Callable[[str], PageResult | None],
) -> list[tuple[ReviewFilter, int]]:
    """Filter options with non-zero counts, in display order."""
    out: list[tuple[ReviewFilter, int]] = []
    for key in REVIEW_FILTER_ORDER:
        count = review_filter_count(
            project,
            filter_key=key,
            base_page_ids=base_page_ids,
            load_page_result=load_page_result,
        )
        if count > 0:
            out.append((key, count))
    return out


def format_review_filter_label(filter_key: ReviewFilter, count: int) -> str:
    return f"{REVIEW_FILTER_LABELS[filter_key]} ({count})"
