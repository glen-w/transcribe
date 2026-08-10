"""Candidate page selection for detection runs."""

from __future__ import annotations

from transcribe.detection.definition import CandidateStrategy, DetectorDefinition
from transcribe.detection.inputs import PageInput, build_page_input
from transcribe.domain.models import Project
from transcribe.paths import ProjectPaths
from transcribe.services.project import ProjectService


def select_candidates(
    detector: DetectorDefinition,
    project: Project,
    project_service: ProjectService,
    paths: ProjectPaths,
    *,
    page_ids: list[str] | None = None,
) -> tuple[list[PageInput], list[dict[str, str]]]:
    warnings: list[dict[str, str]] = []
    allowed = set(page_ids) if page_ids else None
    candidates: list[PageInput] = []
    for order_idx, page in enumerate(project.pages):
        if allowed is not None and page.page_id not in allowed:
            continue
        if page.analysis_excluded:
            continue
        built = build_page_input(
            page=page,
            page_order_index=order_idx,
            project=project,
            project_service=project_service,
            paths=paths,
        )
        if built is None:
            if detector.candidate_strategy == CandidateStrategy.ALL_PAGES:
                warnings.append(
                    {
                        "code": "skip_empty_page",
                        "message": f"page {page.page_id} has no OCR text",
                    }
                )
            continue
        candidates.append(built)
    return candidates, warnings
