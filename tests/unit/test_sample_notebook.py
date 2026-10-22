"""U2.2 sample notebook install."""

from __future__ import annotations

from pathlib import Path

from tests.conftest import FakeClock, SequentialIds
from transcribe.runtime_paths import RuntimePaths
from transcribe.services.project import ProjectService, open_project_paths
from transcribe.services.sample_notebook import SAMPLE_SLUG, install_sample_notebook


def _runtime(tmp_path: Path) -> RuntimePaths:
    data = tmp_path / "data"
    projects = tmp_path / "projects"
    for path in (data, projects, tmp_path / "inbox", tmp_path / "exports", data / "config"):
        path.mkdir(parents=True, exist_ok=True)
    return RuntimePaths(
        repo_root=tmp_path,
        data_dir=data,
        projects_dir=projects,
        inbox_dir=tmp_path / "inbox",
        export_dir=tmp_path / "exports",
    )


def test_install_sample_notebook_seeds_text(tmp_path: Path, monkeypatch):
    runtime = _runtime(tmp_path)
    monkeypatch.setenv("TRANSCRIBE_DATA_DIR", str(runtime.data_dir))
    monkeypatch.setenv("TRANSCRIBE_PROJECTS_DIR", str(runtime.projects_dir))
    root = install_sample_notebook(
        runtime,
        clock=FakeClock(),
        ids=SequentialIds("smp"),
    )
    assert root.name == SAMPLE_SLUG
    assert root.is_dir()
    projects = ProjectService(open_project_paths(root), clock=FakeClock(), ids=SequentialIds("x"))
    project = projects.load()
    assert len(project.pages) == 3
    texts = [projects.load_page_result(p.page_id).effective_text() for p in project.pages]
    assert any("Anna" in (t or "") for t in texts)
    assert any("Paris" in (t or "") for t in texts)


def test_install_sample_idempotent_without_force(tmp_path: Path, monkeypatch):
    runtime = _runtime(tmp_path)
    monkeypatch.setenv("TRANSCRIBE_DATA_DIR", str(runtime.data_dir))
    monkeypatch.setenv("TRANSCRIBE_PROJECTS_DIR", str(runtime.projects_dir))
    clock, ids = FakeClock(), SequentialIds("smp")
    root1 = install_sample_notebook(runtime, clock=clock, ids=ids)
    marker = root1 / "project.json"
    mtime = marker.stat().st_mtime_ns
    root2 = install_sample_notebook(runtime, clock=clock, ids=ids, force=False)
    assert root2 == root1
    assert marker.stat().st_mtime_ns == mtime
