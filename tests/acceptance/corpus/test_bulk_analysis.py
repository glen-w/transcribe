"""Acceptance: multi-notebook Analyse batch + CLI surfaces (offline)."""

from __future__ import annotations

from pathlib import Path

from transcribe.__main__ import main
from transcribe.corpus.analysis_batch_run import AnalysisBatchRunStore
from transcribe.corpus.paths import CorpusPaths
from transcribe.ingest import IngestService
from transcribe.persistence.schema import SUPPORTED
from transcribe.services.batch_analysis import (
    BatchAnalysisCoordinator,
    list_analysis_candidates,
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


def test_analysis_batch_run_format_registered() -> None:
    assert SUPPORTED.get("transcribe.analysis-batch-run") == 1
    contract = Path("docs/contracts/analysis-batch-run.md").read_text(encoding="utf-8")
    assert "transcribe.analysis-batch-run" in contract


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
    run = coord.create_run(selected, module_ids=["stats"])
    progress = coord.run_blocking(run.analysis_batch_id)
    assert progress.status == "completed"
    stored = AnalysisBatchRunStore(corpus).load(run.analysis_batch_id)
    assert all(i.state == "completed" for i in stored.items)


def test_cli_wires_bulk_analyse_surfaces() -> None:
    from pathlib import Path as P

    main_src = P("src/transcribe/__main__.py").read_text(encoding="utf-8")
    assert '"bulk-analyse"' in main_src
    assert "pending" in main_src


def test_cli_bulk_analyse_pending_offline(tmp_path: Path, monkeypatch) -> None:
    corpus = _corpus(tmp_path)
    clock, ids = FakeClock(), SequentialIds("cli")
    _nb(corpus, "one", clock=clock, ids=ids)
    _nb(corpus, "two", clock=clock, ids=ids)

    monkeypatch.setenv("TRANSCRIBE_DATA_DIR", str(corpus.data_dir))
    monkeypatch.setenv("TRANSCRIBE_PROJECTS_DIR", str(corpus.projects_dir))
    # Reload PATHS is sticky — patch module PATHS
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
    try:
        rc = main(["bulk-analyse", "pending", "--preset", "quick"])
        assert rc == 0
        runs = AnalysisBatchRunStore(corpus).list_runs()
        assert runs
        assert main(["bulk-analyse", "status", runs[0].analysis_batch_id]) == 0
        assert main(["bulk-analyse", "resume", runs[0].analysis_batch_id]) == 0
    finally:
        main_mod.PATHS = live
