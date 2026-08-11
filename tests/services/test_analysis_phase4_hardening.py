"""Phase 4 product hardening: content_revision + shared AnalysisHealth."""

from __future__ import annotations

from pathlib import Path

from PIL import Image

from transcribe.analysis.health import (
    ModuleHealth,
    aggregate_module_health,
    derive_analysis_health,
    scope_analysis_health,
)
from transcribe.analysis.runner import AnalysisRunner
from transcribe.analysis.storage import AnalysisStorage
from transcribe.domain.content_revision import content_revision_hex
from transcribe.ingest import IngestService
from transcribe.services.project import ProjectService, open_project_paths
from tests.conftest import FakeClock, SequentialIds


def _png_bytes() -> bytes:
    from io import BytesIO

    img = Image.new("RGB", (32, 32), (10, 20, 30))
    buf = BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def _project_with_pages(tmp_path: Path, texts: list[str]):
    paths = open_project_paths(tmp_path / "proj")
    clock, ids = FakeClock(), SequentialIds("p4")
    projects = ProjectService(paths, clock=clock, ids=ids)
    projects.create("notebook")
    ingest = IngestService(paths, clock=clock, ids=ids)
    for i, _ in enumerate(texts):
        ingest.import_bytes(f"p{i}.png", _png_bytes())
    project = projects.load()
    for page, text in zip(project.pages, texts, strict=True):
        projects.save_user_edit(page.page_id, text)
    return projects, AnalysisRunner(projects, clock=clock, ids=ids), clock, ids, paths


def test_content_revision_changes_on_edit_and_stable_otherwise(tmp_path: Path):
    projects, _runner, _clock, _ids, _paths = _project_with_pages(
        tmp_path,
        [
            "Revision notebook page one with enough text for identity hashing.",
            "Revision notebook page two also carries sufficient text content.",
        ],
    )
    rev1 = projects.content_revision()
    rev2 = projects.content_revision()
    assert rev1 == rev2
    assert len(rev1) == 64

    project = projects.load(reconcile=False)
    projects.save_user_edit(
        project.pages[0].page_id,
        "Revision notebook page one EDITED with enough text for identity hashing.",
    )
    rev3 = projects.content_revision()
    assert rev3 != rev1


def test_content_revision_matches_hex_helper(tmp_path: Path):
    projects, runner, _clock, _ids, paths = _project_with_pages(
        tmp_path,
        [
            "Included page with plenty of handwritten notebook text for analysis.",
            "Also included second page text that stays in the export membership set.",
        ],
    )
    rev = projects.content_revision()
    project = projects.load(reconcile=False)
    results = {
        p.page_id: projects.load_page_result(p.page_id) for p in project.pages
    }
    assert content_revision_hex(project, results) == rev

    storage = AnalysisStorage(paths)
    health = derive_analysis_health(
        storage=storage,
        runner=runner,
        module_ids=["stats"],
        content_revision=rev,
    )
    assert health.aggregate == "missing"
    assert health.content_revision == rev


def test_shared_health_scope_agrees_on_overlapping_modules(tmp_path: Path):
    projects, runner, _clock, _ids, paths = _project_with_pages(
        tmp_path,
        [
            "Shared health notebook text with enough content for stats success runs.",
            "Second page also has sufficient content for diversity metrics here now.",
        ],
    )
    results = runner.run_batch(["stats", "lexical_diversity"])
    assert results["stats"]["outcome"] == "success"
    storage = AnalysisStorage(paths)
    rev = projects.content_revision()
    batch = derive_analysis_health(
        storage=storage,
        runner=runner,
        module_ids=["stats", "lexical_diversity", "sentiment"],
        content_revision=rev,
    )
    overview = scope_analysis_health(batch, ["stats", "lexical_diversity"])
    overlap = scope_analysis_health(batch, ["stats"])
    assert overview.modules["stats"].freshness == batch.modules["stats"].freshness
    assert overlap.modules["stats"].as_dict() == overview.modules["stats"].as_dict()
    assert overview.aggregate == "healthy"
    # Unavailable modules do not force missing unless ALL scoped modules are unavailable.
    assert batch.aggregate == "healthy"


def test_aggregate_transitions():
    missing = [
        ModuleHealth("a", "unavailable", None, None, None, []),
        ModuleHealth("b", "unavailable", None, None, None, []),
    ]
    assert aggregate_module_health(missing) == "missing"
    assert aggregate_module_health(missing, active_run_status="running") == "running"
    assert aggregate_module_health(missing, active_run_status="interrupted") == "interrupted"

    stale = [
        ModuleHealth("a", "ok", "available", "success", {"outcome": "success"}, []),
        ModuleHealth("b", "stale", "available", "success", {"outcome": "success"}, []),
    ]
    assert aggregate_module_health(stale) == "stale"

    degraded = [
        ModuleHealth(
            "a",
            "ok",
            "unavailable_model",
            "insufficient_data",
            {"capability": "unavailable_model", "outcome": "insufficient_data"},
            [],
        )
    ]
    assert aggregate_module_health(degraded) == "degraded"

    healthy = [
        ModuleHealth(
            "a",
            "ok",
            "available",
            "success",
            {"capability": "available", "outcome": "success"},
            [],
        )
    ]
    assert aggregate_module_health(healthy) == "healthy"


def test_health_becomes_stale_after_edit(tmp_path: Path):
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
