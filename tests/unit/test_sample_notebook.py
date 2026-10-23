"""Offline U2.2 sample notebook: copy → Analyse Quick → export markdown."""

from __future__ import annotations

from pathlib import Path

from transcribe.analysis.coordinator import AnalysisCoordinator
from transcribe.analysis.plan import build_analysis_run_plan
from transcribe.analysis.presets import resolve_analysis_preset
from transcribe.analysis.storage import AnalysisStorage
from transcribe.samples import demo_notebook_dir
from transcribe.services.export import ExportService
from transcribe.services.export_options import ExportOptions
from transcribe.services.project import ProjectService, open_project_paths
from transcribe.services.sample_notebook import SAMPLE_TITLE, copy_demo_notebook
from tests.conftest import FakeClock, SequentialIds

ROOT = Path(__file__).resolve().parents[2]
HOME = ROOT / "src" / "transcribe" / "ui" / "home.py"
NEW_NB = ROOT / "src" / "transcribe" / "ui" / "app.py"


def test_home_empty_state_has_no_open_sample():
    text = HOME.read_text(encoding="utf-8")
    assert "Open sample" not in text
    assert 'label="Create notebook"' in text
    assert 'label="Import"' in text


def test_new_notebook_page_has_open_sample():
    text = NEW_NB.read_text(encoding="utf-8")
    assert 'st.button("Open sample"' in text
    assert "copy_demo_notebook" in text


def test_copy_demo_notebook_analyse_quick_export(tmp_path: Path):
    clock, ids = FakeClock(), SequentialIds("sample")
    root = copy_demo_notebook(tmp_path / "projects", clock=clock, ids=ids)
    paths = open_project_paths(root)
    projects = ProjectService(paths, clock=clock, ids=ids)
    project = projects.load()
    assert project.title == SAMPLE_TITLE
    pngs = sorted(demo_notebook_dir().glob("page-*.png"))
    assert len(project.pages) == len(pngs) == 3
    for page, png in zip(project.pages, pngs, strict=True):
        sidecar = png.with_suffix(".txt").read_text(encoding="utf-8").strip()
        result = projects.load_page_result(page.page_id)
        assert result is not None
        assert result.effective_text() == sidecar

    resolved = resolve_analysis_preset("quick")
    assert "stats" in resolved.module_ids
    assert "llm_summary" not in resolved.module_ids
    plan = build_analysis_run_plan(
        project_service=projects,
        module_ids=resolved.module_ids,
        detector_ids=resolved.detector_ids,
        preset_key=resolved.preset,
        preset_label="Quick",
        clock=clock,
        ids=ids,
    )
    progress = AnalysisCoordinator(projects, clock=clock, ids=ids).run_blocking(plan)
    assert progress.status == "completed"
    published = AnalysisStorage(paths).read_published("stats")
    assert published is not None
    assert published.get("outcome") == "success"

    written = ExportService(paths, projects).export_all(
        dest_dir=tmp_path / "export",
        options=ExportOptions(formats=frozenset({"markdown"})),
    )
    markdown = written["markdown"].read_text(encoding="utf-8")
    assert "river ran high" in markdown
    assert "Market day" in markdown
    assert "Evening closed the book" in markdown
