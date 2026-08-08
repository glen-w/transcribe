"""Offline tests for Wave 1 analysis adapter/runner/storage."""

from __future__ import annotations

from pathlib import Path

from transcribe.analysis.adapter import build_page_v1_document
from transcribe.analysis.document import AnalysisUnit, content_fingerprint, validate_analysis_document
from transcribe.analysis.eligibility import evaluate_notebook_eligibility_v1
from transcribe.analysis.runner import AnalysisRunner
from transcribe.analysis.storage import AnalysisStorage
from transcribe.ingest import IngestService
from transcribe.paths import ProjectPaths
from transcribe.services.job import JobCoordinator
from transcribe.services.project import ProjectService, open_project_paths
from tests.conftest import FakeClock, SequentialIds
from tests.fakes import FakeVisionOCRProvider
from tests.ingest.test_ingest import _png_bytes


def _transcribed_project(tmp_path: Path, n_pages: int = 2):
    paths = open_project_paths(tmp_path / "proj")
    clock, ids = FakeClock(), SequentialIds("an")
    projects = ProjectService(paths, clock=clock, ids=ids)
    projects.create("analysis-probe")
    ingest = IngestService(paths, clock=clock, ids=ids)
    for i in range(n_pages):
        ingest.import_bytes(f"p{i}.png", _png_bytes(color=(i * 20, 40, 60)))
    project = projects.load()
    settings = project.settings
    settings.model_name = "fake-vision"
    projects.save_settings(project, settings)
    texts = [
        "alpha beta gamma delta epsilon",
        "alpha beta zeta eta theta iota",
    ]
    provider = FakeVisionOCRProvider(text_by_call=texts[:n_pages])
    JobCoordinator(paths, projects, provider, clock=clock, ids=ids).run_blocking()
    return paths, projects, clock, ids


def test_ensure_layout_does_not_create_analysis_dir(tmp_path: Path):
    paths = ProjectPaths(tmp_path / "empty")
    paths.ensure_layout()
    assert paths.analysis_dir.exists() is False


def test_stats_run_publishes_under_analysis_and_cache_hits(tmp_path: Path):
    paths, projects, clock, ids = _transcribed_project(tmp_path)
    assert not paths.analysis_dir.exists()
    runner = AnalysisRunner(projects, clock=clock, ids=ids)
    first = runner.run_module("stats")
    assert first["attempt_state"] == "succeeded"
    assert first["outcome"] == "success"
    assert first["project_id"] == projects.load().id
    assert paths.analysis_dir.is_dir()
    published = AnalysisStorage(paths).read_published("stats")
    assert published is not None
    assert published["cache_identity"] == first["cache_identity"]

    second = runner.run_module("stats")
    assert second["cache_identity"] == first["cache_identity"]
    assert second["attempt_id"] == first["attempt_id"]


def test_content_fingerprint_stable_for_same_document(tmp_path: Path):
    _paths, projects, _clock, _ids = _transcribed_project(tmp_path, n_pages=1)
    doc = build_page_v1_document(projects.load(), projects)
    validated = validate_analysis_document(doc)
    fp1 = content_fingerprint(validated)
    fp2 = content_fingerprint(validate_analysis_document(doc))
    assert fp1 == fp2
    assert len(fp1) == 64


def test_eligibility_marks_whitespace_unit_ineligible():
    units = [
        AnalysisUnit(
            unit_id="p1",
            text="ok text here",
            order=0,
            source_ref={"kind": "page", "page_id": "p1"},
        ),
        AnalysisUnit(
            unit_id="p2",
            text="  \n\t",
            order=1,
            source_ref={"kind": "page", "page_id": "p2"},
        ),
    ]
    out = evaluate_notebook_eligibility_v1(units, excluded_page_ids=set())
    assert out["eligible_unit_ids"] == ["p1"]
    reasons = {d["unit_id"]: d["reason"] for d in out["decisions"]}
    assert reasons["p2"] == "empty_or_whitespace"
