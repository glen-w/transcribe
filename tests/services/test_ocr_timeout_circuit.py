"""Timeout circuit breaker: skip remaining pages after consecutive hangs."""

from __future__ import annotations

from pathlib import Path

from transcribe.ingest import IngestService
from transcribe.services.job import TIMEOUT_CIRCUIT_THRESHOLD, JobCoordinator
from transcribe.services.project import ProjectService, open_project_paths
from tests.conftest import FakeClock, SequentialIds
from tests.fakes import FakeVisionOCRProvider
from tests.ingest.test_ingest import _png_bytes


def _project_with_pages(tmp_path: Path, n: int):
    paths = open_project_paths(tmp_path / "proj")
    clock, ids = FakeClock(), SequentialIds()
    projects = ProjectService(paths, clock=clock, ids=ids)
    projects.create("circuit")
    ingest = IngestService(paths, clock=clock, ids=ids)
    for i in range(n):
        ingest.import_bytes(f"p{i}.png", _png_bytes(color=(i * 20, 10, 5)))
    project = projects.load()
    settings = project.settings
    settings.model_name = "fake-vision"
    projects.save_settings(project, settings)
    return paths, projects, clock, ids


def test_three_consecutive_timeouts_skip_remaining(tmp_path: Path):
    paths, projects, clock, ids = _project_with_pages(tmp_path, 5)
    provider = FakeVisionOCRProvider(
        fail_codes=["timeout"] * 5,
        digest="digest-aaa",
        verified=True,
    )
    coord = JobCoordinator(paths, projects, provider, clock=clock, ids=ids)
    progress = coord.run_blocking(force=True)
    assert progress.status == "completed"
    assert progress.circuit_open
    assert progress.failed == TIMEOUT_CIRCUIT_THRESHOLD
    assert progress.skipped == 2
    assert provider.calls == TIMEOUT_CIRCUIT_THRESHOLD


def test_success_resets_timeout_streak(tmp_path: Path):
    paths, projects, clock, ids = _project_with_pages(tmp_path, 4)
    provider = FakeVisionOCRProvider(
        fail_codes=["timeout", "", "timeout", "timeout"],
        digest="digest-aaa",
        verified=True,
    )
    coord = JobCoordinator(paths, projects, provider, clock=clock, ids=ids)
    progress = coord.run_blocking(force=True)
    assert progress.circuit_open is False
    assert progress.failed == 3
    assert progress.completed == 1
    assert provider.calls == 4


def test_non_timeout_failure_resets_streak(tmp_path: Path):
    paths, projects, clock, ids = _project_with_pages(tmp_path, 4)
    provider = FakeVisionOCRProvider(
        fail_codes=["timeout", "timeout", "http_error", "timeout"],
        digest="digest-aaa",
        verified=True,
    )
    coord = JobCoordinator(paths, projects, provider, clock=clock, ids=ids)
    progress = coord.run_blocking(force=True)
    assert progress.circuit_open is False
    assert progress.failed == 4
    assert provider.calls == 4


def test_circuit_breaker_with_two_workers(tmp_path: Path):
    paths, projects, clock, ids = _project_with_pages(tmp_path, 6)
    project = projects.load()
    settings = project.settings
    settings.max_workers = 2
    projects.save_settings(project, settings)
    provider = FakeVisionOCRProvider(
        fail_codes=["timeout"] * 6,
        digest="digest-aaa",
        verified=True,
    )
    coord = JobCoordinator(paths, projects, provider, clock=clock, ids=ids)
    progress = coord.run_blocking(force=True)
    assert progress.circuit_open
    assert progress.failed >= TIMEOUT_CIRCUIT_THRESHOLD
    # In-flight workers may still call Ollama after the trip; remaining queued
    # pages skip without a generate.
    assert provider.calls < 6
    assert progress.skipped >= 1


def test_job_sends_default_num_predict(tmp_path: Path):
    from transcribe.domain.models import DEFAULT_VISION_NUM_PREDICT

    paths, projects, clock, ids = _project_with_pages(tmp_path, 1)
    provider = FakeVisionOCRProvider(digest="digest-aaa", verified=True)
    coord = JobCoordinator(paths, projects, provider, clock=clock, ids=ids)
    progress = coord.run_blocking(force=True)
    assert progress.status == "completed"
    assert provider.last_options.get("num_predict") == DEFAULT_VISION_NUM_PREDICT
