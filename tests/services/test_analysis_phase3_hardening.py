"""Phase 3 product hardening: plan_hash bind + versioned presets."""

from __future__ import annotations

from pathlib import Path

from PIL import Image

from transcribe.analysis.coordinator import AnalysisCoordinator
from transcribe.analysis.plan import (
    AnalysisRunPlan,
    PlanHashMismatchError,
    build_analysis_run_plan,
    compute_plan_hash,
    verify_plan_hash,
)
from transcribe.analysis.presets import (
    bump_preset_content_versions,
    custom_modules_fingerprint,
    resolve_analysis_preset,
)
from transcribe.analysis.runner import AnalysisRunner
from transcribe.config.facade import clear_config_cache, require_operation_config
from transcribe.config.models import PresetPolicyConfig
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
    clock, ids = FakeClock(), SequentialIds("p3")
    projects = ProjectService(paths, clock=clock, ids=ids)
    projects.create("notebook")
    ingest = IngestService(paths, clock=clock, ids=ids)
    for i, _ in enumerate(texts):
        ingest.import_bytes(f"p{i}.png", _png_bytes())
    project = projects.load()
    for page, text in zip(project.pages, texts, strict=True):
        projects.save_user_edit(page.page_id, text)
    return projects, AnalysisRunner(projects, clock=clock, ids=ids), clock, ids


def test_plan_hash_stable_across_serialize_round_trip(tmp_path: Path):
    projects, _runner, clock, ids = _project_with_pages(
        tmp_path,
        ["Plan hash notebook text with enough content for stats module success."],
    )
    plan = build_analysis_run_plan(
        project_service=projects,
        module_ids=["stats"],
        preset_key="balanced",
        preset_content_version=1,
        preset_policy_fingerprint="abc",
        preset_label="Balanced",
        clock=clock,
        ids=ids,
    )
    assert plan.plan_hash
    assert verify_plan_hash(plan)
    restored = AnalysisRunPlan.from_dict(plan.as_dict())
    assert restored.plan_hash == plan.plan_hash
    assert verify_plan_hash(restored)
    assert compute_plan_hash(restored) == plan.plan_hash


def test_plan_hash_changes_with_modules_and_preset_version(tmp_path: Path):
    projects, _runner, clock, ids = _project_with_pages(
        tmp_path,
        ["Hash sensitivity text with enough words for stats and lexical diversity."],
    )
    base = build_analysis_run_plan(
        project_service=projects,
        module_ids=["stats"],
        preset_key="quick",
        preset_content_version=1,
        preset_policy_fingerprint="fp1",
        clock=clock,
        ids=ids,
    )
    more_modules = build_analysis_run_plan(
        project_service=projects,
        module_ids=["stats", "lexical_diversity"],
        preset_key="quick",
        preset_content_version=1,
        preset_policy_fingerprint="fp1",
        clock=clock,
        ids=ids,
    )
    bumped = build_analysis_run_plan(
        project_service=projects,
        module_ids=["stats"],
        preset_key="quick",
        preset_content_version=2,
        preset_policy_fingerprint="fp1",
        clock=clock,
        ids=ids,
    )
    assert base.plan_hash != more_modules.plan_hash
    assert base.plan_hash != bumped.plan_hash


def test_pending_freeze_survives_settings_mutation(tmp_path: Path):
    projects, runner, clock, ids = _project_with_pages(
        tmp_path,
        [
            "Frozen pending plan text with enough content for stats and lexical.",
            "Second page also has sufficient content for diversity metrics here.",
        ],
    )
    plan = build_analysis_run_plan(
        project_service=projects,
        module_ids=["stats", "lexical_diversity"],
        preset_key="balanced",
        preset_content_version=1,
        preset_policy_fingerprint="fp",
        clock=clock,
        ids=ids,
    )
    pending = {"plan": plan.as_dict(), "plan_hash": plan.plan_hash}

    settings = projects.load(reconcile=False).settings
    settings.model_name = "mutated-after-freeze"
    projects.save_settings(projects.load(reconcile=False), settings)
    clear_config_cache()

    restored = AnalysisRunPlan.from_dict(pending["plan"])
    assert restored.plan_hash == pending["plan_hash"]
    assert verify_plan_hash(restored)
    results = runner.run_batch_from_plan(restored)
    assert set(results) == {"stats", "lexical_diversity"}
    assert restored.effective_config.as_dict() == plan.effective_config.as_dict()
    assert projects.load(reconcile=False).settings.model_name == "mutated-after-freeze"


def test_coordinator_refuses_tampered_plan_hash(tmp_path: Path):
    projects, _runner, clock, ids = _project_with_pages(
        tmp_path,
        ["Tamper refusal notebook text with enough words for a successful stats run."],
    )
    plan = build_analysis_run_plan(
        project_service=projects,
        module_ids=["stats"],
        clock=clock,
        ids=ids,
    )
    bad = AnalysisRunPlan(
        run_id=plan.run_id,
        project_id=plan.project_id,
        module_ids=plan.module_ids,
        question_text=plan.question_text,
        effective_config=plan.effective_config,
        config_fingerprint=plan.config_fingerprint,
        text_model=plan.text_model,
        plan_hash="0" * 64,
        preset_label=plan.preset_label,
        preset_key=plan.preset_key,
        preset_content_version=plan.preset_content_version,
        preset_policy_fingerprint=plan.preset_policy_fingerprint,
        created_at=plan.created_at,
    )
    coord = AnalysisCoordinator(projects, clock=clock, ids=ids)
    try:
        coord.start(bad)
        raise AssertionError("expected PlanHashMismatchError")
    except PlanHashMismatchError:
        pass


def test_bump_preset_content_versions_only_when_body_changes():
    previous = {
        "quick": PresetPolicyConfig(allow_llm=False, content_version=1).as_dict(),
        "balanced": PresetPolicyConfig(
            allow_llm=True, llm_module_ids=("llm_summary",), content_version=3
        ).as_dict(),
        "thorough": PresetPolicyConfig(
            allow_llm=True, include_excluded_from_default=True, content_version=2
        ).as_dict(),
    }
    unchanged = bump_preset_content_versions(previous, previous)
    assert unchanged["quick"]["content_version"] == 1
    assert unchanged["balanced"]["content_version"] == 3
    assert unchanged["thorough"]["content_version"] == 2

    next_draft = {
        "quick": dict(previous["quick"]),
        "balanced": {
            **previous["balanced"],
            "llm_module_ids": ["llm_summary", "llm_action_items"],
        },
        "thorough": dict(previous["thorough"]),
    }
    bumped = bump_preset_content_versions(previous, next_draft)
    assert bumped["quick"]["content_version"] == 1
    assert bumped["balanced"]["content_version"] == 4
    assert bumped["thorough"]["content_version"] == 2
    assert bumped["balanced"]["llm_module_ids"] == ["llm_summary", "llm_action_items"]


def test_custom_modules_fingerprint_changes_with_selection():
    a = custom_modules_fingerprint(["stats", "ner"])
    b = custom_modules_fingerprint(["ner", "stats"])
    c = custom_modules_fingerprint(["stats"])
    assert a != b  # order matters for selected list identity
    assert a != c


def test_resolve_named_preset_exposes_version_and_fingerprint():
    clear_config_cache()
    cfg = require_operation_config()
    resolved = resolve_analysis_preset("balanced", effective=cfg)
    assert resolved.preset == "balanced"
    assert resolved.content_version >= 1
    assert len(resolved.policy_fingerprint) == 64
    custom = resolve_analysis_preset(
        "custom", custom_modules=["stats", "lexical_diversity"], effective=cfg
    )
    assert custom.preset == "custom"
    assert custom.content_version == 0
    assert custom.policy_fingerprint == custom_modules_fingerprint(custom.module_ids)
