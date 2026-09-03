"""Per-page vs span detection tag approval."""

from __future__ import annotations

from pathlib import Path

from tests.conftest import FakeClock, SequentialIds
from tests.ingest.test_ingest import _png_bytes
from tests.services.test_poetry_detector import POEM_P2, POEM_P3, PROSE_P1, _poetry_response
from transcribe.analysis.llm_runtime import RecordedDoubleClient, TextLLMContext
from transcribe.detection.api import DetectionService
from transcribe.ingest import IngestService
from transcribe.runtime_paths import RuntimePaths
from transcribe.services.project import ProjectService, open_project_paths


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


def _poetry_notebook(
    tmp_path: Path, monkeypatch
) -> tuple[ProjectService, DetectionService, list[str]]:
    runtime = _runtime(tmp_path)
    monkeypatch.setenv("TRANSCRIBE_DATA_DIR", str(runtime.data_dir))
    monkeypatch.setenv("TRANSCRIBE_PROJECTS_DIR", str(runtime.projects_dir))
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
    result = svc.run_detector("poetry", force=True, auto_tag=False)
    assert result["outcome"] == "success"
    page_ids = [p.page_id for p in projects.load().pages]
    return projects, svc, page_ids


def test_apply_finding_tag_single_page_leaves_span_untagged(tmp_path: Path, monkeypatch):
    projects, svc, page_ids = _poetry_notebook(tmp_path, monkeypatch)
    findings = svc.list_findings("poetry")
    assert findings
    finding = findings[0]
    span_ids = svc.span_page_ids(finding)
    assert len(span_ids) >= 2

    n = svc.apply_finding_tag(finding, [page_ids[1]], approve_finding=False)
    assert n == 1
    after = projects.load(reconcile=False)
    assert "poetry" in after.pages[1].tags
    assert "poetry" not in after.pages[0].tags
    assert finding.review_status == "unreviewed"


def test_apply_finding_tag_span_approves_finding(tmp_path: Path, monkeypatch):
    projects, svc, _page_ids = _poetry_notebook(tmp_path, monkeypatch)
    findings = svc.list_findings("poetry")
    finding = findings[0]
    span_ids = svc.span_page_ids(finding)

    n = svc.apply_finding_tag(finding, span_ids, approve_finding=True)
    assert n >= 2
    after = projects.load(reconcile=False)
    tagged = [p for p in after.pages if "poetry" in p.tags]
    assert len(tagged) == len(span_ids)
    refreshed = svc.list_findings("poetry")
    by_id = {f.finding_id: f for f in refreshed}
    assert by_id[finding.finding_id].review_status == "approved"


def test_apply_finding_tag_single_page_span_marks_approved(tmp_path: Path, monkeypatch):
    runtime = _runtime(tmp_path)
    monkeypatch.setenv("TRANSCRIBE_DATA_DIR", str(runtime.data_dir))
    paths = open_project_paths(runtime.projects_dir / "one")
    clock, ids = FakeClock(), SequentialIds("one")
    projects = ProjectService(paths, clock=clock, ids=ids)
    projects.create("one-page")
    ingest = IngestService(paths, clock=clock, ids=ids)
    ingest.import_bytes("p0.png", _png_bytes())
    page_id = projects.load().pages[0].page_id
    projects.save_user_edit(page_id, POEM_P2)
    client = RecordedDoubleClient(
        responses={
            "default": _poetry_response(
                detected=True, continues_before=False, continues_after=False
            ),
        },
        digest="test-digest",
    )
    svc = DetectionService(projects, text_ctx=_bind(client))
    svc.run_detector("poetry", force=True, auto_tag=False)
    finding = svc.list_findings("poetry")[0]
    n = svc.apply_finding_tag(finding, [page_id], approve_finding=True)
    assert n == 1
    assert svc.list_findings("poetry")[0].review_status == "approved"


def test_accept_finding_approves_and_tags_span(tmp_path: Path, monkeypatch):
    projects, svc, _page_ids = _poetry_notebook(tmp_path, monkeypatch)
    finding = svc.list_findings("poetry")[0]
    span_ids = svc.span_page_ids(finding)
    assert finding.review_status == "unreviewed"

    n = svc.accept_finding(finding)
    assert n == len(span_ids)
    after = projects.load(reconcile=False)
    tagged = [p for p in after.pages if "poetry" in p.tags]
    assert len(tagged) == len(span_ids)
    assert svc.list_findings("poetry")[0].review_status == "approved"


def test_accept_finding_when_already_tagged_only_approves(tmp_path: Path, monkeypatch):
    projects, svc, _page_ids = _poetry_notebook(tmp_path, monkeypatch)
    finding = svc.list_findings("poetry")[0]
    span_ids = svc.span_page_ids(finding)
    tagged_n = svc.apply_finding_tag(finding, span_ids, approve_finding=False)
    assert tagged_n == len(span_ids)
    finding = svc.list_findings("poetry")[0]
    assert finding.review_status == "unreviewed"

    n = svc.accept_finding(finding)
    assert n == 0
    assert svc.list_findings("poetry")[0].review_status == "approved"


def test_accept_finding_unrejects(tmp_path: Path, monkeypatch):
    _projects, svc, _page_ids = _poetry_notebook(tmp_path, monkeypatch)
    finding = svc.list_findings("poetry")[0]
    svc.set_review_status("poetry", finding.finding_id, "rejected")
    finding = svc.list_findings("poetry")[0]
    assert finding.review_status == "rejected"

    n = svc.accept_finding(finding)
    assert n >= 1
    assert svc.list_findings("poetry")[0].review_status == "approved"


def test_set_page_review_rejects_one_page_keeps_others(tmp_path: Path, monkeypatch):
    projects, svc, _page_ids = _poetry_notebook(tmp_path, monkeypatch)
    finding = svc.list_findings("poetry")[0]
    span_ids = svc.span_page_ids(finding)
    assert len(span_ids) >= 2
    svc.apply_finding_tag(finding, span_ids, approve_finding=False)

    dropped = svc.set_page_review(finding, span_ids[-1], "rejected")
    assert dropped == 1
    after = projects.load(reconcile=False)
    tags = {p.page_id: set(p.tags) for p in after.pages}
    assert "poetry" not in tags[span_ids[-1]]
    assert "poetry" in tags[span_ids[0]]
    refreshed = svc.list_findings("poetry")[0]
    assert refreshed.page_reviews[span_ids[-1]] == "rejected"
    assert refreshed.review_status == "unreviewed"

    n = svc.accept_finding(refreshed)
    assert n == 0
    done = svc.list_findings("poetry")[0]
    assert done.review_status == "approved"
    assert done.page_reviews[span_ids[-1]] == "rejected"
    assert done.page_reviews[span_ids[0]] == "approved"
    tagged = [p.page_id for p in projects.load(reconcile=False).pages if "poetry" in p.tags]
    assert span_ids[-1] not in tagged
    assert span_ids[0] in tagged


def test_set_page_review_accept_one_page(tmp_path: Path, monkeypatch):
    projects, svc, _page_ids = _poetry_notebook(tmp_path, monkeypatch)
    finding = svc.list_findings("poetry")[0]
    span_ids = svc.span_page_ids(finding)
    n = svc.set_page_review(finding, span_ids[0], "approved")
    assert n == 1
    after = {p.page_id: p for p in projects.load(reconcile=False).pages}
    assert "poetry" in after[span_ids[0]].tags
    refreshed = svc.list_findings("poetry")[0]
    assert refreshed.page_reviews[span_ids[0]] == "approved"
    assert refreshed.review_status == "unreviewed"
