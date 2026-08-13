"""Acceptance: multi-notebook Analyse batch + CLI surfaces (offline)."""

from __future__ import annotations

from pathlib import Path

from transcribe.__main__ import main
from transcribe.corpus.analysis_batch_run import AnalysisBatchRunStore
from transcribe.corpus.import_run import ImportRun, ImportRunItemOutcome, ImportRunStore
from transcribe.corpus.paths import CorpusPaths
from transcribe.corpus.plan import POLICY_SKIP_EXISTING_V1
from transcribe.ingest import IngestService
from transcribe.persistence.schema import SUPPORTED
from transcribe.services.batch_analysis import (
    BatchAnalysisCoordinator,
    list_analysis_candidates,
    select_from_import_run,
    select_needing_analysis,
)
from transcribe.services.project import ProjectService, open_project_paths
from tests.conftest import FakeClock, SequentialIds
from tests.ingest.test_ingest import _png_bytes


def _corpus(tmp_path: Path) -> CorpusPaths:
    paths = CorpusPaths(data_dir=tmp_path / "data", projects_dir=tmp_path / "projects")
    paths.projects_dir.mkdir(parents=True)
    paths.ensure_layout()
    return paths


def _nb(corpus: CorpusPaths, name: str, *, clock, ids) -> Path:
    root = corpus.projects_dir / name
    projects = ProjectService(open_project_paths(root), clock=clock, ids=ids)
    projects.create(name)
    IngestService(open_project_paths(root), clock=clock, ids=ids).import_bytes(
        f"{name}.png", _png_bytes()
    )
    project = projects.load()
    projects.save_user_edit(
        project.pages[0].page_id,
        f"Offline acceptance text for {name}. Enough content for stats modules.",
    )
    return root


def _patch_paths(monkeypatch, corpus: CorpusPaths):
    import transcribe.__main__ as main_mod
    from transcribe.runtime_paths import RuntimePaths

    live = main_mod.PATHS
    main_mod.PATHS = RuntimePaths(
        repo_root=live.repo_root,
        data_dir=corpus.data_dir,
        projects_dir=corpus.projects_dir,
        inbox_dir=live.inbox_dir,
        export_dir=live.export_dir,
    )
    return main_mod, live


def test_analysis_batch_run_format_registered() -> None:
    assert SUPPORTED.get("transcribe.analysis-batch-run") == 1
    contract = Path("docs/contracts/analysis-batch-run.md").read_text(encoding="utf-8")
    assert "transcribe.analysis-batch-run" in contract
    assert "corpus/analysis-runs/" in contract


def test_batch_analysis_three_notebooks_offline(tmp_path: Path) -> None:
    corpus = _corpus(tmp_path)
    clock, ids = FakeClock(), SequentialIds("acc")
    for name in ("a", "b", "c"):
        _nb(corpus, name, clock=clock, ids=ids)
    coord = BatchAnalysisCoordinator(corpus, clock=clock, ids=ids)
    selected = select_needing_analysis(
        list_analysis_candidates(corpus, clock=clock, ids=ids)
    )
    assert len(selected) == 3
    run = coord.create_run(
        selected,
        module_ids=["stats"],
        preset_key="quick",
        preset_content_version=1,
        preset_policy_fingerprint="test",
    )
    progress = coord.run_blocking(run.analysis_batch_id)
    assert progress.status == "completed"
    stored = AnalysisBatchRunStore(corpus).load(run.analysis_batch_id)
    assert all(i.state == "completed" for i in stored.items)
    assert stored.preset_key == "quick"
    for item in stored.items:
        root = corpus.resolve_managed(item.managed_relpath)
        assert (root / "analysis" / "stats" / "published.json").is_file()


def test_batch_analysis_from_import_run(tmp_path: Path) -> None:
    corpus = _corpus(tmp_path)
    clock, ids = FakeClock(), SequentialIds("imp")
    _nb(corpus, "kept", clock=clock, ids=ids)
    _nb(corpus, "other", clock=clock, ids=ids)
    candidates = list_analysis_candidates(corpus, clock=clock, ids=ids)
    by_title = {c.title: c for c in candidates}
    ImportRunStore(corpus).save(
        ImportRun(
            import_run_id="imp-ax",
            plan_id="plan",
            plan_fingerprint="b" * 64,
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
                    resulting_ids={"notebook_id": by_title["other"].notebook_id},
                ),
            ],
        )
    )
    selected = select_from_import_run(
        corpus, "imp-ax", candidates, purpose="analyse"
    )
    assert [c.title for c in selected] == ["kept"]
    coord = BatchAnalysisCoordinator(corpus, clock=clock, ids=ids)
    run = coord.create_run(
        selected, module_ids=["stats"], import_run_id="imp-ax"
    )
    progress = coord.run_blocking(run.analysis_batch_id)
    assert progress.status == "completed"
    stored = AnalysisBatchRunStore(corpus).load(run.analysis_batch_id)
    assert stored.import_run_id == "imp-ax"
    assert len(stored.items) == 1


def test_cli_wires_bulk_analyse_surfaces() -> None:
    main_src = Path("src/transcribe/__main__.py").read_text(encoding="utf-8")
    assert '"bulk-analyse"' in main_src
    for sub in ("pending", "import-run", "notebooks", "status", "resume"):
        assert sub in main_src


def test_cli_bulk_analyse_pending_offline(tmp_path: Path, monkeypatch) -> None:
    corpus = _corpus(tmp_path)
    clock, ids = FakeClock(), SequentialIds("cli")
    _nb(corpus, "one", clock=clock, ids=ids)
    _nb(corpus, "two", clock=clock, ids=ids)

    main_mod, live = _patch_paths(monkeypatch, corpus)
    try:
        rc = main(["bulk-analyse", "pending", "--preset", "quick"])
        assert rc == 0
        runs = AnalysisBatchRunStore(corpus).list_runs()
        assert runs
        assert main(["bulk-analyse", "status", runs[0].analysis_batch_id]) == 0
        assert main(["bulk-analyse", "resume", runs[0].analysis_batch_id]) == 0
    finally:
        main_mod.PATHS = live


def test_cli_bulk_analyse_notebooks_path(tmp_path: Path, monkeypatch) -> None:
    corpus = _corpus(tmp_path)
    clock, ids = FakeClock(), SequentialIds("clipath")
    root = _nb(corpus, "solo", clock=clock, ids=ids)

    main_mod, live = _patch_paths(monkeypatch, corpus)
    try:
        rc = main(
            ["bulk-analyse", "notebooks", str(root), "--preset", "quick"]
        )
        assert rc == 0
        runs = AnalysisBatchRunStore(corpus).list_runs()
        assert len(runs) == 1
        assert len(runs[0].items) == 1
        assert runs[0].items[0].state == "completed"
    finally:
        main_mod.PATHS = live


def test_cli_bulk_analyse_import_run(tmp_path: Path, monkeypatch) -> None:
    corpus = _corpus(tmp_path)
    clock, ids = FakeClock(), SequentialIds("cliimp")
    _nb(corpus, "kept", clock=clock, ids=ids)
    candidates = list_analysis_candidates(corpus, clock=clock, ids=ids)
    ImportRunStore(corpus).save(
        ImportRun(
            import_run_id="cli-imp",
            plan_id="plan",
            plan_fingerprint="c" * 64,
            import_policy_id=POLICY_SKIP_EXISTING_V1,
            created_at="2026-01-01T00:00:00+00:00",
            updated_at="2026-01-01T00:00:00+00:00",
            status="complete",
            items=[
                ImportRunItemOutcome(
                    item_id="i1",
                    state="committed",
                    resulting_ids={"notebook_id": candidates[0].notebook_id},
                ),
            ],
        )
    )
    main_mod, live = _patch_paths(monkeypatch, corpus)
    try:
        rc = main(
            ["bulk-analyse", "import-run", "cli-imp", "--preset", "quick"]
        )
        assert rc == 0
        runs = AnalysisBatchRunStore(corpus).list_runs()
        assert runs[0].import_run_id == "cli-imp"
    finally:
        main_mod.PATHS = live
