"""Deepened Phase 3–5 hardening coverage (offline)."""

from __future__ import annotations

from pathlib import Path

from PIL import Image

from transcribe.analysis.health import ModuleHealth, aggregate_module_health
from transcribe.analysis.plan import (
    AnalysisRunPlan,
    build_analysis_run_plan,
    compute_plan_hash,
    run_record_payload,
    verify_plan_hash,
)
from transcribe.analysis.runner import AnalysisRunner
from transcribe.analysis.storage import AnalysisStorage
from transcribe.domain.content_revision import (
    CONTENT_REVISION_VERSION,
    build_content_revision_object,
    content_revision_hex,
)
from transcribe.ingest import IngestService
from transcribe.persistence.atomic import read_json
from transcribe.services.export import ExportService
from transcribe.services.project import ProjectService, open_project_paths
from tests.conftest import FakeClock, SequentialIds


def _png_bytes() -> bytes:
    from io import BytesIO

    img = Image.new("RGB", (32, 32), (10, 20, 30))
    buf = BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def _project(tmp_path: Path, texts: list[str]):
    paths = open_project_paths(tmp_path / "proj")
    clock, ids = FakeClock(), SequentialIds("deep")
    projects = ProjectService(paths, clock=clock, ids=ids)
    projects.create("notebook")
    ingest = IngestService(paths, clock=clock, ids=ids)
    for i, _ in enumerate(texts):
        ingest.import_bytes(f"p{i}.png", _png_bytes())
    project = projects.load()
    for page, text in zip(project.pages, texts, strict=True):
        projects.save_user_edit(page.page_id, text)
    return projects, paths, clock, ids


def test_content_revision_changes_on_tags_and_reorder(tmp_path: Path):
    projects, paths, _clock, _ids = _project(
        tmp_path,
        [
            "Deep test page one with enough text for revision hashing identity.",
            "Deep test page two with enough text for revision hashing identity.",
        ],
    )
    rev0 = projects.content_revision()
    project = projects.load(reconcile=False)
    projects.update_page_metadata(project.pages[0].page_id, tags=["alpha", "beta"])
    rev_tags = projects.content_revision()
    assert rev_tags != rev0

    # Reorder pages in manifest
    project = projects.load(reconcile=False)
    pages = list(project.pages)
    pages[0], pages[1] = pages[1], pages[0]
    from transcribe.persistence.atomic import write_json_atomic
    from transcribe.persistence.locks import mutation_lock

    with mutation_lock(paths.mutation_lock):
        project.pages = pages
        write_json_atomic(paths.manifest, project.as_dict())
    rev_order = projects.content_revision()
    assert rev_order != rev_tags


def test_content_revision_object_version_and_sorted_tags(tmp_path: Path):
    projects, _paths, _clock, _ids = _project(
        tmp_path,
        ["Object shape page with enough text for building revision object body."],
    )
    project = projects.load(reconcile=False)
    projects.update_page_metadata(project.pages[0].page_id, tags=["zulu", "alpha"])
    project = projects.load(reconcile=False)
    results = {p.page_id: projects.load_page_result(p.page_id) for p in project.pages}
    obj = build_content_revision_object(project, results)
    assert obj["content_revision_version"] == CONTENT_REVISION_VERSION
    assert obj["pages"][0]["tags"] == ["alpha", "zulu"]
    assert content_revision_hex(project, results) == projects.content_revision()


def test_run_record_embeds_plan_hash_and_preset_identity(tmp_path: Path):
    projects, paths, clock, ids = _project(
        tmp_path,
        ["Run record plan hash page with enough text for a successful stats run."],
    )
    plan = build_analysis_run_plan(
        project_service=projects,
        module_ids=["stats"],
        preset_key="balanced",
        preset_content_version=2,
        preset_policy_fingerprint="deadbeef",
        preset_label="Balanced",
        clock=clock,
        ids=ids,
    )
    payload = run_record_payload(plan, status="running")
    assert payload["plan_hash"] == plan.plan_hash
    assert payload["preset_key"] == "balanced"
    assert payload["preset_content_version"] == 2
    assert payload["plan"]["plan_hash"] == plan.plan_hash
    storage = AnalysisStorage(paths)
    storage.write_run_record(payload)
    loaded = storage.read_run_record(plan.run_id)
    assert loaded is not None
    restored = AnalysisRunPlan.from_dict(loaded["plan"])
    assert verify_plan_hash(restored)


def test_plan_hash_ignores_ephemeral_run_id_and_created_at(tmp_path: Path):
    projects, _paths, clock, ids = _project(
        tmp_path,
        ["Ephemeral fields page with enough text for plan hash stability checks."],
    )
    plan = build_analysis_run_plan(
        project_service=projects,
        module_ids=["stats"],
        clock=clock,
        ids=ids,
    )
    twin = AnalysisRunPlan(
        run_id="other-run-id",
        project_id=plan.project_id,
        module_ids=plan.module_ids,
        question_text=plan.question_text,
        effective_config=plan.effective_config,
        config_fingerprint=plan.config_fingerprint,
        text_model=plan.text_model,
        plan_hash="",
        preset_label=plan.preset_label,
        preset_key=plan.preset_key,
        preset_content_version=plan.preset_content_version,
        preset_policy_fingerprint=plan.preset_policy_fingerprint,
        created_at="2099-01-01T00:00:00Z",
    )
    assert compute_plan_hash(twin) == plan.plan_hash


def test_aggregate_failed_beats_degraded():
    modules = [
        ModuleHealth(
            "a",
            "ok",
            "unavailable_model",
            "insufficient_data",
            {"capability": "unavailable_model", "outcome": "insufficient_data"},
            [],
        ),
        ModuleHealth(
            "b",
            "ok",
            "failed",
            "failed",
            {"capability": "failed", "outcome": "failed"},
            [],
        ),
    ]
    assert aggregate_module_health(modules) == "failed"


def test_export_revision_matches_service_content_revision(tmp_path: Path):
    projects, paths, _clock, _ids = _project(
        tmp_path,
        [
            "Export match page one with enough text for coherent revision binding.",
            "Export match page two with enough text for coherent revision binding.",
        ],
    )
    rev = projects.content_revision()
    written = ExportService(paths, projects).export_all(dest_dir=tmp_path / "out")
    notebook = read_json(written["notebook"])
    assert notebook["content_revision"] == rev
    # Analysis batch + export still share revision token
    runner = AnalysisRunner(projects, clock=FakeClock(), ids=SequentialIds("x"))
    runner.run_batch(["stats"])
    assert projects.content_revision() == rev
