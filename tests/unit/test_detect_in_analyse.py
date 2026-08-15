"""Detect integration into Analyse plans / presets / coordinators."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from transcribe.analysis.coordinator import AnalysisCoordinator
from transcribe.analysis.plan import (
    AnalysisRunPlan,
    build_analysis_run_plan,
    compute_plan_hash,
    verify_plan_hash,
)
from transcribe.analysis.presets import (
    BUILTIN_PRESET_POLICIES,
    compute_effective_modules,
    resolve_analysis_preset,
)
from transcribe.corpus.paths import CorpusPaths
from transcribe.ingest import IngestService
from transcribe.services.batch_analysis import (
    BatchAnalysisCoordinator,
    plan_template_hash,
)
from transcribe.services.project import ProjectService, open_project_paths
from tests.conftest import FakeClock, SequentialIds
from tests.ingest.test_ingest import _png_bytes


def _notebook(tmp_path: Path, name: str = "nb") -> tuple[ProjectService, FakeClock, SequentialIds]:
    clock, ids = FakeClock(), SequentialIds("det")
    root = tmp_path / name
    projects = ProjectService(open_project_paths(root), clock=clock, ids=ids)
    projects.create(name)
    ingest = IngestService(open_project_paths(root), clock=clock, ids=ids)
    ingest.import_bytes(f"{name}.png", _png_bytes())
    project = projects.load()
    for page in project.pages:
        projects.save_user_edit(page.page_id, "Some notebook text for analysis and detection.")
    return projects, clock, ids


def test_thorough_preset_includes_detectors_quick_does_not():
    assert BUILTIN_PRESET_POLICIES["thorough"].allow_detection is True
    assert BUILTIN_PRESET_POLICIES["quick"].allow_detection is False
    assert BUILTIN_PRESET_POLICIES["balanced"].allow_detection is False

    thorough = resolve_analysis_preset("thorough")
    quick = resolve_analysis_preset("quick")
    assert thorough.detector_ids
    assert "poetry" in thorough.detector_ids
    assert quick.detector_ids == ()


def test_custom_detector_only_preset():
    resolved = resolve_analysis_preset(
        "custom",
        custom_modules=[],
        custom_detectors=["poetry"],
    )
    assert resolved.module_ids == ()
    assert resolved.detector_ids == ("poetry",)
    plan = compute_effective_modules(resolved, custom_qa_execution=False)
    assert plan.needs_llm() is True
    assert plan.detector_count == 1


def test_plan_hash_includes_detector_ids(tmp_path: Path):
    projects, clock, ids = _notebook(tmp_path)
    base = build_analysis_run_plan(
        project_service=projects,
        module_ids=["stats"],
        clock=clock,
        ids=ids,
    )
    with_det = build_analysis_run_plan(
        project_service=projects,
        module_ids=["stats"],
        detector_ids=["poetry"],
        clock=clock,
        ids=ids,
    )
    assert base.plan_hash != with_det.plan_hash
    assert with_det.detector_ids == ("poetry",)
    assert with_det.needs_llm() is True
    restored = AnalysisRunPlan.from_dict(with_det.as_dict())
    assert restored.detector_ids == ("poetry",)
    assert verify_plan_hash(restored)
    assert compute_plan_hash(restored) == with_det.plan_hash


def test_plan_from_dict_defaults_missing_detectors(tmp_path: Path):
    projects, clock, ids = _notebook(tmp_path)
    plan = build_analysis_run_plan(
        project_service=projects,
        module_ids=["stats"],
        clock=clock,
        ids=ids,
    )
    raw = plan.as_dict()
    del raw["detector_ids"]
    restored = AnalysisRunPlan.from_dict(raw)
    assert restored.detector_ids == ()


def test_detector_only_plan_allowed(tmp_path: Path):
    projects, clock, ids = _notebook(tmp_path)
    plan = build_analysis_run_plan(
        project_service=projects,
        module_ids=[],
        detector_ids=["poetry"],
        clock=clock,
        ids=ids,
    )
    assert plan.module_ids == ()
    assert plan.detector_ids == ("poetry",)
    assert plan.step_total() == 1


def test_coordinator_runs_detectors_after_modules(tmp_path: Path):
    projects, clock, ids = _notebook(tmp_path)
    plan = build_analysis_run_plan(
        project_service=projects,
        module_ids=["stats"],
        detector_ids=["poetry"],
        clock=clock,
        ids=ids,
    )
    coord = AnalysisCoordinator(projects, clock=clock, ids=ids)
    called: list[str] = []

    def fake_run_detector(detector_id, **kwargs):
        called.append(detector_id)
        return {"outcome": "success", "capability": "ok", "findings": []}

    with patch(
        "transcribe.detection.api.DetectionService.run_detector",
        side_effect=fake_run_detector,
    ):
        progress = coord.run_blocking(plan)
    assert progress.status == "completed"
    assert "poetry" in called
    assert progress.total == plan.step_total()
    assert "poetry" in progress.module_outcomes
    assert "stats" in progress.module_outcomes


def test_coordinator_detector_only(tmp_path: Path):
    projects, clock, ids = _notebook(tmp_path)
    plan = build_analysis_run_plan(
        project_service=projects,
        module_ids=[],
        detector_ids=["poetry", "lists"],
        clock=clock,
        ids=ids,
    )
    coord = AnalysisCoordinator(projects, clock=clock, ids=ids)

    with patch(
        "transcribe.detection.api.DetectionService.run_detector",
        return_value={"outcome": "success", "capability": "ok"},
    ) as mock_run:
        progress = coord.run_blocking(plan)
    assert progress.status == "completed"
    assert mock_run.call_count == 2
    assert progress.completed == 2


def test_batch_create_run_persists_detectors(tmp_path: Path):
    corpus = CorpusPaths(data_dir=tmp_path / "data", projects_dir=tmp_path / "projects")
    corpus.projects_dir.mkdir(parents=True)
    corpus.ensure_layout()
    clock, ids = FakeClock(), SequentialIds("batch")
    root = corpus.projects_dir / "one"
    projects = ProjectService(open_project_paths(root), clock=clock, ids=ids)
    projects.create("one")
    ingest = IngestService(open_project_paths(root), clock=clock, ids=ids)
    ingest.import_bytes("one.png", _png_bytes())
    project = projects.load()
    for page in project.pages:
        projects.save_user_edit(page.page_id, "Some notebook text for analysis and detection.")
    from transcribe.services.batch_notebooks import NotebookCandidate

    coord = BatchAnalysisCoordinator(corpus, clock=clock, ids=ids)
    candidates = [
        NotebookCandidate(
            notebook_id=project.id,
            title="one",
            managed_relpath="",
            root=root,
            pages_total=1,
            pages_pending=0,
        )
    ]
    run = coord.create_run(
        candidates,
        module_ids=["stats"],
        detector_ids=["poetry"],
        seed_project=projects,
    )
    assert run.detector_ids == ["poetry"]
    assert run.module_ids == ["stats"]
    loaded = coord.store.load(run.analysis_batch_id)
    assert loaded.detector_ids == ["poetry"]
    tmpl = plan_template_hash(
        module_ids=run.module_ids,
        detector_ids=run.detector_ids,
        question_text=run.question_text,
        effective_config=run.effective_config,
        config_fingerprint=run.config_fingerprint,
        text_model=run.text_model,
        preset_key=run.preset_key,
        preset_content_version=run.preset_content_version,
        preset_policy_fingerprint=run.preset_policy_fingerprint,
    )
    assert tmpl == run.plan_template_hash


def test_batch_detector_only_create_run(tmp_path: Path):
    corpus = CorpusPaths(data_dir=tmp_path / "data", projects_dir=tmp_path / "projects")
    corpus.projects_dir.mkdir(parents=True)
    corpus.ensure_layout()
    clock, ids = FakeClock(), SequentialIds("batch2")
    root = corpus.projects_dir / "solo"
    projects = ProjectService(open_project_paths(root), clock=clock, ids=ids)
    projects.create("solo")
    ingest = IngestService(open_project_paths(root), clock=clock, ids=ids)
    ingest.import_bytes("solo.png", _png_bytes())
    project = projects.load()
    for page in project.pages:
        projects.save_user_edit(page.page_id, "Text for detector-only batch.")
    from transcribe.services.batch_notebooks import NotebookCandidate

    coord = BatchAnalysisCoordinator(corpus, clock=clock, ids=ids)
    candidates = [
        NotebookCandidate(
            notebook_id=project.id,
            title="solo",
            managed_relpath="",
            root=root,
            pages_total=1,
            pages_pending=0,
        )
    ]
    run = coord.create_run(
        candidates,
        module_ids=[],
        detector_ids=["poetry"],
        seed_project=projects,
    )
    assert run.module_ids == []
    assert run.detector_ids == ["poetry"]
    assert run.items[0].modules_total == 1
