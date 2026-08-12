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
    allocate_notebook_root,
    delete_managed_notebook,
    notebook_dir_slug,
    open_project_paths,
)
from tests.conftest import FakeClock, SequentialIds
from tests.ingest.test_ingest import _pdf_bytes, _png_bytes


def _svc(tmp_path: Path, name: str = "nb") -> tuple[ProjectService, Path]:
    paths = open_project_paths(tmp_path / "projects" / name)
    clock, ids = FakeClock(), SequentialIds()
    return ProjectService(paths, clock=clock, ids=ids), paths.root.parent


def test_create_refuses_existing_project(tmp_path: Path) -> None:
    projects, _ = _svc(tmp_path)
    projects.create("Once")
    with pytest.raises(ProjectError, match="already exists"):
        projects.create("Twice")


def test_allocate_notebook_root_unique(tmp_path: Path) -> None:
    projects = tmp_path / "projects"
    projects.mkdir()
    assert notebook_dir_slug("Travel 2024") == "Travel-2024"
    first = allocate_notebook_root(projects, "Travel 2024")
    assert first == projects / "Travel-2024"
    first.mkdir()
    second = allocate_notebook_root(projects, "Travel 2024")
    assert second == projects / "Travel-2024-2"
    second.mkdir()
    third = allocate_notebook_root(projects, "Travel 2024")
    assert third == projects / "Travel-2024-3"


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


def test_delete_page_removes_single_image_source(tmp_path: Path) -> None:
    projects, _ = _svc(tmp_path, "del-img")
    projects.create("Two images")
    ingest = IngestService(projects.paths, clock=projects.clock, ids=projects.ids)
    project = ingest.import_bytes("a.png", _png_bytes(color=(1, 2, 3)))
    project = ingest.import_bytes("b.png", _png_bytes(color=(4, 5, 6)))
    assert len(project.pages) == 2
    assert len(project.sources) == 2
    first = project.pages[0]
    first_id = first.page_id
    first_source = first.source_id
    render = project.renders[first.active_render_id]
    img_path = projects.paths.resolve_contained(render.image_relpath)
    source_path = projects.paths.resolve_contained(project.sources[0].stored_relpath)
    assert img_path.is_file()
    assert source_path.is_file()

    updated = projects.delete_page(first_id)
    assert len(updated.pages) == 1
    assert first_id not in {p.page_id for p in updated.pages}
    assert first_source not in {s.source_id for s in updated.sources}
    assert first.active_render_id not in updated.renders
    assert not img_path.exists()
    assert not source_path.exists()
    assert not projects.paths.result_path(first_id).exists()
    reloaded = projects.load(reconcile=False)
    assert len(reloaded.pages) == 1


def test_delete_page_reindexes_pdf_source(tmp_path: Path) -> None:
    projects, _ = _svc(tmp_path, "del-pdf")
    projects.create("PDF")
    ingest = IngestService(projects.paths, clock=projects.clock, ids=projects.ids)
    project = ingest.import_bytes("scan.pdf", _pdf_bytes(3), render_dpi=100)
    assert [p.page_index for p in project.pages] == [0, 1, 2]
    middle = project.pages[1]
    middle_id = middle.page_id
    kept_ids = [project.pages[0].page_id, project.pages[2].page_id]

    updated = projects.delete_page(middle_id)
    assert [p.page_id for p in updated.pages] == kept_ids
    assert [p.page_index for p in updated.pages] == [0, 1]
    assert updated.sources[0].page_count == 2
    for page in updated.pages:
        render = updated.renders[page.active_render_id]
        expected_prefix = f"pages/{page.source_id}/{page.page_index:04d}/"
        assert render.image_relpath.startswith(expected_prefix)
        assert projects.paths.resolve_contained(render.image_relpath).is_file()
        assert render.pdf_page_index == page.page_index
    assert not (
        projects.paths.pages_dir / middle.source_id / "0002"
    ).exists()


def test_delete_first_pdf_page_reindexes_without_collision(tmp_path: Path) -> None:
    projects, _ = _svc(tmp_path, "del-pdf-first")
    projects.create("PDF first")
    ingest = IngestService(projects.paths, clock=projects.clock, ids=projects.ids)
    project = ingest.import_bytes("scan.pdf", _pdf_bytes(3), render_dpi=100)
    first_id = project.pages[0].page_id
    kept = [project.pages[1].page_id, project.pages[2].page_id]

    updated = projects.delete_page(first_id)
    assert [p.page_id for p in updated.pages] == kept
    assert [p.page_index for p in updated.pages] == [0, 1]
    for page in updated.pages:
        render = updated.renders[page.active_render_id]
        assert projects.paths.resolve_contained(render.image_relpath).is_file()
        assert render.pdf_page_index == page.page_index


def test_delete_page_clears_cover_and_refuses_last(
    tmp_path: Path,
) -> None:
    projects, _ = _svc(tmp_path, "del-last")
    projects.create("Cover clear")
    ingest = IngestService(projects.paths, clock=projects.clock, ids=projects.ids)
    project = ingest.import_bytes("a.png", _png_bytes(color=(1, 1, 1)))
    project = ingest.import_bytes("b.png", _png_bytes(color=(2, 2, 2)))
    cover_id = project.pages[0].page_id
    projects.update_notebook_metadata(cover_page_id=cover_id)

    updated = projects.delete_page(cover_id)
    assert updated.cover_page_id is None
    assert len(updated.pages) == 1

    with pytest.raises(ProjectError, match="last page"):
        projects.delete_page(updated.pages[0].page_id)


def test_delete_page_refuses_when_job_lock_held(tmp_path: Path) -> None:
    projects, _ = _svc(tmp_path, "del-busy")
    projects.create("Busy")
    ingest = IngestService(projects.paths, clock=projects.clock, ids=projects.ids)
    project = ingest.import_bytes("a.png", _png_bytes(color=(1, 1, 1)))
    project = ingest.import_bytes("b.png", _png_bytes(color=(2, 2, 2)))
    held = JobLock(projects.paths.job_lock)
    assert held.try_acquire()
    try:
        with pytest.raises(JobConflictError, match="OCR job is running"):
            projects.delete_page(project.pages[0].page_id)
    finally:
        held.release()
