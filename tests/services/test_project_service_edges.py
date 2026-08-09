"""ProjectService and delete_managed_notebook edge contracts."""

from __future__ import annotations

from pathlib import Path

import pytest

from transcribe.domain.dates import ApproximateDate
from transcribe.domain.models import MAX_ATTEMPTS_RETAINED, OCRAttempt
from transcribe.errors import JobConflictError, ProjectError
from transcribe.ingest import IngestService
from transcribe.persistence.locks import JobLock
from transcribe.services.project import (
    ProjectService,
    delete_managed_notebook,
    open_project_paths,
)
from tests.conftest import FakeClock, SequentialIds
from tests.ingest.test_ingest import _png_bytes


def _svc(tmp_path: Path, name: str = "nb") -> tuple[ProjectService, Path]:
    paths = open_project_paths(tmp_path / "projects" / name)
    clock, ids = FakeClock(), SequentialIds()
    return ProjectService(paths, clock=clock, ids=ids), paths.root.parent


def test_create_refuses_existing_project(tmp_path: Path) -> None:
    projects, _ = _svc(tmp_path)
    projects.create("Once")
    with pytest.raises(ProjectError, match="already exists"):
        projects.create("Twice")


def test_load_missing_manifest_raises(tmp_path: Path) -> None:
    projects, _ = _svc(tmp_path, "empty")
    with pytest.raises(ProjectError, match="no project.json"):
        projects.load(reconcile=False)


def test_title_rename_roundtrip(tmp_path: Path) -> None:
    projects, _ = _svc(tmp_path)
    projects.create("Original")
    updated = projects.update_notebook_metadata(title="  Renamed notebook  ")
    assert updated.title == "  Renamed notebook  "
    assert projects.load(reconcile=False).title == "  Renamed notebook  "


def test_unknown_page_and_cover_refused(tmp_path: Path) -> None:
    projects, _ = _svc(tmp_path)
    projects.create("Meta")
    with pytest.raises(ProjectError, match="unknown page_id"):
        projects.update_page_metadata("missing", tags=["x"])
    with pytest.raises(ProjectError, match="unknown cover_page_id"):
        projects.update_notebook_metadata(cover_page_id="missing")


def test_adopt_raw_as_edit_clears_edited_text(tmp_path: Path) -> None:
    projects, _ = _svc(tmp_path)
    project = projects.create("Edit")
    ingest = IngestService(projects.paths, clock=projects.clock, ids=projects.ids)
    project = ingest.import_bytes("a.png", _png_bytes())
    page_id = project.pages[0].page_id
    projects.record_generation(
        page_id,
        OCRAttempt(
            attempt_id="a1",
            status="succeeded",
            input_fingerprint="fp",
            fingerprint_payload={},
            raw_text="ocr raw",
            provenance=None,
            provider_metadata={},
            started_at="2026-01-01T00:00:00.000Z",
            completed_at="2026-01-01T00:00:01.000Z",
        ),
    )
    projects.save_user_edit(page_id, "user edit")
    result = projects.load_page_result(page_id)
    assert result is not None
    assert result.effective_text() == "user edit"
    cleared = projects.adopt_raw_as_edit(page_id)
    assert cleared.edited_text is None
    assert cleared.effective_text() == "ocr raw"


def test_record_generation_retains_active_and_newest(
    tmp_path: Path,
) -> None:
    projects, _ = _svc(tmp_path)
    project = projects.create("Attempts")
    ingest = IngestService(projects.paths, clock=projects.clock, ids=projects.ids)
    project = ingest.import_bytes("a.png", _png_bytes())
    page_id = project.pages[0].page_id
    total = MAX_ATTEMPTS_RETAINED + 3
    for i in range(total):
        projects.record_generation(
            page_id,
            OCRAttempt(
                attempt_id=f"a{i:02d}",
                status="succeeded",
                input_fingerprint="fp",
                fingerprint_payload={},
                raw_text=f"t{i}",
                provenance=None,
                provider_metadata={},
                started_at=f"2026-01-01T00:{i:02d}:00.000Z",
                completed_at=f"2026-01-01T00:{i:02d}:01.000Z",
            ),
        )
    result = projects.load_page_result(page_id)
    assert result is not None
    assert result.active_attempt_id == f"a{total - 1:02d}"
    assert len(result.attempts) == MAX_ATTEMPTS_RETAINED
    ids = [a.attempt_id for a in result.attempts]
    assert result.active_attempt_id in ids
    # Newest attempts retained (active is newest).
    assert ids[-1] == result.active_attempt_id
    assert f"a{total - 1:02d}" in ids
    assert "a00" not in ids


def test_delete_managed_notebook_refuses_missing_manifest(tmp_path: Path) -> None:
    projects_dir = tmp_path / "projects"
    projects_dir.mkdir()
    root = projects_dir / "hollow"
    root.mkdir()
    with pytest.raises(ProjectError, match="missing project.json"):
        delete_managed_notebook(root, projects_dir=projects_dir)


def test_delete_managed_notebook_refuses_non_directory(tmp_path: Path) -> None:
    projects_dir = tmp_path / "projects"
    projects_dir.mkdir()
    root = projects_dir / "file-not-dir"
    root.write_text("{}", encoding="utf-8")
    with pytest.raises(ProjectError, match="not a directory"):
        delete_managed_notebook(root, projects_dir=projects_dir)


def test_delete_managed_notebook_refuses_when_job_lock_held(
    tmp_path: Path,
) -> None:
    projects_dir = tmp_path / "projects"
    projects_dir.mkdir()
    paths = open_project_paths(projects_dir / "busy")
    clock, ids = FakeClock(), SequentialIds()
    ProjectService(paths, clock=clock, ids=ids).create("Busy")
    held = JobLock(paths.job_lock)
    assert held.try_acquire()
    try:
        with pytest.raises(JobConflictError, match="OCR job is running"):
            delete_managed_notebook(paths.root, projects_dir=projects_dir)
    finally:
        held.release()
    assert paths.root.is_dir()


def test_cover_page_roundtrip_after_ingest(tmp_path: Path) -> None:
    projects, _ = _svc(tmp_path)
    project = projects.create("Cover")
    ingest = IngestService(projects.paths, clock=projects.clock, ids=projects.ids)
    project = ingest.import_bytes("a.png", _png_bytes())
    page_id = project.pages[0].page_id
    updated = projects.update_notebook_metadata(
        cover_page_id=page_id,
        date_start=ApproximateDate(2020),
    )
    assert updated.cover_page_id == page_id
    reloaded = projects.load(reconcile=False)
    assert reloaded.cover_page_id == page_id
    assert reloaded.date_start == ApproximateDate(2020)
