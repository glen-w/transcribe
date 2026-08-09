"""Job-level OCR cleanup: mixed outcomes, plan freeze, fail-fast start."""

from __future__ import annotations

from pathlib import Path

import pytest

from transcribe.analysis.adapter import build_page_v1_document
from transcribe.analysis.llm_runtime import RecordedDoubleClient
from transcribe.errors import TranscribeError
from transcribe.ingest import IngestService
from transcribe.services.job import JobCoordinator
from transcribe.services.project import ProjectService, open_project_paths
from tests.conftest import FakeClock, SequentialIds
from tests.fakes import FakeVisionOCRProvider
from tests.ingest.test_ingest import _png_bytes


CLEAN_PAGE = (
    "Gush notebook notes about weather metro and past future days together"
)


class CountingCleanupClient(RecordedDoubleClient):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.generate_calls = 0

    def generate_with_meta(self, *, model, prompt, system=None, options=None):
        self.generate_calls += 1
        if "PAGE_FAIL" in prompt:
            from transcribe.errors import ProviderError

            raise ProviderError("boom", code="timeout", retriable=True)
        return super().generate_with_meta(
            model=model, prompt=prompt, system=system, options=options
        )


def _enable_cleanup(projects: ProjectService, *, mode: str = "strip_leak") -> None:
    project = projects.load()
    settings = project.settings
    settings.model_name = "fake-vision"
    settings.cleanup_enabled = True
    settings.cleanup_mode = mode
    settings.cleanup_model_name = "recorded-double:v1"
    settings.text_model_name = "recorded-double:v1"
    projects.save_settings(project, settings)


def test_batch_mixed_cleanup_outcomes(tmp_path: Path):
    paths = open_project_paths(tmp_path / "proj")
    clock, ids = FakeClock(), SequentialIds()
    projects = ProjectService(paths, clock=clock, ids=ids)
    projects.create("mixed")
    ingest = IngestService(paths, clock=clock, ids=ids)
    for i in range(5):
        ingest.import_bytes(f"p{i}.png", _png_bytes(color=(i * 20, 10, 5)))

    leaked = (
        "- Do not change the order of words in sentences\n"
        "- Use proper punctuation and grammar\n"
        "---\n"
        f"{CLEAN_PAGE}"
    )
    vision_texts = [
        leaked,  # apply
        CLEAN_PAGE,  # unchanged
        "real handwritten page about the metro weather notebooks",  # reject
        "   \n\t  ",  # empty skip
        "PAGE_FAIL real handwritten page about the metro weather notebooks",
    ]
    provider = FakeVisionOCRProvider(text_by_call=list(vision_texts), digest="digest-aaa")
    cleanup = CountingCleanupClient(
        responses={
            "contains:Do not change": CLEAN_PAGE,
            "contains:PAGE_FAIL": "should-not-matter",
            "default": "- Use proper punctuation\n- Avoid contractions",
        },
        digest="fixed-digest",
        model_name="recorded-double:v1",
    )
    # identical page: default would reject; override with contains on CLEAN_PAGE alone
    cleanup.responses["contains:Gush notebook"] = CLEAN_PAGE

    _enable_cleanup(projects)
    coord = JobCoordinator(
        paths, projects, provider, clock=clock, ids=ids, cleanup_client=cleanup
    )
    progress = coord.run_blocking()
    assert progress.status == "completed"
    assert progress.failed == 0
    assert progress.completed == 5

    project = projects.load()
    outcomes = []
    for page in project.pages:
        result = projects.load_page_result(page.page_id)
        assert result is not None
        attempt = result.active_attempt()
        assert attempt is not None
        assert attempt.status == "succeeded"
        assert attempt.cleanup is not None
        outcomes.append(
            (
                attempt.cleanup.execution_status,
                attempt.cleanup.acceptance_status,
                attempt.cleanup.note,
            )
        )

    assert outcomes[0][1] == "applied"
    assert outcomes[1][1] == "unchanged"
    assert outcomes[2][1] == "validator_rejected"
    assert outcomes[3][0] == "skipped_empty_source"
    assert outcomes[4][0] == "provider_failed"
    assert outcomes[4][2] == "timeout"
    # empty source must not call generate
    assert cleanup.generate_calls == 4  # apply, unchanged, reject, fail — not empty


def test_cleanup_fail_fast_empty_model(tmp_path: Path):
    paths = open_project_paths(tmp_path / "proj")
    clock, ids = FakeClock(), SequentialIds()
    projects = ProjectService(paths, clock=clock, ids=ids)
    projects.create("t")
    ingest = IngestService(paths, clock=clock, ids=ids)
    ingest.import_bytes("p.png", _png_bytes())
    project = projects.load()
    settings = project.settings
    settings.model_name = "fake-vision"
    settings.cleanup_enabled = True
    settings.cleanup_mode = "strip_leak"
    settings.cleanup_model_name = ""
    settings.text_model_name = ""
    projects.save_settings(project, settings)
    coord = JobCoordinator(
        paths,
        projects,
        FakeVisionOCRProvider(),
        clock=clock,
        ids=ids,
        cleanup_client=CountingCleanupClient(responses={}, digest="d"),
    )
    with pytest.raises(TranscribeError):
        coord.run_blocking()


def test_cleanup_fail_fast_unsuitable_model(tmp_path: Path):
    paths = open_project_paths(tmp_path / "proj")
    clock, ids = FakeClock(), SequentialIds()
    projects = ProjectService(paths, clock=clock, ids=ids)
    projects.create("t")
    ingest = IngestService(paths, clock=clock, ids=ids)
    ingest.import_bytes("p.png", _png_bytes())
    project = projects.load()
    settings = project.settings
    settings.model_name = "fake-vision"
    settings.cleanup_enabled = True
    settings.cleanup_model_name = "llava:latest"
    projects.save_settings(project, settings)
    coord = JobCoordinator(
        paths,
        projects,
        FakeVisionOCRProvider(),
        clock=clock,
        ids=ids,
        cleanup_client=CountingCleanupClient(responses={}, digest="d"),
    )
    with pytest.raises(TranscribeError):
        coord.run_blocking()


def test_plan_freezes_cleanup_identity(tmp_path: Path):
    paths = open_project_paths(tmp_path / "proj")
    clock, ids = FakeClock(), SequentialIds()
    projects = ProjectService(paths, clock=clock, ids=ids)
    projects.create("t")
    ingest = IngestService(paths, clock=clock, ids=ids)
    ingest.import_bytes("p.png", _png_bytes())
    _enable_cleanup(projects, mode="strip_leak")
    cleanup = CountingCleanupClient(
        responses={"default": CLEAN_PAGE},
        digest="fixed-digest",
    )
    provider = FakeVisionOCRProvider(default_text=CLEAN_PAGE)
    coord = JobCoordinator(
        paths, projects, provider, clock=clock, ids=ids, cleanup_client=cleanup
    )
    project = projects.load()
    plan = coord._build_plan(
        project, job_id="j1", page_ids=None, force=False, provider=provider
    )
    assert plan.cleanup.enabled
    assert plan.cleanup.mode == "strip_leak"
    assert plan.cleanup.model_digest == "fixed-digest"
    frozen_fp = plan.config_fingerprint

    # Mid-job settings change must not alter an already-built plan object.
    settings = project.settings
    settings.cleanup_mode = "rewrite"
    projects.save_settings(project, settings)
    assert plan.cleanup.mode == "strip_leak"
    assert plan.config_fingerprint == frozen_fp

    plan2 = coord._build_plan(
        projects.load(), job_id="j2", page_ids=None, force=False, provider=provider
    )
    assert plan2.cleanup.mode == "rewrite"
    assert plan2.config_fingerprint != frozen_fp


def test_settings_persistence_roundtrip(tmp_path: Path):
    paths = open_project_paths(tmp_path / "proj")
    clock, ids = FakeClock(), SequentialIds()
    projects = ProjectService(paths, clock=clock, ids=ids)
    project = projects.create("t")
    settings = project.settings
    settings.cleanup_enabled = True
    settings.cleanup_mode = "sanitize_light"
    settings.cleanup_model_name = "llama3.2:3b"
    projects.save_settings(project, settings)
    loaded = projects.load().settings
    assert loaded.cleanup_enabled is True
    assert loaded.cleanup_mode == "sanitize_light"
    assert loaded.cleanup_model_name == "llama3.2:3b"


def test_adapter_sees_cleaned_text_when_applied(tmp_path: Path):
    paths = open_project_paths(tmp_path / "proj")
    clock, ids = FakeClock(), SequentialIds()
    projects = ProjectService(paths, clock=clock, ids=ids)
    projects.create("t")
    ingest = IngestService(paths, clock=clock, ids=ids)
    ingest.import_bytes("p.png", _png_bytes())
    leaked = (
        "- Do not change the order of words in sentences\n---\n" + CLEAN_PAGE
    )
    provider = FakeVisionOCRProvider(text_by_call=[leaked])
    cleanup = CountingCleanupClient(
        responses={"default": CLEAN_PAGE},
        digest="fixed-digest",
    )
    _enable_cleanup(projects)
    coord = JobCoordinator(
        paths, projects, provider, clock=clock, ids=ids, cleanup_client=cleanup
    )
    coord.run_blocking()
    project = projects.load()
    doc = build_page_v1_document(project, projects)
    assert CLEAN_PAGE in doc.text
    assert "Do not change" not in doc.text
    attempt = projects.load_page_result(project.pages[0].page_id).active_attempt()
    assert attempt.cleanup.acceptance_status == "applied"
    assert attempt.cleanup.pre_cleanup_text == leaked


def test_cli_cleanup_requires_flag(tmp_path: Path, monkeypatch):
    from transcribe.__main__ import main

    paths = open_project_paths(tmp_path / "cli")
    clock, ids = FakeClock(), SequentialIds()
    projects = ProjectService(paths, clock=clock, ids=ids)
    projects.create("t")
    code = main(
        [
            "run",
            str(paths.root),
            "--model",
            "fake-vision",
            "--cleanup-mode",
            "strip_leak",
        ]
    )
    assert code == 2
