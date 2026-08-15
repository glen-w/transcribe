"""Detection auto-tag unions finding_type onto span pages without touching cache identity."""

from __future__ import annotations

from pathlib import Path

from tests.conftest import FakeClock, SequentialIds
from tests.ingest.test_ingest import _png_bytes
from tests.services.test_poetry_detector import POEM_P2, POEM_P3, PROSE_P1, _poetry_response
from transcribe.analysis.llm_runtime import RecordedDoubleClient, TextLLMContext
from transcribe.detection.api import DetectionService
from transcribe.detection.registry import resolve_detector
from transcribe.ingest import IngestService
from transcribe.runtime_paths import RuntimePaths
from transcribe.services.project import ProjectService, open_project_paths
from transcribe.services.tags import TagService


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


def _bind(client: RecordedDoubleClient) -> TextLLMContext:
    return TextLLMContext(
        client=client,
        model_name=client.model_name,
        resolved_model_digest=client.digest or "d",
    )


def test_auto_tag_unions_span_pages_and_skips_cache_config(tmp_path: Path, monkeypatch):
    runtime = _runtime(tmp_path)
    monkeypatch.setenv("TRANSCRIBE_DATA_DIR", str(runtime.data_dir))
    monkeypatch.setenv("TRANSCRIBE_PROJECTS_DIR", str(runtime.projects_dir))
    detector = resolve_detector("poetry")
    assert detector is not None
    assert "auto_tag" not in detector.cache_config()

    paths = open_project_paths(runtime.projects_dir / "poem")
    clock, ids = FakeClock(), SequentialIds("poem")
    projects = ProjectService(paths, clock=clock, ids=ids)
    projects.create("poem-notebook")
    ingest = IngestService(paths, clock=clock, ids=ids)
    for i in range(3):
        ingest.import_bytes(f"p{i}.png", _png_bytes())
    project = projects.load()
    for page, text in zip(project.pages, [PROSE_P1, POEM_P2, POEM_P3], strict=True):
        projects.save_user_edit(page.page_id, text)

    client = RecordedDoubleClient(
        responses={
            "default": _poetry_response(
                detected=True, continues_before=False, continues_after=True
            ),
            "contains:Roses": _poetry_response(
                detected=True, continues_before=False, continues_after=True
            ),
            "contains:moon": _poetry_response(
                detected=True, continues_before=True, continues_after=False
            ),
        },
        digest="test-digest",
    )
    svc = DetectionService(projects, text_ctx=_bind(client))
    result = svc.run_detector("poetry", force=True, auto_tag=True)
    assert result["outcome"] == "success"
    identity = result.get("cache_identity")
    assert identity
    tagged = result.get("auto_tagged_pages")
    assert tagged and tagged >= 1
    after = projects.load(reconcile=False)
    poetry_pages = [p for p in after.pages if "poetry" in p.tags]
    assert len(poetry_pages) >= 1
    catalog = TagService(runtime, clock=clock, ids=SequentialIds("tag")).load_catalog()
    assert catalog.get_by_slug("poetry") is not None

    cached = svc.run_detector("poetry", force=False, auto_tag=False)
    assert cached.get("cache_identity") == identity


def test_apply_tags_from_published_without_rerun(tmp_path: Path, monkeypatch):
    runtime = _runtime(tmp_path)
    monkeypatch.setenv("TRANSCRIBE_DATA_DIR", str(runtime.data_dir))
    paths = open_project_paths(runtime.projects_dir / "poem")
    clock, ids = FakeClock(), SequentialIds("poem")
    projects = ProjectService(paths, clock=clock, ids=ids)
    projects.create("poem-notebook")
    ingest = IngestService(paths, clock=clock, ids=ids)
    ingest.import_bytes("p0.png", _png_bytes())
    ingest.import_bytes("p1.png", _png_bytes())
    project = projects.load()
    projects.save_user_edit(project.pages[0].page_id, PROSE_P1)
    projects.save_user_edit(project.pages[1].page_id, POEM_P2)
    client = RecordedDoubleClient(
        responses={
            "default": _poetry_response(
                detected=True, continues_before=False, continues_after=False
            ),
        },
        digest="test-digest",
    )
    svc = DetectionService(projects, text_ctx=_bind(client))
    result = svc.run_detector("poetry", force=True, auto_tag=False)
    assert result["outcome"] == "success"
    assert all("poetry" not in p.tags for p in projects.load().pages)
    n = svc.apply_tags_from_published("poetry")
    assert n >= 1
    assert any("poetry" in p.tags for p in projects.load().pages)
