"""Bulk Analyse selection, resume, cancel, and progress (offline)."""

from __future__ import annotations

from pathlib import Path

import pytest

from transcribe.analysis.coordinator import AnalysisCoordinator, AnalysisProgress
from transcribe.corpus.analysis_batch_run import (
    AnalysisBatchItem,
    AnalysisBatchRun,
    AnalysisBatchRunStore,
    finalize_analysis_batch_status,
)
from transcribe.corpus.paths import CorpusPaths
from transcribe.errors import CorpusError, JobConflictError, ValidationError
from transcribe.ingest import IngestService
from transcribe.services.batch_analysis import (
    BatchAnalysisCoordinator,
    BatchAnalysisProgress,
    list_analysis_candidates,
    plan_template_hash,
    select_needing_analysis,
)
from transcribe.services.batch_notebooks import (
    select_by_ids,
    select_from_import_run,
    select_pending,
)
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
    page_texts = (
        texts
        if texts is not None
        else [
            f"Enough notebook text for analysis in {name}. "
            "Stats and lexical diversity need a few sentences of content."
        ]
    )
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
    projects = ProjectService(open_project_paths(empty), clock=clock, ids=ids)
    project = projects.load()
    for page in project.pages:
        projects.save_user_edit(page.page_id, "   ")

    candidates = list_analysis_candidates(corpus, clock=clock, ids=ids)
    needing = select_needing_analysis(candidates)
    assert {c.title for c in needing} == {"needs"}
    # OCR pending still sees both (no OCR succeeded)
    assert len(select_pending(candidates)) == 2


def test_select_needing_analysis_excludes_healthy(tmp_path: Path) -> None:
    corpus = _corpus(tmp_path)
    clock, ids = FakeClock(), SequentialIds("hlt")
    _make_notebook(corpus, "fresh", clock=clock, ids=ids)
    _make_notebook(corpus, "stale-ish", clock=clock, ids=ids)
    coord = BatchAnalysisCoordinator(corpus, clock=clock, ids=ids)
    candidates = list_analysis_candidates(corpus, clock=clock, ids=ids)
    by_title = {c.title: c for c in candidates}
    # Analyse only "fresh" so it becomes healthy; leave other missing.
    run = coord.create_run([by_title["fresh"]], module_ids=["stats"])
    assert coord.run_blocking(run.analysis_batch_id).status == "completed"

    after = list_analysis_candidates(corpus, clock=clock, ids=ids)
    needing = select_needing_analysis(after)
    titles = {c.title for c in needing}
    assert "fresh" not in titles
    assert "stale-ish" in titles


def test_select_from_import_run_and_by_ids(tmp_path: Path) -> None:
    from transcribe.corpus.import_run import ImportRun, ImportRunItemOutcome, ImportRunStore
    from transcribe.corpus.plan import POLICY_SKIP_EXISTING_V1

    corpus = _corpus(tmp_path)
    clock, ids = FakeClock(), SequentialIds("imp")
    _make_notebook(corpus, "kept", clock=clock, ids=ids)
    _make_notebook(corpus, "skipped-nb", clock=clock, ids=ids)
    candidates = list_analysis_candidates(corpus, clock=clock, ids=ids)
    by_title = {c.title: c for c in candidates}
    run = ImportRun(
        import_run_id="imprun-ax",
        plan_id="plan1",
        plan_fingerprint="a" * 64,
        import_policy_id=POLICY_SKIP_EXISTING_V1,
        created_at="2026-01-01T00:00:00+00:00",
        updated_at="2026-01-01T00:00:00+00:00",
        status="complete",
        items=[
            ImportRunItemOutcome(
                item_id="i1",
                state="committed",
                resulting_ids={"notebook_id": by_title["kept"].notebook_id},
            ),
            ImportRunItemOutcome(
                item_id="i2",
                state="skipped",
                resulting_ids={"notebook_id": by_title["skipped-nb"].notebook_id},
            ),
        ],
    )
    ImportRunStore(corpus).save(run)
    selected = select_from_import_run(corpus, "imprun-ax", candidates, purpose="analyse")
    assert [c.title for c in selected] == ["kept"]
    ordered = select_by_ids(
        candidates,
        [by_title["skipped-nb"].notebook_id, by_title["kept"].notebook_id],
    )
    assert [c.title for c in ordered] == ["skipped-nb", "kept"]
    with pytest.raises(CorpusError, match="not found"):
        select_by_ids(candidates, ["missing-notebook-id"])


def test_batch_analysis_runs_two_notebooks(tmp_path: Path) -> None:
    corpus = _corpus(tmp_path)
    clock, ids = FakeClock(), SequentialIds("bat")
    _make_notebook(corpus, "alpha", clock=clock, ids=ids)
    _make_notebook(corpus, "beta", clock=clock, ids=ids)
    coord = BatchAnalysisCoordinator(corpus, clock=clock, ids=ids)
    selected = select_needing_analysis(list_analysis_candidates(corpus, clock=clock, ids=ids))
    run = coord.create_run(selected, module_ids=["stats", "lexical_diversity"])
    progress = coord.run_blocking(run.analysis_batch_id)
    assert progress.status == "completed"
    stored = AnalysisBatchRunStore(corpus).load(run.analysis_batch_id)
    assert all(i.state == "completed" for i in stored.items)
    assert all(i.inner_run_id for i in stored.items)
    assert all(i.modules_total >= 2 for i in stored.items)
    assert stored.plan_template_hash
    assert stored.module_ids[0] == "stats"

    # Published modules exist under each project
    for item in stored.items:
        root = corpus.resolve_managed(item.managed_relpath)
        assert (root / "analysis" / "stats" / "published.json").is_file()

    # Resume of completed run is a no-op
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
    assert progress.skipped >= 1


def test_one_notebook_fails_continues_partial(tmp_path: Path) -> None:
    corpus = _corpus(tmp_path)
    clock, ids = FakeClock(), SequentialIds("fail")
    _make_notebook(corpus, "bad", clock=clock, ids=ids)
    _make_notebook(corpus, "good", clock=clock, ids=ids)
    coord = BatchAnalysisCoordinator(corpus, clock=clock, ids=ids)
    selected = select_needing_analysis(list_analysis_candidates(corpus, clock=clock, ids=ids))
    # Stable discover order: bad, good
    run = coord.create_run(selected, module_ids=["stats"])

    orig = AnalysisCoordinator.run_blocking
    calls = {"n": 0}

    def fail_first(self, plan, *, on_progress=None):
        calls["n"] += 1
        if calls["n"] == 1:
            raise ValidationError("simulated notebook failure")
        return orig(self, plan, on_progress=on_progress)

    AnalysisCoordinator.run_blocking = fail_first  # type: ignore[method-assign]
    try:
        progress = coord.run_blocking(run.analysis_batch_id)
    finally:
        AnalysisCoordinator.run_blocking = orig  # type: ignore[method-assign]

    stored = AnalysisBatchRunStore(corpus).load(run.analysis_batch_id)
    states = {i.title: i.state for i in stored.items}
    assert states["bad"] == "failed"
    assert "simulated notebook failure" in (stored.items[0].error_message or "")
    assert states["good"] == "completed"
    assert progress.status == "partial"
    assert progress.failed == 1
    assert progress.completed == 1


def test_batch_analysis_cancel_does_not_start_next(tmp_path: Path) -> None:
    corpus = _corpus(tmp_path)
    clock, ids = FakeClock(), SequentialIds("can")
    _make_notebook(corpus, "first", clock=clock, ids=ids)
    _make_notebook(corpus, "second", clock=clock, ids=ids)

    coord = BatchAnalysisCoordinator(corpus, clock=clock, ids=ids)
    selected = select_needing_analysis(list_analysis_candidates(corpus, clock=clock, ids=ids))
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


def test_resume_resets_running_item_and_continues(tmp_path: Path) -> None:
    corpus = _corpus(tmp_path)
    clock, ids = FakeClock(), SequentialIds("rsm")
    _make_notebook(corpus, "done-nb", clock=clock, ids=ids)
    _make_notebook(corpus, "pending-nb", clock=clock, ids=ids)
    coord = BatchAnalysisCoordinator(corpus, clock=clock, ids=ids)
    candidates = list_analysis_candidates(corpus, clock=clock, ids=ids)
    by_title = {c.title: c for c in candidates}
    # Pre-analyse done-nb so resume won't redo heavy work unnecessarily
    first = coord.create_run([by_title["done-nb"]], module_ids=["stats"])
    assert coord.run_blocking(first.analysis_batch_id).status == "completed"

    run = coord.create_run(
        [by_title["done-nb"], by_title["pending-nb"]],
        module_ids=["stats"],
    )
    stored = AnalysisBatchRunStore(corpus).load(run.analysis_batch_id)
    stored.items[0].state = "completed"
    stored.items[0].modules_completed = 1
    stored.items[0].modules_total = 1
    stored.items[1].state = "running"
    stored.status = "running"
    AnalysisBatchRunStore(corpus).save(stored)

    progress = coord.resume(run.analysis_batch_id, blocking=True)
    assert progress.status == "completed"
    final = AnalysisBatchRunStore(corpus).load(run.analysis_batch_id)
    assert all(i.state == "completed" for i in final.items)
    assert final.items[1].inner_run_id


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


def test_create_run_freezes_explicit_text_model_for_batch(tmp_path: Path) -> None:
    from transcribe.analysis.llm_runtime import RecordedDoubleClient, set_text_llm_client
    from transcribe.analysis.plan import FrozenTextModel

    corpus = _corpus(tmp_path)
    clock, ids = FakeClock(), SequentialIds("tm")
    root_a = _make_notebook(corpus, "a", clock=clock, ids=ids)
    root_b = _make_notebook(corpus, "b", clock=clock, ids=ids)
    for root, model in ((root_a, "notebook-a:latest"), (root_b, "notebook-b:latest")):
        projects = ProjectService(open_project_paths(root), clock=clock, ids=ids)
        project = projects.load()
        settings = project.settings
        settings.text_model_name = model
        projects.save_settings(project, settings)

    coord = BatchAnalysisCoordinator(corpus, clock=clock, ids=ids)
    selected = list_analysis_candidates(corpus, clock=clock, ids=ids)
    set_text_llm_client(RecordedDoubleClient(responses={"default": "{}"}, digest="batch-digest"))
    try:
        run = coord.create_run(
            selected,
            module_ids=["llm_summary"],
            text_model_name="batch-pick:latest",
        )
    finally:
        set_text_llm_client(None)

    assert run.text_model is not None
    assert run.text_model["model_name"] == "batch-pick:latest"
    assert run.text_model["resolved_model_digest"] == "batch-digest"

    projects_b = ProjectService(open_project_paths(root_b), clock=clock, ids=ids)
    plan = coord._plan_for_notebook(run, projects_b, projects_b.load())
    assert isinstance(plan.text_model, FrozenTextModel)
    assert plan.text_model.model_name == "batch-pick:latest"
    assert plan.text_model.resolved_model_digest == "batch-digest"


def test_create_run_rejects_unresolvable_explicit_text_model(tmp_path: Path) -> None:
    from transcribe.analysis.llm_runtime import RecordedDoubleClient, set_text_llm_client

    corpus = _corpus(tmp_path)
    clock, ids = FakeClock(), SequentialIds("bad")
    _make_notebook(corpus, "nb", clock=clock, ids=ids)
    coord = BatchAnalysisCoordinator(corpus, clock=clock, ids=ids)
    selected = list_analysis_candidates(corpus, clock=clock, ids=ids)
    set_text_llm_client(RecordedDoubleClient(responses={}, healthy=False))
    try:
        with pytest.raises(ValidationError, match="could not resolve text model"):
            coord.create_run(
                selected,
                module_ids=["llm_summary"],
                text_model_name="missing:latest",
            )
    finally:
        set_text_llm_client(None)


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
        with pytest.raises(JobConflictError):
            coord.run_blocking(run.analysis_batch_id)
    finally:
        barrier.set()
        time.sleep(0.05)


@pytest.mark.parametrize(
    ("states", "expected"),
    [
        (("completed", "skipped"), "completed"),
        (("completed", "cancelled"), "partial"),
        (("failed", "failed"), "failed"),
        (("cancelled", "cancelled"), "cancelled"),
        (("completed", "failed"), "partial"),
        (("pending", "cancelled"), "cancelled"),
        (("running", "pending"), "running"),
    ],
)
def test_finalize_status_matrix(states: tuple[str, ...], expected: str) -> None:
    run = AnalysisBatchRun(
        analysis_batch_id="r1",
        created_at="t",
        updated_at="t",
        status="running",
        module_ids=["stats"],
        items=[
            AnalysisBatchItem(notebook_id=f"n{i}", state=state) for i, state in enumerate(states)
        ],
    )
    assert finalize_analysis_batch_status(run) == expected


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
        question_text="What themes?",
        import_run_id="imp-1",
        items=[
            AnalysisBatchItem(
                notebook_id="a",
                state="pending",
                modules_total=2,
                inner_run_id="inner-1",
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
    assert loaded.question_text == "What themes?"
    assert loaded.import_run_id == "imp-1"
    listed = store.list_runs()
    assert any(r.analysis_batch_id == "r-ab" for r in listed)


def test_progress_snapshot_maps_modules_and_terminals() -> None:
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
    assert snap["current_module"] == "stats"
    assert snap["completed"] == 1
    assert 0 < snap["pct"] < 100

    done = batch_analysis_progress_to_snapshot(
        BatchAnalysisProgress(
            analysis_batch_id="x",
            status="completed",
            total=2,
            completed=2,
            message="Batch completed",
        )
    )
    assert done["status"] == "completed"
    assert done["pct"] == 100.0

    partial = batch_analysis_progress_to_snapshot(
        BatchAnalysisProgress(
            analysis_batch_id="x", status="partial", total=2, completed=1, failed=1
        )
    )
    assert partial["phase"] == "partial"

    cancelled = batch_analysis_progress_to_snapshot(
        BatchAnalysisProgress(analysis_batch_id="x", status="cancelled", total=2)
    )
    assert cancelled["status"] == "failed"
    assert cancelled["phase"] == "cancelled"


def test_live_progress_forwards_module_ticks(tmp_path: Path) -> None:
    corpus = _corpus(tmp_path)
    clock, ids = FakeClock(), SequentialIds("live")
    _make_notebook(corpus, "alpha", clock=clock, ids=ids)
    coord = BatchAnalysisCoordinator(corpus, clock=clock, ids=ids)
    selected = list_analysis_candidates(corpus, clock=clock, ids=ids)
    run = coord.create_run(selected, module_ids=["stats", "lexical_diversity"])

    seen: list[tuple[str, str, int]] = []
    orig = AnalysisCoordinator.run_blocking

    def recording(self, plan, *, on_progress=None):
        def wrapped(progress: AnalysisProgress) -> None:
            live = coord.get_progress()
            seen.append((live.current_item, live.current_module_id, live.modules_total))
            if on_progress is not None:
                on_progress(progress)

        return orig(self, plan, on_progress=wrapped)

    AnalysisCoordinator.run_blocking = recording  # type: ignore[method-assign]
    try:
        progress = coord.run_blocking(run.analysis_batch_id)
    finally:
        AnalysisCoordinator.run_blocking = orig  # type: ignore[method-assign]

    assert progress.status == "completed"
    assert seen
    assert any("alpha" in item for item, _mid, _total in seen)
    assert any(mid == "stats" for _item, mid, _total in seen)
    assert any(total >= 2 for _item, _mid, total in seen)


def test_ocr_list_candidates_unaffected_by_analysis_fields(tmp_path: Path) -> None:
    """Shared extract keeps OCR pending semantics; analysis fields optional."""
    from transcribe.services.batch_notebooks import list_candidates

    corpus = _corpus(tmp_path)
    clock, ids = FakeClock(), SequentialIds("ocrreg")
    _make_notebook(corpus, "pending-nb", clock=clock, ids=ids)
    candidates = list_candidates(corpus, clock=clock, ids=ids, include_analysis=False)
    assert len(candidates) == 1
    assert candidates[0].pages_pending > 0
    assert candidates[0].analysis_aggregate == "missing"
    assert select_pending(candidates)


def test_list_candidates_light_skips_page_and_analysis_io(tmp_path: Path) -> None:
    from transcribe.services.batch_notebooks import list_candidates_light

    corpus = _corpus(tmp_path)
    clock, ids = FakeClock(), SequentialIds("light")
    _make_notebook(corpus, "has-text", clock=clock, ids=ids)
    light = list_candidates_light(corpus, clock=clock, ids=ids)
    assert len(light) == 1
    assert light[0].title == "has-text"
    assert light[0].pages_total == 1
    assert light[0].pages_with_text == 0
    assert light[0].pages_pending == 0
    assert light[0].analysis_aggregate == "missing"
    full = list_analysis_candidates(corpus, clock=clock, ids=ids)
    assert full[0].pages_with_text == 1
    assert full[0].analysis_aggregate == "missing"


def test_list_analyse_picker_candidates_uses_published_status_not_page_io(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import json

    from transcribe.services.batch_notebooks import (
        list_analyse_picker_candidates,
        published_analysis_status,
    )

    corpus = _corpus(tmp_path)
    clock, ids = FakeClock(), SequentialIds("pickst")
    missing_root = _make_notebook(corpus, "no-ax", clock=clock, ids=ids)
    degraded_root = _make_notebook(corpus, "degraded-ax", clock=clock, ids=ids)
    pub = degraded_root / "analysis" / "stats" / "published.json"
    pub.parent.mkdir(parents=True, exist_ok=True)
    pub.write_text(
        json.dumps(
            {
                "format": "transcribe.analysis-result",
                "schema_version": 1,
                "outcome": "insufficient_data",
                "capability": "insufficient_data",
            }
        ),
        encoding="utf-8",
    )

    original = ProjectService.load_page_result
    calls = {"n": 0}

    def _counted(self, page_id):  # noqa: ANN001
        calls["n"] += 1
        return original(self, page_id)

    monkeypatch.setattr(ProjectService, "load_page_result", _counted)
    picker = list_analyse_picker_candidates(corpus, clock=clock, ids=ids)
    assert calls["n"] == 0
    by_title = {c.title: c.analysis_aggregate for c in picker}
    assert by_title["no-ax"] == "missing"
    assert by_title["degraded-ax"] == "degraded"

    missing_projects = ProjectService(open_project_paths(missing_root), clock=clock, ids=ids)
    degraded_projects = ProjectService(open_project_paths(degraded_root), clock=clock, ids=ids)
    assert published_analysis_status(missing_projects) == "missing"
    assert published_analysis_status(degraded_projects) == "degraded"


def test_page_stats_single_pass_matches_legacy_helpers(tmp_path: Path) -> None:
    from transcribe.services.batch_notebooks import page_counts, page_stats, pages_with_text_count

    corpus = _corpus(tmp_path)
    clock, ids = FakeClock(), SequentialIds("stats")
    root = _make_notebook(corpus, "nb", clock=clock, ids=ids)
    projects = ProjectService(open_project_paths(root), clock=clock, ids=ids)
    project = projects.load(reconcile=False)
    total, pending, failed, with_text = page_stats(projects, project)
    assert (total, pending, failed) == page_counts(projects, project)
    assert with_text == pages_with_text_count(projects, project)
    assert with_text == 1


def test_analysis_aggregate_scan_skips_ollama_bind(tmp_path: Path, monkeypatch) -> None:
    """Corpus scan must not bind text LLM / planned_cache_identity (Ollama)."""
    from transcribe.services import batch_notebooks as bn

    corpus = _corpus(tmp_path)
    clock, ids = FakeClock(), SequentialIds("agg")
    root = _make_notebook(corpus, "needs", clock=clock, ids=ids)
    projects = ProjectService(open_project_paths(root), clock=clock, ids=ids)

    def _boom(*_a, **_k):
        raise AssertionError("scan must not call planned_cache_identity")

    monkeypatch.setattr(
        "transcribe.analysis.runner.AnalysisRunner.planned_cache_identity",
        _boom,
    )
    monkeypatch.setattr(
        "transcribe.analysis.llm_runtime.bind_text_llm_context",
        _boom,
    )
    aggregate = bn.analysis_aggregate_for_project(projects, clock=clock, ids=ids)
    assert aggregate == "missing"

    # After a real analyse, aggregate should become healthy without Ollama.
    coord = BatchAnalysisCoordinator(corpus, clock=clock, ids=ids)
    candidates = list_analysis_candidates(corpus, clock=clock, ids=ids)
    run = coord.create_run(candidates, module_ids=["stats"])
    assert coord.run_blocking(run.analysis_batch_id).status == "completed"
    after = bn.analysis_aggregate_for_project(projects, clock=clock, ids=ids)
    assert after == "healthy"


def test_list_analysis_candidates_loads_each_page_result_once(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    corpus = _corpus(tmp_path)
    clock, ids = FakeClock(), SequentialIds("once")
    root = _make_notebook(corpus, "nb", clock=clock, ids=ids)
    coord = BatchAnalysisCoordinator(corpus, clock=clock, ids=ids)
    cands = list_analysis_candidates(corpus, clock=clock, ids=ids)
    run = coord.create_run(cands, module_ids=["stats"])
    assert coord.run_blocking(run.analysis_batch_id).status == "completed"

    original = ProjectService.load_page_result
    calls = {"n": 0}

    def _counted(self, page_id):  # noqa: ANN001
        calls["n"] += 1
        return original(self, page_id)

    monkeypatch.setattr(ProjectService, "load_page_result", _counted)
    listed = list_analysis_candidates(corpus, clock=clock, ids=ids)
    assert listed[0].analysis_aggregate == "healthy"
    project = ProjectService(open_project_paths(root), clock=clock, ids=ids).load(reconcile=False)
    assert calls["n"] == len(project.pages)


def test_enrich_page_stats_fills_counts_for_light_candidates(tmp_path: Path) -> None:
    from transcribe.services.batch_notebooks import enrich_page_stats, list_candidates_light

    corpus = _corpus(tmp_path)
    clock, ids = FakeClock(), SequentialIds("enr")
    _make_notebook(corpus, "nb", clock=clock, ids=ids)
    light = list_candidates_light(corpus, clock=clock, ids=ids)
    assert light[0].pages_with_text == 0
    filled = enrich_page_stats(light, clock=clock, ids=ids)
    assert filled[0].pages_with_text == 1
    assert filled[0].pages_pending >= 1


def test_analysis_aggregate_marks_stale_on_module_version_mismatch(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Published module_version drift must surface as stale without Ollama."""
    import json

    from transcribe.services import batch_notebooks as bn

    corpus = _corpus(tmp_path)
    clock, ids = FakeClock(), SequentialIds("ver")
    root = _make_notebook(corpus, "nb", clock=clock, ids=ids)
    projects = ProjectService(open_project_paths(root), clock=clock, ids=ids)
    coord = BatchAnalysisCoordinator(corpus, clock=clock, ids=ids)
    cands = list_analysis_candidates(corpus, clock=clock, ids=ids)
    run = coord.create_run(cands, module_ids=["stats"])
    assert coord.run_blocking(run.analysis_batch_id).status == "completed"
    assert bn.analysis_aggregate_for_project(projects, clock=clock, ids=ids) == "healthy"

    published_path = projects.paths.analysis_dir / "stats" / "published.json"
    payload = json.loads(published_path.read_text(encoding="utf-8"))
    payload["module_version"] = f"{payload['module_version']}+drift"
    published_path.write_text(json.dumps(payload), encoding="utf-8")

    def _boom(*_a, **_k):
        raise AssertionError("stale scan must not bind Ollama / planned_cache_identity")

    monkeypatch.setattr(
        "transcribe.analysis.runner.AnalysisRunner.planned_cache_identity",
        _boom,
    )
    monkeypatch.setattr(
        "transcribe.analysis.llm_runtime.bind_text_llm_context",
        _boom,
    )
    assert bn.analysis_aggregate_for_project(projects, clock=clock, ids=ids) == "stale"
    needing = select_needing_analysis(list_analysis_candidates(corpus, clock=clock, ids=ids))
    assert {c.title for c in needing} == {"nb"}
    assert needing[0].analysis_aggregate == "stale"
