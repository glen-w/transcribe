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
    empty_text_page_ids,
    failed_ocr_page_ids,
    filter_review_page_ids,
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
