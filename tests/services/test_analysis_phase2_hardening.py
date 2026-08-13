"""Phase 2 product hardening: AnalysisCoordinator + frozen AnalysisRunPlan."""

from __future__ import annotations

import time
from pathlib import Path

from PIL import Image

from transcribe.analysis.coordinator import AnalysisCoordinator
from transcribe.analysis.plan import (
    AnalysisRunPlan,
    build_analysis_run_plan,
    run_record_payload,
)
from transcribe.analysis.runner import AnalysisRunner
from transcribe.analysis.storage import AnalysisStorage
from transcribe.config.facade import require_operation_config
from transcribe.ingest import IngestService
from transcribe.persistence.locks import AnalysisLock, analysis_lock_held
from transcribe.services.project import ProjectService, open_project_paths
from tests.conftest import FakeClock, SequentialIds


def _png_bytes() -> bytes:
    from io import BytesIO

    img = Image.new("RGB", (32, 32), (10, 20, 30))
    buf = BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def _project_with_pages(tmp_path: Path, texts: list[str]):
    paths = open_project_paths(tmp_path / "proj")
    clock, ids = FakeClock(), SequentialIds("p2")
    projects = ProjectService(paths, clock=clock, ids=ids)
    projects.create("notebook")
    ingest = IngestService(paths, clock=clock, ids=ids)
    for i, _ in enumerate(texts):
        ingest.import_bytes(f"p{i}.png", _png_bytes())
    project = projects.load()
    for page, text in zip(project.pages, texts, strict=True):
        projects.save_user_edit(page.page_id, text)
    return projects, AnalysisRunner(projects, clock=clock, ids=ids), clock, ids


def test_frozen_config_survives_mid_run_settings_mutation(tmp_path: Path):
    projects, runner, clock, ids = _project_with_pages(
        tmp_path,
        [
            "Frozen config notebook text with enough content for stats and lexical.",
            "Second page also has sufficient content for diversity metrics here.",
        ],
    )
    plan = build_analysis_run_plan(
        project_service=projects,
        module_ids=["stats", "lexical_diversity"],
        clock=clock,
        ids=ids,
    )
    seen_cfg: list[dict] = []
    original_run = runner._run_module_unlocked
    mutated = {"done": False}

    def wrapped(module, *, project, question_text, **kwargs):
        if not mutated["done"]:
            mutated["done"] = True
            settings = project.settings
            settings.model_name = "mutated-mid-run-model"
            projects.save_settings(project, settings)
            from transcribe.config.facade import clear_config_cache

            clear_config_cache()
        seen_cfg.append(require_operation_config().as_dict())
        return original_run(module, project=project, question_text=question_text, **kwargs)

    runner._run_module_unlocked = wrapped  # type: ignore[method-assign]
    results = runner.run_batch_from_plan(plan)
    assert set(results) == {"stats", "lexical_diversity"}
    assert len(seen_cfg) == 2
    assert seen_cfg[0] == seen_cfg[1] == plan.effective_config.as_dict()
    # Disk settings changed after plan freeze.
    assert projects.load(reconcile=False).settings.model_name == "mutated-mid-run-model"


def test_async_coordinator_survives_without_ui_handles(tmp_path: Path):
    projects, _runner, clock, ids = _project_with_pages(
        tmp_path,
        ["Async survival text with enough words for a successful stats module run."],
    )
    coord = AnalysisCoordinator(projects, clock=clock, ids=ids)
    plan = build_analysis_run_plan(
        project_service=projects,
        module_ids=["stats", "lexical_diversity"],
        clock=clock,
        ids=ids,
    )
    run_id = coord.start(plan)
    assert run_id == plan.run_id
    # Drop UI-like handles; only coordinator reference remains.
    deadline = time.time() + 30
    while coord.is_running() and time.time() < deadline:
        time.sleep(0.05)
    progress = coord.get_progress()
    assert progress.status == "completed"
    assert progress.completed + progress.failed + progress.skipped == progress.total
    storage = AnalysisStorage(projects.paths)
    published = storage.read_published("stats")
    assert published is not None
    assert published.get("outcome") == "success"
    record = storage.read_run_record(plan.run_id)
    assert record is not None
    assert record["status"] == "completed"
    assert record["format"] == "transcribe.analysis-run"


def test_crash_reopen_interrupts_attempt_and_run_without_clobber(tmp_path: Path):
    projects, runner, clock, ids = _project_with_pages(
        tmp_path,
        ["Published notebook text with sufficient content for stats module."],
    )
    published = runner.run_module("stats")
    assert published["outcome"] == "success"
    storage = AnalysisStorage(projects.paths)
    orphan = dict(published)
    orphan["attempt_id"] = "orphan-running"
    orphan["attempt_state"] = "running"
    orphan["published"] = False
    storage.write_attempt("stats", orphan)

    plan = build_analysis_run_plan(
        project_service=projects,
        module_ids=["stats"],
        clock=clock,
        ids=ids,
    )
    storage.write_run_record(
        run_record_payload(plan, status="running", message="crashed mid-flight")
    )
    before = storage.read_published("stats")
    projects.load(reconcile=True)
    after_attempt = storage.read_attempt("stats", "orphan-running")
    assert after_attempt["attempt_state"] == "interrupted"
    assert storage.read_published("stats")["cache_identity"] == before["cache_identity"]
    record = storage.read_run_record(plan.run_id)
    assert record is not None
    assert record["status"] == "interrupted"


def test_reconcile_noop_while_analysis_lock_held(tmp_path: Path):
    projects, runner, _clock, _ids = _project_with_pages(
        tmp_path,
        ["Lock gating text with enough content for stats publish path testing."],
    )
    published = runner.run_module("stats")
    storage = AnalysisStorage(projects.paths)
    orphan = dict(published)
    orphan["attempt_id"] = "still-running"
    orphan["attempt_state"] = "running"
    orphan["published"] = False
    storage.write_attempt("stats", orphan)

    lock = AnalysisLock(projects.paths.analysis_lock)
    assert lock.try_acquire()
    try:
        assert analysis_lock_held(projects.paths.analysis_lock) is True
        changed = storage.reconcile_interrupted()
        assert changed == []
        still = storage.read_attempt("stats", "still-running")
        assert still["attempt_state"] == "running"
    finally:
        lock.release()

    changed = storage.reconcile_interrupted()
    assert any("still-running" in c for c in changed)
    assert storage.read_attempt("stats", "still-running")["attempt_state"] == "interrupted"


def test_plan_roundtrip_and_module_order(tmp_path: Path):
    projects, _runner, clock, ids = _project_with_pages(
        tmp_path,
        ["Plan roundtrip notebook content suitable for entity sentiment parents."],
    )
    plan = build_analysis_run_plan(
        project_service=projects,
        module_ids=["entity_sentiment"],  # expands hard parents
        clock=clock,
        ids=ids,
    )
    assert "ner" in plan.module_ids
    assert "sentiment" in plan.module_ids
    assert plan.module_ids.index("ner") < plan.module_ids.index("entity_sentiment")
    restored = AnalysisRunPlan.from_dict(plan.as_dict())
    assert restored.run_id == plan.run_id
    assert restored.module_ids == plan.module_ids
    assert restored.config_fingerprint == plan.config_fingerprint
