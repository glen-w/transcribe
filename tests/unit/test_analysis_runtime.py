"""Offline tests for analysis adapter/runner/storage."""

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


def test_module_freshness_matches_planned_identity(tmp_path: Path):
    from transcribe.analysis.runner import module_freshness

    paths, projects, clock, ids = _transcribed_project(tmp_path, n_pages=1)
    runner = AnalysisRunner(projects, clock=clock, ids=ids)
    storage = AnalysisStorage(paths)
    env = runner.run_module("stats")
    models = module_freshness(runner, storage, ["stats"])
    assert len(models) == 1
    assert models[0]["status"] == "ok"
    assert models[0]["envelope"]["cache_identity"] == env["cache_identity"]

    page_id = projects.load().pages[0].page_id
    projects.save_user_edit(page_id, "edited text makes published stats stale for freshness")
    stale = module_freshness(runner, storage, ["stats"])
    assert stale[0]["status"] == "stale"


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


def test_effective_text_prefers_edit_over_raw_for_fingerprint(tmp_path: Path):
    paths, projects, clock, ids = _transcribed_project(tmp_path, n_pages=1)
    page_id = projects.load().pages[0].page_id
    doc_raw = build_page_v1_document(projects.load(), projects)
    fp_raw = content_fingerprint(doc_raw)
    projects.save_user_edit(page_id, "edited supersedes raw text for analysis fingerprint")
    doc_edit = build_page_v1_document(projects.load(), projects)
    assert doc_edit.units[0].text.startswith("edited supersedes")
    assert content_fingerprint(doc_edit) != fp_raw


def test_text_edit_invalidates_cache_identity(tmp_path: Path):
    paths, projects, clock, ids = _transcribed_project(tmp_path, n_pages=1)
    runner = AnalysisRunner(projects, clock=clock, ids=ids)
    first = runner.run_module("stats")
    page_id = projects.load().pages[0].page_id
    projects.save_user_edit(page_id, "brand new edited notebook page text for invalidation")
    second = runner.run_module("stats")
    assert second["cache_identity"] != first["cache_identity"]
    assert second["attempt_id"] != first["attempt_id"]


def test_cache_hit_refuses_module_version_mismatch(tmp_path: Path):
    from transcribe.analysis.cache_identity import (
        build_cache_identity_object,
        cache_identity_hex,
    )
    from transcribe.persistence.atomic import write_json_atomic

    paths, projects, clock, ids = _transcribed_project(tmp_path, n_pages=1)
    runner = AnalysisRunner(projects, clock=clock, ids=ids)
    env = runner.run_module("stats")
    storage = AnalysisStorage(paths)
    # Tamper published module_version
    published = dict(storage.read_published("stats"))
    published["module_version"] = "0.0.0-tampered"
    write_json_atomic(storage.published_path("stats"), published)
    hit = storage.validate_cache_hit(
        module_id="stats",
        expected_cache_identity=env["cache_identity"],
        expected_module_version="1.1.0",
    )
    assert hit is None
    # Runner must recompute a new attempt rather than reuse tampered publish
    again = runner.run_module("stats")
    assert again["module_version"] == "1.1.0"
    assert again["attempt_id"] != env["attempt_id"]


def test_cache_identity_includes_required_fields(tmp_path: Path):
    from transcribe.analysis.cache_identity import build_cache_identity_object

    _paths, projects, _clock, _ids = _transcribed_project(tmp_path, n_pages=1)
    doc = build_page_v1_document(projects.load(), projects)
    obj = build_cache_identity_object(
        project_id=projects.load().id,
        module_id="stats",
        module_version="1.1.0",
        document=doc,
    )
    for key in (
        "cache_identity_version",
        "project_id",
        "module_id",
        "module_version",
        "content_fingerprint",
        "content_fingerprint_version",
        "adapter_version",
        "granularity_version",
        "split_profile",
        "config_fingerprint",
        "parents",
    ):
        assert key in obj
    assert obj["granularity_version"] == "page_v1"
    assert obj["split_profile"] == "page"


def test_unit_date_day_precision_only(tmp_path: Path):
    from transcribe.domain.dates import ApproximateDate
    from transcribe.persistence.atomic import read_json, write_json_atomic
    from transcribe.persistence.locks import mutation_lock
    from transcribe.persistence.schema import require_format
    from transcribe.domain.models import Project

    _paths, projects, _clock, _ids = _transcribed_project(tmp_path, n_pages=1)
    with mutation_lock(projects.paths.mutation_lock):
        payload = require_format(read_json(projects.paths.manifest), "transcribe.project")
        current = Project.from_dict(payload)
        current.pages[0].date = ApproximateDate(year=2024, month=6, day=15)
        write_json_atomic(projects.paths.manifest, current.as_dict())
    doc = build_page_v1_document(projects.load(), projects)
    assert doc.units[0].date == "2024-06-15"

    with mutation_lock(projects.paths.mutation_lock):
        payload = require_format(read_json(projects.paths.manifest), "transcribe.project")
        current = Project.from_dict(payload)
        current.pages[0].date = ApproximateDate(year=2024, month=6)
        write_json_atomic(projects.paths.manifest, current.as_dict())
    doc2 = build_page_v1_document(projects.load(), projects)
    assert doc2.units[0].date is None


def test_surrogate_rejection():
    import pytest
    from transcribe.analysis.document import AnalysisDocument, AnalysisDocumentError

    bad = AnalysisDocument(
        document_id="p",
        text="a\ud800b",
        units=[
            AnalysisUnit(
                unit_id="u1",
                text="a\ud800b",
                order=0,
                source_ref={"kind": "page", "page_id": "u1"},
            )
        ],
    )
    with pytest.raises(AnalysisDocumentError) as ei:
        validate_analysis_document(bad)
    assert ei.value.code == "invalid_text"


def test_lexical_partial_when_below_mtld_threshold(tmp_path: Path):
    paths, projects, clock, ids = _transcribed_project(tmp_path, n_pages=1)
    # Override with short but tokenizable text (< 50 tokens)
    page_id = projects.load().pages[0].page_id
    projects.save_user_edit(
        page_id, "short alpha beta gamma delta epsilon zeta eta"
    )
    runner = AnalysisRunner(projects, clock=clock, ids=ids)
    env = runner.run_module("lexical_diversity")
    assert env["outcome"] == "success"
    assert env.get("partial") is True
    assert "mtld" not in env["payload"]["document"]
    assert any(w["code"] == "below_mtld_threshold" for w in env["warnings"])
