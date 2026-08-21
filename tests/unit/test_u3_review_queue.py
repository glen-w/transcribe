"""U3 Review queue filters and Reading chronology helpers."""

from __future__ import annotations

from pathlib import Path

from transcribe.domain.dates import ApproximateDate, DATE_SOURCE_EXTRACTED
from transcribe.domain.models import OCRAttempt, PageResult, Project
from transcribe.domain.validation import validate_project
from transcribe.ingest import IngestService
from transcribe.persistence.atomic import write_json_atomic
from transcribe.ports import to_iso
from transcribe.services.project import ProjectService, open_project_paths
from transcribe.ui.action_menus.nav import chronological_page_ids, viewer_page_ids
from transcribe.ui.review_queue import (
    available_review_filters,
    empty_text_page_ids,
    failed_ocr_page_ids,
    filter_review_page_ids,
    format_review_filter_label,
    high_disagreement_page_ids,
    not_reviewed_page_ids,
    rerun_ocr_page_ids,
    review_status_page_ids,
    unapproved_date_page_ids,
)
from tests.conftest import FakeClock, SequentialIds
from tests.ingest.test_ingest import _png_bytes


def _seed_result(
    projects: ProjectService,
    page_id: str,
    *,
    text: str | None,
    status: str,
    clock: FakeClock,
) -> None:
    attempts = []
    active = None
    if status != "pending":
        active = "a1"
        attempts = [
            OCRAttempt(
                attempt_id="a1",
                status=status,
                input_fingerprint="x",
                fingerprint_payload={},
                raw_text=text,
                provenance=None,
                provider_metadata={},
                started_at=to_iso(clock.now()),
                completed_at=to_iso(clock.now()),
            )
        ]
    write_json_atomic(
        projects.paths.result_path(page_id),
        PageResult(
            page_id=page_id,
            active_attempt_id=active,
            attempts=attempts,
            updated_at=to_iso(clock.now()),
        ).as_dict(),
    )


def _project_with_pages(tmp_path: Path, n: int = 3) -> tuple[ProjectService, Project, FakeClock]:
    paths = open_project_paths(tmp_path / "nb")
    clock, ids = FakeClock(), SequentialIds()
    projects = ProjectService(paths, clock=clock, ids=ids)
    projects.create("U3")
    ingest = IngestService(paths, clock=clock, ids=ids)
    for i in range(n):
        ingest.import_bytes(f"{i}.png", _png_bytes(color=(i, i, i)))
    return projects, projects.load(reconcile=False), clock


def _write_project(projects: ProjectService, project: Project) -> Project:
    validate_project(project)
    write_json_atomic(projects.paths.manifest, project.as_dict())
    return projects.load(reconcile=False)


def test_review_queue_filters(tmp_path: Path) -> None:
    projects, project, clock = _project_with_pages(tmp_path, 3)
    p0, p1, p2 = [p.page_id for p in project.pages]
    _seed_result(projects, p0, text="hello", status="succeeded", clock=clock)
    _seed_result(projects, p1, text="", status="succeeded", clock=clock)
    _seed_result(projects, p2, text=None, status="failed", clock=clock)

    projects.approve_page_date(p0, ApproximateDate(2024, 1, 2))
    project = projects.load(reconcile=False)
    page1 = next(p for p in project.pages if p.page_id == p1)
    page1.set_date_state(ApproximateDate(2024, 2, 1), approved=False, source=DATE_SOURCE_EXTRACTED)
    project = _write_project(projects, project)

    assert unapproved_date_page_ids(project) == [p1]
    assert empty_text_page_ids(project, projects.load_page_result) == [p1, p2]
    assert failed_ocr_page_ids(project, projects.load_page_result) == [p2]

    base = viewer_page_ids(project)
    assert filter_review_page_ids(
        project,
        filter_key="needs_date",
        base_page_ids=base,
        load_page_result=projects.load_page_result,
    ) == [p1]
    assert filter_review_page_ids(
        project,
        filter_key="failed_ocr",
        base_page_ids=base,
        load_page_result=projects.load_page_result,
    ) == [p2]


def test_available_review_filters_omit_zero_counts(tmp_path: Path) -> None:
    projects, project, clock = _project_with_pages(tmp_path, 3)
    p0, p1, p2 = [p.page_id for p in project.pages]
    _seed_result(projects, p0, text="hello", status="succeeded", clock=clock)
    _seed_result(projects, p1, text="", status="succeeded", clock=clock)
    _seed_result(projects, p2, text=None, status="failed", clock=clock)
    page1 = next(p for p in project.pages if p.page_id == p1)
    page1.set_date_state(ApproximateDate(2024, 2, 1), approved=False, source=DATE_SOURCE_EXTRACTED)
    project = _write_project(projects, project)

    base = viewer_page_ids(project)
    options = available_review_filters(
        project,
        base_page_ids=base,
        load_page_result=projects.load_page_result,
    )
    keys = [key for key, _ in options]
    assert "high_disagreement" not in keys
    assert "reviewed" not in keys
    assert "skipped" not in keys
    assert options == [
        ("unreviewed", 3),
        ("needs_date", 1),
        ("no_text", 2),
        ("failed_ocr", 1),
        ("all", 3),
    ]
    assert format_review_filter_label("needs_date", 1) == "Needs date approval (1)"


def test_batch_approve_and_ignore_suggested_dates(tmp_path: Path) -> None:
    projects, project, _clock = _project_with_pages(tmp_path, 2)
    p0, p1 = [p.page_id for p in project.pages]
    for pid, date in (
        (p0, ApproximateDate(2024, 3, 1)),
        (p1, ApproximateDate(2024, 3, 2)),
    ):
        page = next(p for p in project.pages if p.page_id == pid)
        page.set_date_state(date, approved=False, source=DATE_SOURCE_EXTRACTED)
    _write_project(projects, project)

    project, count, regs = projects.approve_all_suggested_dates(confirm_regressions=True)
    assert count == 2
    assert regs == []
    assert all(p.date_approved for p in project.pages if p.date is not None)

    project = projects.load(reconcile=False)
    for page in project.pages:
        page.set_date_state(
            ApproximateDate(2025, 1, 1), approved=False, source=DATE_SOURCE_EXTRACTED
        )
    _write_project(projects, project)
    project, ignored = projects.ignore_all_suggested_dates()
    assert ignored == 2
    assert all(p.date is None for p in project.pages)


def test_batch_approve_requires_confirm_on_regressions(tmp_path: Path) -> None:
    projects, project, _clock = _project_with_pages(tmp_path, 2)
    p0, p1 = [p.page_id for p in project.pages]
    next(p for p in project.pages if p.page_id == p0).set_date_state(
        ApproximateDate(2024, 6, 1), approved=False, source=DATE_SOURCE_EXTRACTED
    )
    next(p for p in project.pages if p.page_id == p1).set_date_state(
        ApproximateDate(2024, 1, 1), approved=False, source=DATE_SOURCE_EXTRACTED
    )
    _write_project(projects, project)

    project, count, regs = projects.approve_all_suggested_dates(confirm_regressions=False)
    assert count == 0
    assert len(regs) == 1
    assert all(not p.date_approved for p in project.pages)

    project, count, regs = projects.approve_all_suggested_dates(confirm_regressions=True)
    assert count == 2
    assert len(regs) == 1


def test_chronological_page_ids_orders_dated_then_undated(tmp_path: Path) -> None:
    projects, project, _clock = _project_with_pages(tmp_path, 3)
    p0, p1, p2 = project.pages
    p0.set_date_state(ApproximateDate(2024, 5, 1), approved=True, source=None)
    p2.set_date_state(ApproximateDate(2024, 1, 1), approved=True, source=None)
    project = _write_project(projects, project)

    ordered = chronological_page_ids(project)
    assert ordered[0] == p2.page_id
    assert ordered[1] == p0.page_id
    assert ordered[2] == p1.page_id


def test_high_disagreement_filter_uses_cached_count(tmp_path: Path) -> None:
    projects, project, clock = _project_with_pages(tmp_path, 2)
    p0, p1 = [p.page_id for p in project.pages]
    _seed_result(projects, p0, text="hello", status="succeeded", clock=clock)
    _seed_result(projects, p1, text="hello", status="succeeded", clock=clock)
    projects.cache_alignment_signals(p0, source_disagreement_count=3, agreement_ratio=0.5)
    projects.cache_alignment_signals(p1, source_disagreement_count=2, agreement_ratio=0.8)
    assert high_disagreement_page_ids(project, projects.load_page_result) == [p0]
    base = viewer_page_ids(project)
    assert filter_review_page_ids(
        project,
        filter_key="high_disagreement",
        base_page_ids=base,
        load_page_result=projects.load_page_result,
    ) == [p0]


def test_review_status_queue_filters(tmp_path: Path) -> None:
    projects, project, clock = _project_with_pages(tmp_path, 3)
    p0, p1, p2 = [p.page_id for p in project.pages]
    _seed_result(projects, p0, text="hello", status="succeeded", clock=clock)
    _seed_result(projects, p1, text="hello", status="succeeded", clock=clock)
    _seed_result(projects, p2, text="hello", status="succeeded", clock=clock)
    projects.save_user_edit(p0, None, mark_reviewed=True)
    projects.set_page_review_status(p1, "needs_attention")
    project = projects.load(reconcile=False)
    assert review_status_page_ids(project, "reviewed") == [p0]
    assert review_status_page_ids(project, "needs_attention") == [p1]
    assert review_status_page_ids(project, "unreviewed") == [p2]
    base = viewer_page_ids(project)
    assert filter_review_page_ids(
        project,
        filter_key="reviewed",
        base_page_ids=base,
        load_page_result=projects.load_page_result,
    ) == [p0]
    assert not_reviewed_page_ids(project) == [p1, p2]
    assert rerun_ocr_page_ids(project, scope="this_page", page_id=p0) == [p0]
    assert rerun_ocr_page_ids(project, scope="this_page", page_id="missing") == []
    assert rerun_ocr_page_ids(project, scope="all_pages", page_id=p0) == [p0, p1, p2]
    assert rerun_ocr_page_ids(project, scope="not_reviewed", page_id=p0) == [p1, p2]
