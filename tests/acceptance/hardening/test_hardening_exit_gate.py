"""Product-hardening acceptance gate (ROADMAP exit).

Covers the five exit bullets:

1. Crash/reopen — orphaned attempts/runs become interrupted; published intact
2. Stale detection — edits make health stale
3. Offline operation — deterministic modules succeed without live Ollama
4. Export provenance — content_revision coherent across artifacts
5. Normal Analyse workflows — product UX language (no module-console literacy)

Deep coverage remains in ``tests/services/test_analysis_phase*.py``; this package
names the gate and is marked ``smoke`` for pre-release.
"""

from __future__ import annotations

from io import BytesIO
from pathlib import Path

import pytest
from PIL import Image

from transcribe.analysis.health import (
    ModuleHealth,
    aggregate_module_health,
    derive_analysis_health,
)
from transcribe.analysis.plan import build_analysis_run_plan, run_record_payload
from transcribe.analysis.runner import AnalysisRunner
from transcribe.analysis.storage import AnalysisStorage
from transcribe.domain.content_revision import content_revision_hex
from transcribe.ingest import IngestService
from transcribe.persistence.atomic import read_json
from transcribe.services.export import ExportService
from transcribe.services.project import ProjectService, open_project_paths
from transcribe.ui.analysis_health_view import (
    last_run_product_summary,
    product_aggregate_label,
    product_capability_label,
)
from tests.conftest import FakeClock, SequentialIds


def _png_bytes() -> bytes:
    img = Image.new("RGB", (32, 32), (10, 20, 30))
    buf = BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def _project_with_pages(tmp_path: Path, texts: list[str], *, prefix: str = "gate"):
    paths = open_project_paths(tmp_path / "proj")
    clock, ids = FakeClock(), SequentialIds(prefix)
    projects = ProjectService(paths, clock=clock, ids=ids)
    projects.create("notebook")
    ingest = IngestService(paths, clock=clock, ids=ids)
    for i, _ in enumerate(texts):
        ingest.import_bytes(f"p{i}.png", _png_bytes())
    project = projects.load()
    for page, text in zip(project.pages, texts, strict=True):
        projects.save_user_edit(page.page_id, text)
    runner = AnalysisRunner(projects, clock=clock, ids=ids)
    return projects, runner, clock, ids, paths


@pytest.mark.smoke
def test_gate_crash_reopen_interrupts_without_clobber(tmp_path: Path):
    """Exit bullet 1 — crash/reopen marks interrupted; published untouched."""
    projects, runner, clock, ids, _paths = _project_with_pages(
        tmp_path,
        ["Published notebook text with sufficient content for stats module."],
    )
    published = runner.run_module("stats")
    assert published["outcome"] == "success"
    storage = AnalysisStorage(projects.paths)
    orphan = dict(published)
    orphan["attempt_id"] = "orphan-running"
    orphan["attempt_state"] = "running"
    orphan["published"] = False
    storage.write_attempt("stats", orphan)

    plan = build_analysis_run_plan(
        project_service=projects,
        module_ids=["stats"],
        clock=clock,
        ids=ids,
    )
    storage.write_run_record(
        run_record_payload(plan, status="running", message="crashed mid-flight")
    )
    before = storage.read_published("stats")
    projects.load(reconcile=True)
    after_attempt = storage.read_attempt("stats", "orphan-running")
    assert after_attempt is not None
    assert after_attempt["attempt_state"] == "interrupted"
    assert storage.read_published("stats")["cache_identity"] == before["cache_identity"]
    record = storage.read_run_record(plan.run_id)
    assert record is not None
    assert record["status"] == "interrupted"


@pytest.mark.smoke
def test_gate_stale_detection_after_edit(tmp_path: Path):
    """Exit bullet 2 — health becomes stale after notebook edit."""
    projects, runner, _clock, _ids, paths = _project_with_pages(
        tmp_path,
        ["Stale after edit notebook text with enough words for successful stats."],
    )
    runner.run_batch(["stats"])
    storage = AnalysisStorage(paths)
    rev = projects.content_revision()
    before = derive_analysis_health(
        storage=storage,
        runner=runner,
        module_ids=["stats"],
        content_revision=rev,
    )
    assert before.aggregate == "healthy"
    assert before.modules["stats"].freshness == "ok"

    project = projects.load(reconcile=False)
    projects.save_user_edit(
        project.pages[0].page_id,
        "Stale after edit notebook text CHANGED with enough words for successful stats.",
    )
    after = derive_analysis_health(
        storage=storage,
        runner=runner,
        module_ids=["stats"],
        content_revision=projects.content_revision(),
    )
    assert after.modules["stats"].freshness == "stale"
    assert after.aggregate == "stale"


@pytest.mark.smoke
def test_gate_offline_deterministic_stats(tmp_path: Path):
    """Exit bullet 3 — deterministic module runs offline (no Ollama)."""
    _projects, runner, _clock, _ids, _paths = _project_with_pages(
        tmp_path,
        ["Offline notebook text with enough content for deterministic stats success."],
    )
    env = runner.run_module("stats")
    assert env.get("capability") != "unavailable_model"
    assert env["outcome"] == "success"
    assert env.get("published") is True


@pytest.mark.smoke
def test_gate_export_provenance_revision(tmp_path: Path):
    """Exit bullet 4 — export artifacts share content_revision."""
    projects, _runner, _clock, _ids, paths = _project_with_pages(
        tmp_path,
        [
            "Export provenance page one with enough text for a stable revision.",
            "Export provenance page two also carries enough text content here.",
        ],
        prefix="exp",
    )
    service = ExportService(paths, projects)
    snap = service.capture_snapshot()
    expected = content_revision_hex(snap.project, snap.results)
    assert snap.content_revision == expected

    written = service.export_all(dest_dir=tmp_path / "out")
    notebook = read_json(written["notebook"])
    manifest = read_json(written["manifest"])
    md = written["markdown"].read_text(encoding="utf-8")
    txt = written["text"].read_text(encoding="utf-8")

    assert notebook["content_revision"] == expected
    assert manifest["content_revision"] == expected
    assert md.startswith(f"<!-- transcribe.content_revision: {expected} -->")
    assert txt.startswith(f"# transcribe.content_revision: {expected}")


@pytest.mark.smoke
def test_gate_product_language_and_last_run_summary():
    """Exit bullet 5 — ordinary workflows use product language, not enums."""
    assert product_capability_label("unavailable_model") == "Needs a text model"
    assert (
        product_capability_label("unavailable_extra")
        == "Optional component not installed"
    )
    assert product_capability_label(None, "insufficient_data") == "Not enough text yet"
    assert product_aggregate_label("stale") == "Out of date"
    assert product_aggregate_label("interrupted") == "Interrupted"
    summary = last_run_product_summary(
        {
            "stats": {"outcome": "success", "capability": "success"},
            "ner": {"outcome": "success", "capability": "success"},
        },
        preset_label="Balanced",
    )
    assert "Balanced" in summary
    assert "2 modules" in summary
    assert "healthy" in summary
    assert "outcome=" not in summary


@pytest.mark.smoke
def test_gate_aggregate_interrupted_beats_module_state():
    modules = [
        ModuleHealth(
            module_id="stats",
            freshness="ok",
            capability="success",
            outcome="success",
            envelope={},
            live_evidence=[],
        )
    ]
    assert (
        aggregate_module_health(modules, active_run_status="interrupted")
        == "interrupted"
    )
    assert aggregate_module_health(modules, active_run_status="running") == "running"
