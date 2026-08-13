"""Bulk Analyse selection, resume, cancel, and progress (offline)."""

from __future__ import annotations

from pathlib import Path

import pytest

from transcribe.corpus.analysis_batch_run import (
    AnalysisBatchItem,
    AnalysisBatchRun,
    AnalysisBatchRunStore,
    finalize_analysis_batch_status,
)
from transcribe.corpus.paths import CorpusPaths
from transcribe.errors import JobConflictError, ValidationError
from transcribe.ingest import IngestService
from transcribe.services.batch_analysis import (
    BatchAnalysisCoordinator,
    BatchAnalysisProgress,
    list_analysis_candidates,
    plan_template_hash,
    select_needing_analysis,
)
from transcribe.services.batch_notebooks import select_by_ids, select_pending
from transcribe.services.project import ProjectService, open_project_paths
from tests.conftest import FakeClock, SequentialIds
from tests.ingest.test_ingest import _png_bytes


def _corpus(tmp_path: Path) -> CorpusPaths:
    paths = CorpusPaths(data_dir=tmp_path / "data", projects_dir=tmp_path / "projects")
    paths.projects_dir.mkdir(parents=True)
    paths.ensure_layout()
    return paths


def _make_notebook(
    corpus: CorpusPaths,
    name: str,
    *,
    clock: FakeClock,
    ids: SequentialIds,
    texts: list[str] | None = None,
) -> Path:
    root = corpus.projects_dir / name
    projects = ProjectService(open_project_paths(root), clock=clock, ids=ids)
    projects.create(name)
    ingest = IngestService(open_project_paths(root), clock=clock, ids=ids)
    page_texts = texts if texts is not None else [
        f"Enough notebook text for analysis in {name}. "
        "Stats and lexical diversity need a few sentences of content."
    ]
    for i, text in enumerate(page_texts):
        ingest.import_bytes(f"{name}-{i}.png", _png_bytes(color=(i + 1, 40, 50)))
    project = projects.load()
    for page, text in zip(project.pages, page_texts, strict=False):
        if text:
            projects.save_user_edit(page.page_id, text)
    return root


def test_select_needing_analysis_requires_text_and_missing_health(tmp_path: Path) -> None:
    corpus = _corpus(tmp_path)
    clock, ids = FakeClock(), SequentialIds("sel")
    _make_notebook(corpus, "needs", clock=clock, ids=ids)
    empty = _make_notebook(corpus, "empty", clock=clock, ids=ids, texts=[""])
    # empty text edit still creates a page; clear by not saving text — use blank
    projects = ProjectService(open_project_paths(empty), clock=clock, ids=ids)
    project = projects.load()
    for page in project.pages:
        projects.save_user_edit(page.page_id, "   ")

    candidates = list_analysis_candidates(corpus, clock=clock, ids=ids)
    needing = select_needing_analysis(candidates)
    assert {c.title for c in needing} == {"needs"}
    # OCR pending still sees both (no OCR succeeded)
    assert len(select_pending(candidates)) == 2


def test_batch_analysis_runs_two_notebooks(tmp_path: Path) -> None:
    corpus = _corpus(tmp_path)
    clock, ids = FakeClock(), SequentialIds("bat")
    _make_notebook(corpus, "alpha", clock=clock, ids=ids)
    _make_notebook(corpus, "beta", clock=clock, ids=ids)
    coord = BatchAnalysisCoordinator(corpus, clock=clock, ids=ids)
    selected = select_needing_analysis(
        list_analysis_candidates(corpus, clock=clock, ids=ids)
    )
    run = coord.create_run(selected, module_ids=["stats", "lexical_diversity"])
    progress = coord.run_blocking(run.analysis_batch_id)
    assert progress.status == "completed"
    stored = AnalysisBatchRunStore(corpus).load(run.analysis_batch_id)
    assert all(i.state == "completed" for i in stored.items)
    assert all(i.inner_run_id for i in stored.items)
    assert stored.plan_template_hash
    assert stored.module_ids[0] == "stats"

    # Resume should be a no-op (already terminal completed items)
    resumed = coord.resume(run.analysis_batch_id, blocking=True)
    assert resumed.status == "completed"


def test_batch_analysis_skips_empty_text(tmp_path: Path) -> None:
    corpus = _corpus(tmp_path)
    clock, ids = FakeClock(), SequentialIds("skp")
    _make_notebook(corpus, "with-text", clock=clock, ids=ids)
    empty_root = corpus.projects_dir / "no-text"
    projects = ProjectService(open_project_paths(empty_root), clock=clock, ids=ids)
    projects.create("no-text")
    IngestService(open_project_paths(empty_root), clock=clock, ids=ids).import_bytes(
        "blank.png", _png_bytes()
    )

    coord = BatchAnalysisCoordinator(corpus, clock=clock, ids=ids)
    candidates = list_analysis_candidates(corpus, clock=clock, ids=ids)
    selected = select_by_ids(candidates, [c.notebook_id for c in candidates])
    run = coord.create_run(selected, module_ids=["stats"])
    progress = coord.run_blocking(run.analysis_batch_id)
    stored = AnalysisBatchRunStore(corpus).load(run.analysis_batch_id)
    states = {i.title: i.state for i in stored.items}
    assert states["with-text"] == "completed"
    assert states["no-text"] == "skipped"
    assert progress.status == "completed"


def test_batch_analysis_cancel_does_not_start_next(tmp_path: Path) -> None:
    from transcribe.analysis.coordinator import AnalysisCoordinator

    corpus = _corpus(tmp_path)
    clock, ids = FakeClock(), SequentialIds("can")
    _make_notebook(corpus, "first", clock=clock, ids=ids)
    _make_notebook(corpus, "second", clock=clock, ids=ids)

    coord = BatchAnalysisCoordinator(corpus, clock=clock, ids=ids)
    selected = select_needing_analysis(
        list_analysis_candidates(corpus, clock=clock, ids=ids)
    )
    run = coord.create_run(selected, module_ids=["stats", "lexical_diversity"])

    orig = AnalysisCoordinator.run_blocking

    def run_then_cancel(self, plan, *, on_progress=None):
        result = orig(self, plan, on_progress=on_progress)
        coord.request_cancel()
        return result

    AnalysisCoordinator.run_blocking = run_then_cancel  # type: ignore[method-assign]
    try:
        progress = coord.run_blocking(run.analysis_batch_id)
    finally:
        AnalysisCoordinator.run_blocking = orig  # type: ignore[method-assign]
    stored = AnalysisBatchRunStore(corpus).load(run.analysis_batch_id)
    states = [i.state for i in stored.items]
    assert "cancelled" in states
    assert states.count("completed") == 1
    assert progress.status in {"cancelled", "partial"}


def test_create_run_requires_modules_and_notebooks(tmp_path: Path) -> None:
    corpus = _corpus(tmp_path)
    coord = BatchAnalysisCoordinator(corpus, clock=FakeClock(), ids=SequentialIds("req"))
    with pytest.raises(ValidationError, match="at least one"):
        coord.create_run([], module_ids=["stats"])
    clock, ids = FakeClock(), SequentialIds("req2")
    _make_notebook(corpus, "nb", clock=clock, ids=ids)
    selected = list_analysis_candidates(corpus, clock=clock, ids=ids)
    with pytest.raises(ValidationError, match="at least one module"):
        coord.create_run(selected, module_ids=[])


def test_job_conflict_on_second_start(tmp_path: Path) -> None:
    corpus = _corpus(tmp_path)
    clock, ids = FakeClock(), SequentialIds("cfl")
    _make_notebook(corpus, "nb", clock=clock, ids=ids)
    coord = BatchAnalysisCoordinator(corpus, clock=clock, ids=ids)
    selected = list_analysis_candidates(corpus, clock=clock, ids=ids)
    run = coord.create_run(selected, module_ids=["stats"])

    import threading
    import time

    barrier = threading.Event()

    def blocker(state):
        barrier.wait(timeout=5)

    coord._run_batch = blocker  # type: ignore[method-assign]
    coord.start(run.analysis_batch_id)
    try:
        with pytest.raises(JobConflictError):
            coord.start(run.analysis_batch_id)
    finally:
        barrier.set()
        time.sleep(0.05)


def test_finalize_status_partial_when_cancelled_after_success() -> None:
    run = AnalysisBatchRun(
        analysis_batch_id="r1",
        created_at="t",
        updated_at="t",
        status="running",
        module_ids=["stats"],
        items=[
            AnalysisBatchItem(notebook_id="a", state="completed"),
            AnalysisBatchItem(notebook_id="b", state="cancelled"),
        ],
    )
    assert finalize_analysis_batch_status(run) == "partial"


def test_analysis_batch_run_round_trip(tmp_path: Path) -> None:
    corpus = _corpus(tmp_path)
    tmpl = plan_template_hash(
        module_ids=["stats"],
        question_text=None,
        effective_config={},
        config_fingerprint="fp",
        text_model=None,
        preset_key="quick",
        preset_content_version=1,
        preset_policy_fingerprint="pol",
    )
    run = AnalysisBatchRun(
        analysis_batch_id="r-ab",
        created_at="t",
        updated_at="t",
        status="pending",
        module_ids=["stats", "lexical_diversity"],
        plan_template_hash=tmpl,
        config_fingerprint="fp",
        preset_key="quick",
        preset_content_version=1,
        preset_policy_fingerprint="pol",
        items=[
            AnalysisBatchItem(
                notebook_id="a", state="pending", modules_total=2, inner_run_id="inner-1"
            ),
        ],
    )
    store = AnalysisBatchRunStore(corpus)
    store.save(run)
    loaded = store.load("r-ab")
    assert loaded.module_ids == ["stats", "lexical_diversity"]
    assert loaded.plan_template_hash == tmpl
    assert loaded.items[0].inner_run_id == "inner-1"
    assert loaded.preset_key == "quick"


def test_progress_snapshot_maps_modules() -> None:
    from transcribe.ui.run_analysis_batch import batch_analysis_progress_to_snapshot

    snap = batch_analysis_progress_to_snapshot(
        BatchAnalysisProgress(
            analysis_batch_id="x",
            status="running",
            total=3,
            completed=1,
            failed=0,
            skipped=0,
            current_item="2/3 · beta",
            current_module_id="stats",
            modules_completed=2,
            modules_failed=0,
            modules_skipped=1,
            modules_total=5,
            message="Running stats (3/5)…",
        )
    )
    assert snap["current_item"] == "2/3 · beta"
    assert snap["detail_unit"] == "modules in this notebook"
    assert snap["detail_total"] == 5
    assert snap["detail_completed"] == 2
    assert snap["detail_current"] == "stats"
    assert snap["completed"] == 1
    assert 0 < snap["pct"] < 100
