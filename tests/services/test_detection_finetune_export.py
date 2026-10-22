"""Detection fine-tune export (approved/rejected labels)."""

from __future__ import annotations

import json
from io import BytesIO
from pathlib import Path

from PIL import Image

from tests.conftest import FakeClock, SequentialIds
from transcribe.detection.api import DetectionService
from transcribe.detection.findings import DetectionFinding
from transcribe.detection.storage import DetectionStorage
from transcribe.ingest import IngestService
from transcribe.runtime_paths import RuntimePaths
from transcribe.services.detection_finetune_export import (
    DetectionFinetuneExportOptions,
    DetectionFinetuneExportService,
)
from transcribe.services.project import ProjectService, open_project_paths


def _png() -> bytes:
    img = Image.new("RGB", (48, 48), (200, 180, 160))
    buf = BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def _notebook(tmp_path: Path, monkeypatch):
    data = tmp_path / "data"
    projects_dir = tmp_path / "projects"
    for path in (data, projects_dir, tmp_path / "inbox", tmp_path / "exports", data / "config"):
        path.mkdir(parents=True, exist_ok=True)
    runtime = RuntimePaths(
        repo_root=tmp_path,
        data_dir=data,
        projects_dir=projects_dir,
        inbox_dir=tmp_path / "inbox",
        export_dir=tmp_path / "exports",
    )
    monkeypatch.setenv("TRANSCRIBE_DATA_DIR", str(runtime.data_dir))
    monkeypatch.setenv("TRANSCRIBE_PROJECTS_DIR", str(runtime.projects_dir))
    paths = open_project_paths(projects_dir / "nb")
    clock, ids = FakeClock(), SequentialIds("dft")
    projects = ProjectService(paths, clock=clock, ids=ids)
    projects.create("detect-ft")
    IngestService(paths, clock=clock, ids=ids).import_bytes("p0.png", _png())
    page = projects.load().pages[0]
    projects.save_user_edit(page.page_id, "Buy milk and eggs — a short todo list.")
    return projects, page.page_id, clock, ids


def _seed_findings(projects: ProjectService, page_id: str, clock, ids) -> None:
    storage = DetectionStorage(projects.paths)
    now = "2026-01-01T00:00:00+00:00"
    notebook_id = projects.load().id
    findings = [
        DetectionFinding(
            finding_id=ids.new_id(),
            detector_id="todo_lists",
            detector_version="1",
            notebook_id=notebook_id,
            start_page_id=page_id,
            end_page_id=page_id,
            finding_type="todo_lists",
            confidence=0.9,
            evidence={"reason": "todo", "snippets": ["Buy milk"]},
            prompt_provenance={"prompt_id": "detect:todo_lists", "version": "1"},
            model_provenance={"model_name": "text", "model_digest": None, "input_mode": "text"},
            input_fingerprint="fp",
            created_at=now,
            updated_at=now,
            review_status="approved",
            detector_data={},
        ),
        DetectionFinding(
            finding_id=ids.new_id(),
            detector_id="todo_lists",
            detector_version="1",
            notebook_id=notebook_id,
            start_page_id=page_id,
            end_page_id=page_id,
            finding_type="todo_lists",
            confidence=0.4,
            evidence={"reason": "weak", "snippets": ["eggs"]},
            prompt_provenance={"prompt_id": "detect:todo_lists", "version": "1"},
            model_provenance={"model_name": "text", "model_digest": None, "input_mode": "text"},
            input_fingerprint="fp",
            created_at=now,
            updated_at=now,
            review_status="rejected",
            detector_data={},
        ),
        DetectionFinding(
            finding_id=ids.new_id(),
            detector_id="todo_lists",
            detector_version="1",
            notebook_id=notebook_id,
            start_page_id=page_id,
            end_page_id=page_id,
            finding_type="todo_lists",
            confidence=0.5,
            evidence={"reason": "maybe", "snippets": ["list"]},
            prompt_provenance={"prompt_id": "detect:todo_lists", "version": "1"},
            model_provenance={"model_name": "text", "model_digest": None, "input_mode": "text"},
            input_fingerprint="fp",
            created_at=now,
            updated_at=now,
            review_status="unreviewed",
            detector_data={},
        ),
    ]
    from transcribe.detection.envelope import build_detection_envelope
    from transcribe.detection.findings import findings_to_dicts

    env = build_detection_envelope(
        notebook_id=notebook_id,
        detector_id="todo_lists",
        detector_version="1",
        cache_identity="test-cache",
        scope_fingerprint="scope",
        attempt_state="succeeded",
        outcome="success",
        findings=findings_to_dicts(findings),
        pages_scanned=[page_id],
        windows_scanned=1,
        config_fingerprint="cfg",
        warnings=[],
        attempt_id=ids.new_id(),
        prompt_provenance={"prompt_id": "detect:todo_lists", "version": "1"},
        model_provenance={"model_name": "text", "model_digest": None, "input_mode": "text"},
        generation_settings={},
    )
    ok = storage.publish_if_current(
        detector_id="todo_lists",
        envelope=env,
        expected_cache_identity="test-cache",
        current_cache_identity="test-cache",
    )
    assert ok
    _ = DetectionService, clock


def test_detection_finetune_excludes_unreviewed_by_default(tmp_path: Path, monkeypatch):
    projects, page_id, clock, ids = _notebook(tmp_path, monkeypatch)
    _seed_findings(projects, page_id, clock, ids)
    out = DetectionFinetuneExportService(projects).export(
        tmp_path / "out",
        options=DetectionFinetuneExportOptions(),
    )
    rows = [
        json.loads(line)
        for line in (out / "samples.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    assert len(rows) == 2
    labels = sorted(r["label"] for r in rows)
    assert labels == ["approved", "rejected"]
    manifest = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["format"] == "transcribe.detection-finetune-export-manifest"
    assert manifest["sample_count"] == 2
    assert (out / "images" / f"{page_id}.png").is_file()


def test_detection_finetune_can_include_unreviewed(tmp_path: Path, monkeypatch):
    projects, page_id, clock, ids = _notebook(tmp_path, monkeypatch)
    _seed_findings(projects, page_id, clock, ids)
    out = DetectionFinetuneExportService(projects).export(
        tmp_path / "out2",
        options=DetectionFinetuneExportOptions(include_unreviewed=True),
    )
    rows = [
        json.loads(line)
        for line in (out / "samples.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    assert len(rows) == 3
