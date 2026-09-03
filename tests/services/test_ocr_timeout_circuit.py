"""Timeout / fatal model-load circuit breakers: skip remaining pages."""

from __future__ import annotations

from pathlib import Path

from transcribe.ingest import IngestService
from transcribe.services.job import (
    MODEL_LOAD_CIRCUIT_THRESHOLD,
    TIMEOUT_CIRCUIT_THRESHOLD,
    JobCoordinator,
    JobProgress,
    cli_run_exit_code,
)
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
    assert "timeout" in progress.message.lower()
    assert cli_run_exit_code(progress) == 1


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


def test_model_load_failure_trips_circuit_immediately(tmp_path: Path):
    paths, projects, clock, ids = _project_with_pages(tmp_path, 5)
    provider = FakeVisionOCRProvider(
        fail_codes=["model_load"] * 5,
        digest="digest-aaa",
        verified=True,
    )
    coord = JobCoordinator(paths, projects, provider, clock=clock, ids=ids)
    progress = coord.run_blocking(force=True)
    assert progress.status == "completed"
    assert progress.circuit_open
    assert progress.failed == MODEL_LOAD_CIRCUIT_THRESHOLD
    assert progress.skipped == 4
    assert provider.calls == MODEL_LOAD_CIRCUIT_THRESHOLD
    assert "cannot load this vision model" in progress.message.lower()
    assert cli_run_exit_code(progress) == 1


def test_model_load_preflight_skips_pages_without_ocr_calls(tmp_path: Path):
    paths, projects, clock, ids = _project_with_pages(tmp_path, 5)
    provider = FakeVisionOCRProvider(
        probe_fail_code="model_load",
        digest="digest-aaa",
        verified=True,
    )
    coord = JobCoordinator(paths, projects, provider, clock=clock, ids=ids)
    progress = coord.run_blocking(force=True)
    assert progress.status == "failed"
    assert progress.failed == 0
    assert progress.skipped == 5
    assert provider.calls == 0
    assert "cannot load this vision model" in progress.message.lower()
    assert cli_run_exit_code(progress) == 1


def test_model_load_circuit_does_not_trip_on_generic_http_error(tmp_path: Path):
    paths, projects, clock, ids = _project_with_pages(tmp_path, 3)
    provider = FakeVisionOCRProvider(
        fail_codes=["http_error", "http_error", "http_error"],
        digest="digest-aaa",
        verified=True,
    )
    coord = JobCoordinator(paths, projects, provider, clock=clock, ids=ids)
    progress = coord.run_blocking(force=True)
    assert progress.circuit_open is False
    assert progress.failed == 3
    assert provider.calls == 3


def test_job_sends_default_num_predict(tmp_path: Path):
    from transcribe.domain.models import DEFAULT_VISION_NUM_PREDICT

    paths, projects, clock, ids = _project_with_pages(tmp_path, 1)
    provider = FakeVisionOCRProvider(digest="digest-aaa", verified=True)
    coord = JobCoordinator(paths, projects, provider, clock=clock, ids=ids)
    progress = coord.run_blocking(force=True)
    assert progress.status == "completed"
    assert provider.last_options.get("num_predict") == DEFAULT_VISION_NUM_PREDICT
    assert cli_run_exit_code(progress) == 0


def test_cli_run_exit_code_completed_without_circuit() -> None:
    assert (
        cli_run_exit_code(
            JobProgress(job_id="j", status="completed", total=1, completed=1)
        )
        == 0
    )
    assert cli_run_exit_code(JobProgress(job_id="j", status="cancelled")) == 1
    assert cli_run_exit_code(JobProgress(job_id="j", status="failed")) == 1
    assert (
        cli_run_exit_code(
            JobProgress(job_id="j", status="completed", circuit_open=True)
        )
        == 1
    )


def test_cli_run_uses_circuit_exit_code_multipass_does_not() -> None:
    main = Path("src/transcribe/__main__.py").read_text(encoding="utf-8")
    assert "return cli_run_exit_code(progress)" in main
    run_idx = main.index('if args.cmd == "run":')
    multi_idx = main.index('if args.cmd == "multipass":')
    assert "return cli_run_exit_code(progress)" in main[run_idx:multi_idx]
    assert "return cli_run_exit_code(progress)" not in main[multi_idx:]
    assert 'return 0 if progress.status == "completed" else 1' in main[multi_idx:]
