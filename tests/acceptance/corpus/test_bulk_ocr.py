"""Acceptance: batch OCR CLI + fake-provider multi-notebook run."""

from __future__ import annotations

from pathlib import Path

from transcribe.corpus.paths import CorpusPaths
from transcribe.domain.models import OCRSettings
from transcribe.ingest import IngestService
from transcribe.services.batch_ocr import (
    BatchOcrCoordinator,
    list_candidates,
    select_pending,
)
from transcribe.services.project import ProjectService, open_project_paths
from tests.conftest import FakeClock, SequentialIds
from tests.fakes import FakeVisionOCRProvider
from tests.ingest.test_ingest import _png_bytes


def _workspace(tmp_path: Path) -> CorpusPaths:
    corpus = CorpusPaths(data_dir=tmp_path / "data", projects_dir=tmp_path / "projects")
    corpus.projects_dir.mkdir(parents=True)
    corpus.ensure_layout()
    return corpus


def _notebook(corpus: CorpusPaths, name: str, clock, ids) -> None:
    root = corpus.projects_dir / name
    projects = ProjectService(open_project_paths(root), clock=clock, ids=ids)
    projects.create(name)
    ingest = IngestService(open_project_paths(root), clock=clock, ids=ids)
    ingest.import_bytes(f"{name}.png", _png_bytes())


def test_batch_ocr_three_notebooks_offline(tmp_path: Path) -> None:
    corpus = _workspace(tmp_path)
    clock, ids = FakeClock(), SequentialIds("acc")
    for name in ("one", "two", "three"):
        _notebook(corpus, name, clock, ids)
    provider = FakeVisionOCRProvider()
    coord = BatchOcrCoordinator(corpus, clock=clock, ids=ids, provider=provider)
    selected = select_pending(list_candidates(corpus, clock=clock, ids=ids))
    assert len(selected) == 3
    run = coord.create_run(
        selected, settings=OCRSettings(model_name="fake-vision"), force=False
    )
    progress = coord.run_blocking(run.ocr_run_id)
    assert progress.status == "completed"
    assert provider.calls == 3
    for cand in selected:
        projects = ProjectService(
            open_project_paths(cand.root), clock=clock, ids=ids
        )
        project = projects.load()
        result = projects.load_page_result(project.pages[0].page_id)
        assert result is not None
        assert result.status == "succeeded"


def test_cli_wires_bulk_run_surfaces() -> None:
    main = Path("src/transcribe/__main__.py").read_text(encoding="utf-8")
    assert '"bulk-run"' in main
    assert "pending" in main
    assert "import-run" in main
    assert "ocr_run_id" in main


def test_cli_bulk_run_pending_offline(tmp_path: Path, monkeypatch) -> None:
    from transcribe.__main__ import main
    from transcribe.runtime_paths import RuntimePaths

    corpus = _workspace(tmp_path)
    clock, ids = FakeClock(), SequentialIds("cli")
    _notebook(corpus, "cli-nb", clock, ids)
    runtime = RuntimePaths(
        repo_root=tmp_path,
        data_dir=corpus.data_dir,
        projects_dir=corpus.projects_dir,
        inbox_dir=tmp_path / "inbox",
        export_dir=tmp_path / "exports",
    )
    monkeypatch.setattr("transcribe.__main__.PATHS", runtime)

    class _FakeOllama(FakeVisionOCRProvider):
        def __init__(self, *args, **kwargs):
            super().__init__()

    monkeypatch.setattr("transcribe.providers.ollama.OllamaVisionProvider", _FakeOllama)

    rc = main(["bulk-run", "pending", "--model", "fake-vision"])
    assert rc == 0
    runs = list(corpus.ocr_runs_dir.glob("*.json"))
    assert runs
    ocr_id = runs[0].stem
    assert main(["bulk-run", "status", ocr_id]) == 0
    assert main(["bulk-run", "resume", ocr_id]) == 0


def test_cli_bulk_run_notebooks_path(tmp_path: Path, monkeypatch) -> None:
    from transcribe.__main__ import main
    from transcribe.runtime_paths import RuntimePaths

    corpus = _workspace(tmp_path)
    clock, ids = FakeClock(), SequentialIds("nbcli")
    _notebook(corpus, "path-nb", clock, ids)
    root = corpus.projects_dir / "path-nb"
    runtime = RuntimePaths(
        repo_root=tmp_path,
        data_dir=corpus.data_dir,
        projects_dir=corpus.projects_dir,
        inbox_dir=tmp_path / "inbox",
        export_dir=tmp_path / "exports",
    )
    monkeypatch.setattr("transcribe.__main__.PATHS", runtime)

    class _FakeOllama(FakeVisionOCRProvider):
        def __init__(self, *args, **kwargs):
            super().__init__()

    monkeypatch.setattr("transcribe.providers.ollama.OllamaVisionProvider", _FakeOllama)
    rc = main(["bulk-run", "notebooks", str(root), "--model", "fake-vision"])
    assert rc == 0
