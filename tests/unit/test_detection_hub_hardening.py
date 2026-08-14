"""Deepened Prompt Hub / Detection hardening coverage (wave 2)."""

from __future__ import annotations

import json
from io import BytesIO
from pathlib import Path

from PIL import Image

from transcribe.analysis.llm_runtime import RecordedDoubleClient, TextLLMContext
from transcribe.detection.api import DetectionService
from transcribe.detection.runner import DetectionRunner
from transcribe.detection.custom import CustomDetectorDefinition, save_custom_detector
from transcribe.detection.envelope import build_detection_envelope
from transcribe.detection.registry import resolve_detector
from transcribe.detection.storage import DetectionStorage
from transcribe.ingest import IngestService
from transcribe.prompt_engine.definition import PromptDefinition, PromptFamily
from transcribe.prompt_engine.hub import ocr_render_for_job, resolve_prompt
from transcribe.prompt_engine.store import save_override
from transcribe.runtime_paths import RuntimePaths
from transcribe.services.project import ProjectService, open_project_paths
from tests.conftest import FakeClock, SequentialIds


def _rt(tmp_path: Path) -> RuntimePaths:
    data = tmp_path / "data"
    data.mkdir()
    return RuntimePaths(
        repo_root=tmp_path,
        data_dir=data,
        projects_dir=data / "projects",
        inbox_dir=data / "inbox",
        export_dir=data / "exports",
    )


def _png_bytes() -> bytes:
    img = Image.new("RGB", (32, 32), (10, 20, 30))
    buf = BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def _bind(client: RecordedDoubleClient) -> TextLLMContext:
    return TextLLMContext(
        client=client,
        model_name=client.model_name,
        resolved_model_digest=client.digest or "d",
    )


def _empty_client() -> RecordedDoubleClient:
    return RecordedDoubleClient(responses={"default": "{}"}, digest="d")


def test_prompt_override_changes_planned_cache_identity(tmp_path: Path, monkeypatch):
    paths = open_project_paths(tmp_path / "proj")
    clock, ids = FakeClock(), SequentialIds("ov")
    projects = ProjectService(paths, clock=clock, ids=ids)
    projects.create("ov-nb")
    ingest = IngestService(paths, clock=clock, ids=ids)
    ingest.import_bytes("p0.png", _png_bytes())
    page = projects.load().pages[0]
    projects.save_user_edit(page.page_id, "a short poem\nline two")

    rt = _rt(tmp_path)
    monkeypatch.setattr("transcribe.runtime_paths.build_runtime_paths", lambda: rt)
    monkeypatch.setattr("transcribe.prompt_engine.hub.build_runtime_paths", lambda: rt)
    monkeypatch.setattr("transcribe.prompt_engine.store.build_runtime_paths", lambda: rt)

    runner = DetectionService(projects, text_ctx=_bind(_empty_client())).runner
    det = resolve_detector("poetry")
    assert det is not None
    id_before, _, obj_before = runner.planned_cache_identity(det)

    base = resolve_prompt("poetry_detect_text_v1", runtime=rt)
    assert base is not None
    ov = PromptDefinition(
        prompt_id=base.prompt_id,
        version="7",
        title=base.title,
        description=base.description,
        system_prompt=base.system_prompt + "\nHardened override.",
        user_template=base.user_template,
        input_mode=base.input_mode,
        response_schema_id=base.response_schema_id,
        model_requirements=base.model_requirements,
        prompt_family=PromptFamily.DETECTION,
        is_override=True,
        is_builtin=False,
    )
    save_override(ov, runtime=rt)

    id_after, _, obj_after = runner.planned_cache_identity(det)
    assert obj_before["prompt_version"] != obj_after["prompt_version"]
    assert obj_after["prompt_version"] == "7"
    assert id_before != id_after


def test_ocr_hub_override_changes_rendered_sha(tmp_path: Path):
    rt = _rt(tmp_path)
    before = ocr_render_for_job(prompt_id="faithful_markdown", runtime=rt)
    base = resolve_prompt("faithful_markdown", runtime=rt)
    assert base is not None
    ov = PromptDefinition(
        prompt_id=base.prompt_id,
        version="3",
        title=base.title,
        description=base.description,
        system_prompt=base.system_prompt,
        user_template=base.user_template + "\nOCR OVERRIDE MARKER",
        input_mode=base.input_mode,
        response_schema_id=base.response_schema_id,
        model_requirements=base.model_requirements,
        prompt_family=PromptFamily.OCR,
        is_override=True,
        is_builtin=False,
    )
    save_override(ov, runtime=rt)
    after = ocr_render_for_job(prompt_id="faithful_markdown", runtime=rt)
    assert after[1] == "3"
    assert after[2] != before[2]
    assert "OCR OVERRIDE MARKER" in after[2]


def test_custom_detector_snapshot_on_success(tmp_path: Path, monkeypatch):
    paths = open_project_paths(tmp_path / "proj")
    clock, ids = FakeClock(), SequentialIds("cust")
    projects = ProjectService(paths, clock=clock, ids=ids)
    projects.create("cust-nb")
    ingest = IngestService(paths, clock=clock, ids=ids)
    ingest.import_bytes("p0.png", _png_bytes())
    page = projects.load().pages[0]
    projects.save_user_edit(page.page_id, "remember to buy milk")

    custom_root = tmp_path / "cfg" / "detection" / "custom"
    custom_root.mkdir(parents=True)
    monkeypatch.setattr("transcribe.detection.custom._custom_config_dir", lambda: custom_root)

    custom = CustomDetectorDefinition(
        name="Milk mentions",
        instruction="Find mentions of shopping for milk.",
        scope="page",
        adjacent_page_detection=False,
        model_mode="text",
        confidence_threshold=0.5,
        custom_id="milk-mentions",
    )
    save_custom_detector(custom)
    did = f"custom/{custom.slug()}"

    resp = json.dumps(
        {
            "detected": True,
            "confidence": 0.95,
            "starts_on_this_window": True,
            "continues_before": False,
            "continues_after": False,
            "boundaries": {"start_page_hint": None, "end_page_hint": None},
            "title": None,
            "reason": "milk shopping",
            "excerpt": "buy milk",
        }
    )
    client = RecordedDoubleClient(responses={"default": resp}, digest="d")
    svc = DetectionService(projects, text_ctx=_bind(client))
    result = svc.run_detector(did, force=True)
    assert result.get("attempt_state") == "succeeded"
    snap = paths.detection_dir / "custom" / "milk-mentions.json"
    assert snap.is_file()
    payload = json.loads(snap.read_text())
    assert payload["detector_id"] == did


def test_project_open_reconciles_detection_interrupted(tmp_path: Path):
    paths = open_project_paths(tmp_path / "proj")
    clock, ids = FakeClock(), SequentialIds("int")
    projects = ProjectService(paths, clock=clock, ids=ids)
    projects.create("int-nb")
    storage = DetectionStorage(paths)
    running = build_detection_envelope(
        notebook_id="nb",
        detector_id="poetry",
        detector_version="1",
        cache_identity="x",
        scope_fingerprint="s",
        attempt_state="running",
        outcome="success",
        findings=[],
        pages_scanned=[],
        windows_scanned=0,
        config_fingerprint="c",
        attempt_id="att-run",
        published=False,
    )
    storage.write_attempt("poetry", running)
    projects.load(reconcile=True)
    attempt = storage.read_attempt("poetry", "att-run")
    assert attempt is not None
    assert attempt["attempt_state"] == "interrupted"
    assert DetectionService(projects).latest_attempt_state("poetry") == "interrupted"


def test_cancel_check_marks_cancelled(tmp_path: Path):
    paths = open_project_paths(tmp_path / "proj")
    clock, ids = FakeClock(), SequentialIds("can")
    projects = ProjectService(paths, clock=clock, ids=ids)
    projects.create("can-nb")
    ingest = IngestService(paths, clock=clock, ids=ids)
    for i in range(3):
        ingest.import_bytes(f"p{i}.png", _png_bytes())
    project = projects.load()
    for page in project.pages:
        projects.save_user_edit(page.page_id, "line one\nline two\nline three")

    client = RecordedDoubleClient(
        responses={
            "default": json.dumps(
                {
                    "detected": False,
                    "confidence": 0.1,
                    "starts_on_this_window": False,
                    "continues_before": False,
                    "continues_after": False,
                    "boundaries": {"start_page_hint": None, "end_page_hint": None},
                    "title": None,
                    "reason": "no",
                }
            )
        },
        digest="d",
    )
    svc = DetectionService(projects, text_ctx=_bind(client))
    result = svc.run_detector(
        "poetry",
        force=True,
        cancel_check=lambda: True,
    )
    assert result.get("attempt_state") == "cancelled"


def test_freshness_binds_project_vision_model_not_workspace_ocr(tmp_path: Path):
    """Regression: Analyse→Detect freshness must not read OcrWorkspaceConfig.model_name."""
    from transcribe.detection.registry import resolve_detector

    paths = open_project_paths(tmp_path / "proj")
    clock, ids = FakeClock(), SequentialIds("fr")
    projects = ProjectService(paths, clock=clock, ids=ids)
    project = projects.create("fr-nb")
    settings = project.settings
    settings.model_name = "gemma3:4b"
    settings.text_model_name = ""
    projects.save_settings(project, settings)
    ingest = IngestService(paths, clock=clock, ids=ids)
    ingest.import_bytes("p0.png", _png_bytes())
    projects.save_user_edit(projects.load().pages[0].page_id, "some notebook text here")

    # No injected LLM contexts — mirrors Streamlit DetectionService(projects).
    svc = DetectionService(projects)
    fresh = svc.freshness("poetry")
    assert fresh in {"missing", "stale", "fresh", "unknown"}
    planned, _scope, _meta = svc.runner.planned_cache_identity(resolve_detector("poetry"))
    assert isinstance(planned, str) and planned


def test_detection_bind_contexts_falls_back_to_reachable_ollama_url(
    tmp_path: Path, monkeypatch
) -> None:
    paths = open_project_paths(tmp_path / "proj")
    clock, ids = FakeClock(), SequentialIds("url")
    projects = ProjectService(paths, clock=clock, ids=ids)
    project = projects.create("url-nb")
    settings = project.settings
    settings.base_url = "http://127.0.0.1:11434"
    settings.text_model_name = "mistral-small:latest"
    settings.model_name = "qwen2.5vl:3b"
    projects.save_settings(project, settings)

    rt = _rt(tmp_path)
    monkeypatch.setattr("transcribe.runtime_paths.build_runtime_paths", lambda: rt)

    class _Ocr:
        base_url = "http://host.docker.internal:11434"
        text_model_name = ""

    class _Llm:
        text_model_preference = ""

    class _Cfg:
        ocr = _Ocr()
        llm = _Llm()

    monkeypatch.setattr("transcribe.config.facade.get_config", lambda **kwargs: _Cfg())
    monkeypatch.setattr(
        "transcribe.providers.ollama.ollama_healthcheck",
        lambda url: url == "http://host.docker.internal:11434",
    )

    captured: dict[str, str] = {}

    def _capture_text_bind(**kwargs):
        captured["text_base_url"] = kwargs.get("base_url") or ""
        return None

    def _capture_vision_bind(**kwargs):
        captured["vision_base_url"] = kwargs.get("base_url") or ""
        return None

    monkeypatch.setattr(
        "transcribe.detection.runner.bind_text_llm_context",
        _capture_text_bind,
    )
    monkeypatch.setattr(
        "transcribe.detection.runner.bind_vision_llm_context",
        _capture_vision_bind,
    )

    runner = DetectionRunner(projects)
    runner._bind_contexts()

    assert captured["text_base_url"] == "http://host.docker.internal:11434"
    assert captured["vision_base_url"] == "http://host.docker.internal:11434"
