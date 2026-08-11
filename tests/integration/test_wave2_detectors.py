"""New detector schema and coexistence tests."""

from __future__ import annotations

import json
from io import BytesIO
from pathlib import Path

from PIL import Image

from transcribe.analysis.llm_runtime import RecordedDoubleClient, TextLLMContext
from transcribe.detection.aggregate import merge_adjacent_spans, raw_from_window_response
from transcribe.detection.api import DetectionService
from transcribe.detection.registry import get_builtin_detector
from transcribe.ingest import IngestService
from transcribe.prompt_engine.validate import (
    validate_lists_window_response_v1,
    validate_quotations_window_response_v1,
    validate_todo_window_response_v1,
)
from transcribe.services.project import ProjectService, open_project_paths
from tests.conftest import FakeClock, SequentialIds


def test_todo_schema_valid():
    out = validate_todo_window_response_v1(
        {
            "detected": True,
            "confidence": 0.9,
            "starts_on_this_window": True,
            "continues_before": False,
            "continues_after": True,
            "items": [{"text": "Buy milk", "status": "open"}],
            "list_style": "checkbox",
            "reason": "checkboxes",
        }
    )
    assert out is not None
    assert out["items"][0]["status"] == "open"


def test_lists_schema_valid():
    out = validate_lists_window_response_v1(
        {
            "detected": True,
            "confidence": 0.8,
            "starts_on_this_window": True,
            "continues_before": False,
            "continues_after": False,
            "list_kind": "shopping",
            "item_count_estimate": 3,
            "sample_items": ["eggs", "milk"],
            "reason": "bullets",
        }
    )
    assert out is not None
    assert out["list_kind"] == "shopping"


def test_quotations_schema_valid():
    out = validate_quotations_window_response_v1(
        {
            "detected": True,
            "confidence": 0.85,
            "starts_on_this_window": True,
            "continues_before": False,
            "continues_after": True,
            "quote_kind": "block",
            "attribution": "Auden",
            "excerpt": "We must love one another",
            "reason": "quotes",
        }
    )
    assert out is not None
    assert out["attribution"] == "Auden"


def test_cross_type_do_not_merge():
    ordered = ["p0", "p1"]
    todo = raw_from_window_response(
        parsed={
            "detected": True,
            "confidence": 0.9,
            "starts_on_this_window": True,
            "continues_before": False,
            "continues_after": False,
            "reason": "todo",
        },
        window_page_ids=("p0",),
        ordered_page_ids=ordered,
        finding_type="todo_lists",
        input_fingerprint="a",
        window_id="w1",
    )
    lst = raw_from_window_response(
        parsed={
            "detected": True,
            "confidence": 0.9,
            "starts_on_this_window": True,
            "continues_before": False,
            "continues_after": False,
            "reason": "list",
        },
        window_page_ids=("p0",),
        ordered_page_ids=ordered,
        finding_type="lists",
        input_fingerprint="b",
        window_id="w2",
    )
    assert todo and lst
    merged = merge_adjacent_spans(
        [todo, lst], ordered_page_ids=ordered, confidence_threshold=0.7
    )
    assert len(merged) == 2


def _png() -> bytes:
    buf = BytesIO()
    Image.new("RGB", (32, 32), (1, 2, 3)).save(buf, format="PNG")
    return buf.getvalue()


def _resp(**kwargs):
    base = {
        "detected": True,
        "confidence": 0.9,
        "starts_on_this_window": True,
        "continues_before": False,
        "continues_after": False,
        "reason": "x",
        "items": [{"text": "task", "status": "open"}],
        "list_style": "checkbox",
        "list_kind": "shopping",
        "item_count_estimate": 2,
        "sample_items": ["a"],
        "quote_kind": "block",
        "attribution": None,
        "excerpt": "quoted",
        "boundaries": {},
        "title": None,
    }
    base.update(kwargs)
    return json.dumps(base)


def test_todo_lists_detector_runs(tmp_path: Path):
    assert get_builtin_detector("todo_lists") is not None
    paths = open_project_paths(tmp_path / "proj")
    clock, ids = FakeClock(), SequentialIds("td")
    projects = ProjectService(paths, clock=clock, ids=ids)
    projects.create("n")
    ingest = IngestService(paths, clock=clock, ids=ids)
    ingest.import_bytes("p.png", _png())
    page = projects.load().pages[0]
    projects.save_user_edit(page.page_id, "- [ ] Write tests\n- [x] Ship")
    client = RecordedDoubleClient(responses={"default": _resp()}, digest="d")
    ctx = TextLLMContext(client=client, model_name=client.model_name, resolved_model_digest="d")
    svc = DetectionService(projects, text_ctx=ctx)
    result = svc.run_detector("todo_lists", force=True)
    assert result["outcome"] == "success"
    assert len(result.get("findings") or []) >= 1
    assert result["findings"][0]["finding_type"] == "todo_lists"


def test_lists_detector_runs(tmp_path: Path):
    assert get_builtin_detector("lists") is not None
    paths = open_project_paths(tmp_path / "proj")
    clock, ids = FakeClock(), SequentialIds("ls")
    projects = ProjectService(paths, clock=clock, ids=ids)
    projects.create("n")
    ingest = IngestService(paths, clock=clock, ids=ids)
    ingest.import_bytes("p.png", _png())
    page = projects.load().pages[0]
    projects.save_user_edit(page.page_id, "- eggs\n- milk\n- bread")
    client = RecordedDoubleClient(
        responses={"default": _resp(list_kind="shopping", list_style="mixed")},
        digest="d",
    )
    ctx = TextLLMContext(
        client=client, model_name=client.model_name, resolved_model_digest="d"
    )
    svc = DetectionService(projects, text_ctx=ctx)
    result = svc.run_detector("lists", force=True)
    assert result["outcome"] == "success"
    assert (result.get("findings") or [])[0]["finding_type"] == "lists"


def test_quotations_multi_page(tmp_path: Path):
    paths = open_project_paths(tmp_path / "proj")
    clock, ids = FakeClock(), SequentialIds("qt")
    projects = ProjectService(paths, clock=clock, ids=ids)
    projects.create("n")
    ingest = IngestService(paths, clock=clock, ids=ids)
    for i in range(2):
        ingest.import_bytes(f"p{i}.png", _png())
    project = projects.load()
    projects.save_user_edit(project.pages[0].page_id, '"We must love one another or die,"')
    projects.save_user_edit(project.pages[1].page_id, "he wrote in September 1, 1939.")
    client = RecordedDoubleClient(
        responses={
            "default": _resp(continues_after=True),
            "contains:love": _resp(continues_after=True),
            "contains:September": _resp(continues_before=True, continues_after=False),
        },
        digest="d",
    )
    ctx = TextLLMContext(client=client, model_name=client.model_name, resolved_model_digest="d")
    svc = DetectionService(projects, text_ctx=ctx)
    result = svc.run_detector("quotations", force=True)
    assert result["outcome"] == "success"
    findings = result.get("findings") or []
    assert len(findings) >= 1
