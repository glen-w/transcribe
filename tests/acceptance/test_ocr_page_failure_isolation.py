"""Acceptance: one page OCR failure must not block remaining pages (offline)."""

from __future__ import annotations

from pathlib import Path

from transcribe.ingest import IngestService
from transcribe.services.job import JobCoordinator
from transcribe.services.project import ProjectService, open_project_paths
from tests.conftest import FakeClock, SequentialIds
from tests.fakes import FakeVisionOCRProvider
from tests.ingest.test_ingest import _png_bytes


def test_provider_failure_on_one_page_isolates_others(tmp_path: Path) -> None:
    paths = open_project_paths(tmp_path / "proj")
    clock, ids = FakeClock(), SequentialIds("iso")
    projects = ProjectService(paths, clock=clock, ids=ids)
    project = projects.create("iso")
    ingest = IngestService(paths, clock=clock, ids=ids)
    for i in range(3):
        project = ingest.import_bytes(f"p{i}.png", _png_bytes(color=(i * 10, 20, 30)))
    settings = project.settings
    settings.model_name = "fake-vision"
    settings.max_workers = 1
    project = projects.save_settings(project, settings)

    # First call fails; subsequent pages succeed (default max_workers=1).
    provider = FakeVisionOCRProvider(fail_times=1)
    coord = JobCoordinator(paths, projects, provider, clock=clock, ids=ids)
    progress = coord.run_blocking()

    assert progress.failed == 1
    assert progress.completed == 2
    assert provider.calls == 3

    statuses = []
    for page in projects.load().pages:
        result = projects.load_page_result(page.page_id)
        assert result is not None
        attempt = result.active_attempt()
        assert attempt is not None
        statuses.append(attempt.status)
    assert statuses.count("failed") == 1
    assert statuses.count("succeeded") == 2
    failed = next(
        projects.load_page_result(p.page_id).active_attempt()
        for p in projects.load().pages
        if projects.load_page_result(p.page_id).active_attempt().status == "failed"
    )
    assert failed.error is not None
    assert failed.error.retriable is True
