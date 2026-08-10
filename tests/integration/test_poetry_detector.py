"""Poetry detector integration test."""

from __future__ import annotations

import json
from io import BytesIO
from pathlib import Path

from PIL import Image

from transcribe.analysis.llm_runtime import RecordedDoubleClient
from transcribe.detection.api import DetectionService
from transcribe.ingest import IngestService
from transcribe.services.project import ProjectService, open_project_paths
from tests.conftest import FakeClock, SequentialIds


def _png_bytes() -> bytes:
    img = Image.new("RGB", (32, 32), (10, 20, 30))
    buf = BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


POEM_P2 = """Roses are red
Violets are blue
Sugar is sweet
And so are you"""

POEM_P3 = """The moon hangs low
Above the silent sea
Stars begin to glow"""

PROSE_P1 = "Today I went to the market and bought eggs, milk, and bread for the week."


def _poetry_response(*, detected: bool, continues_before: bool, continues_after: bool, conf: float = 0.9):
    return json.dumps(
        {
            "detected": detected,
            "confidence": conf,
            "starts_on_this_window": True,
            "continues_before": continues_before,
            "continues_after": continues_after,
            "boundaries": {"start_page_hint": None, "end_page_hint": None},
            "title": "Untitled",
            "reason": "ragged short lines",
        }
    )


def _project_with_poem(tmp_path: Path):
    paths = open_project_paths(tmp_path / "proj")
    clock, ids = FakeClock(), SequentialIds("poem")
    projects = ProjectService(paths, clock=clock, ids=ids)
    projects.create("poem-notebook")
    ingest = IngestService(paths, clock=clock, ids=ids)
    for i in range(3):
        ingest.import_bytes(f"p{i}.png", _png_bytes())
    project = projects.load()
    texts = [PROSE_P1, POEM_P2, POEM_P3]
    for page, text in zip(project.pages, texts, strict=True):
        projects.save_user_edit(page.page_id, text)
    return projects


def test_poetry_spans_multiple_pages(tmp_path: Path):
    projects = _project_with_poem(tmp_path)
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
    result = svc.run_detector("poetry", force=True)
    assert result["outcome"] == "success"
    findings = result.get("findings") or []
    assert len(findings) >= 1
    span = findings[0]
    project = projects.load()
    page_ids = [p.page_id for p in project.pages]
    start_idx = page_ids.index(span["start_page_id"])
    end_idx = page_ids.index(span["end_page_id"])
    assert end_idx - start_idx >= 1
    # Terminal attempt must not have been clobbered to interrupted by mid-run reconcile.
    assert result.get("attempt_state") == "succeeded"


def test_poetry_midrun_load_does_not_interrupt_attempt(tmp_path: Path):
    """Regression: project.load(reconcile=True) during execute must not mark attempt interrupted."""
    projects = _project_with_poem(tmp_path)
    client = RecordedDoubleClient(
        responses={
            "default": _poetry_response(
                detected=True, continues_before=False, continues_after=False
            ),
        },
        digest="test-digest",
    )
    svc = DetectionService(projects, text_ctx=_bind(client))
    result = svc.run_detector("poetry", force=True)
    assert result["attempt_state"] == "succeeded"
    assert result["outcome"] == "success"
    published = svc.runner.storage.read_published("poetry")
    assert published is not None
    assert published.get("attempt_state") == "succeeded"


def _bind(client: RecordedDoubleClient):
    from transcribe.analysis.llm_runtime import TextLLMContext

    return TextLLMContext(
        client=client,
        model_name=client.model_name,
        resolved_model_digest=client.digest or "d",
    )
