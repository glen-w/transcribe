from __future__ import annotations

from pathlib import Path

import pytest

from transcribe.errors import JobConflictError
from transcribe.ingest import IngestService
from transcribe.persistence.locks import JobLock
from transcribe.services.job import JobCoordinator
from transcribe.services.project import ProjectService, open_project_paths
from tests.conftest import FakeClock, SequentialIds
from tests.fakes import FakeVisionOCRProvider
from tests.ingest.test_ingest import _png_bytes


def _project_with_pages(tmp_path: Path, n: int = 2):
    paths = open_project_paths(tmp_path / "proj")
    clock, ids = FakeClock(), SequentialIds()
    projects = ProjectService(paths, clock=clock, ids=ids)
    project = projects.create("t")
    ingest = IngestService(paths, clock=clock, ids=ids)
    for i in range(n):
        project = ingest.import_bytes(f"p{i}.png", _png_bytes(color=(i * 10, 20, 30)))
    settings = project.settings
    settings.model_name = "fake-vision"
    project = projects.save_settings(project, settings)
    provider = FakeVisionOCRProvider()
    coord = JobCoordinator(paths, projects, provider, clock=clock, ids=ids)
    return paths, projects, coord, provider, project


def test_run_and_skip_matching_fingerprint(tmp_path: Path):
    paths, projects, coord, provider, project = _project_with_pages(tmp_path, 2)
    progress = coord.run_blocking()
    assert progress.status == "completed"
    assert provider.calls == 2
    # second run should skip both
    progress2 = coord.run_blocking()
    assert progress2.skipped == 2
    assert provider.calls == 2


def test_edit_survives_rerun(tmp_path: Path):
    paths, projects, coord, provider, project = _project_with_pages(tmp_path, 1)
    coord.run_blocking()
    page_id = project.pages[0].page_id
    projects.save_user_edit(page_id, "my correction")
    provider.default_text = "new raw"
    coord.run_blocking(force=True)
    result = projects.load_page_result(page_id)
    assert result is not None
    assert result.edited_text == "my correction"
    assert result.active_attempt() is not None
    assert result.active_attempt().raw_text.startswith("new raw")
    assert result.effective_text() == "my correction"
    assert len(result.attempts) >= 2


def test_fingerprint_invalidation_on_prompt_change(tmp_path: Path):
    paths, projects, coord, provider, project = _project_with_pages(tmp_path, 2)
    coord.run_blocking()
    assert provider.calls == 2
    settings = projects.load().settings
    settings.custom_prompt = "Extract EXACTLY differently."
    projects.save_settings(projects.load(), settings)
    progress = coord.run_blocking()
    assert progress.skipped == 0
    assert provider.calls == 4


def test_kill_restart_interrupted_and_resume(tmp_path: Path):
    paths, projects, coord, provider, project = _project_with_pages(tmp_path, 3)
    # Simulate crash: mark page 1 succeeded, page 2 running, leave page 3 pending
    coord.run_blocking(page_ids=[project.pages[0].page_id])
    page1 = project.pages[0].page_id
    projects.save_user_edit(page1, "keep me")

    # Manually write a running attempt for page 2
    from transcribe.domain.models import OCRAttempt

    page2 = project.pages[1].page_id
    running = OCRAttempt(
        attempt_id="crashrun",
        status="running",
        input_fingerprint="x",
        fingerprint_payload={},
        raw_text=None,
        provenance=None,
        provider_metadata={},
        started_at="2026-01-01T00:00:00.000Z",
    )
    projects.record_generation(page2, running)

    # Re-open with reconcile (job lock free)
    reopened = ProjectService(paths, clock=FakeClock(), ids=SequentialIds("r"))
    reopened.load(reconcile=True)
    result2 = reopened.load_page_result(page2)
    assert result2 is not None
    assert result2.status == "interrupted"

    # Resume should not redo page1 (matching fingerprint + succeeded), should do page2+3
    calls_before = provider.calls
    coord2 = JobCoordinator(paths, reopened, provider, clock=FakeClock(), ids=SequentialIds("j"))
    progress = coord2.run_blocking()
    assert progress.status == "completed"
    assert reopened.load_page_result(page1).edited_text == "keep me"
    assert provider.calls > calls_before


def test_job_lock_blocks_second_job(tmp_path: Path):
    paths, projects, coord, provider, project = _project_with_pages(tmp_path, 1)
    held = JobLock(paths.job_lock)
    assert held.try_acquire()
    try:
        with pytest.raises(JobConflictError):
            coord.run_blocking()
    finally:
        held.release()


def test_reconcile_skipped_when_job_lock_held(tmp_path: Path):
    paths, projects, coord, provider, project = _project_with_pages(tmp_path, 1)
    from transcribe.domain.models import OCRAttempt

    page_id = project.pages[0].page_id
    projects.record_generation(
        page_id,
        OCRAttempt(
            attempt_id="live",
            status="running",
            input_fingerprint="x",
            fingerprint_payload={},
            raw_text=None,
            provenance=None,
            provider_metadata={},
            started_at="2026-01-01T00:00:00.000Z",
        ),
    )
    held = JobLock(paths.job_lock)
    assert held.try_acquire()
    try:
        projects.load(reconcile=True)
        assert projects.load_page_result(page_id).status == "running"
    finally:
        held.release()


def test_merge_safe_edit_during_generation(tmp_path: Path):
    paths, projects, coord, provider, project = _project_with_pages(tmp_path, 1)
    page_id = project.pages[0].page_id
    # Pretend a generation finished
    coord.run_blocking()
    # Concurrent-style: edit then another generation record
    projects.save_user_edit(page_id, "user edit")
    coord.run_blocking(force=True)
    result = projects.load_page_result(page_id)
    assert result.edited_text == "user edit"
    assert result.active_attempt().raw_text is not None
