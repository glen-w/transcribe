"""Prompt hub persistence and catalogue tests."""

from __future__ import annotations

from pathlib import Path

from transcribe.prompt_engine.definition import (
    InputMode,
    ModelCapability,
    ModelRequirements,
    PromptDefinition,
    PromptFamily,
    validate_prompt_definition,
)
from transcribe.prompt_engine.hub import (
    list_catalogue,
    ocr_render_for_job,
    resolve_prompt,
)
from transcribe.prompt_engine.store import (
    delete_override,
    load_overrides,
    save_custom_prompt,
    save_override,
)
from transcribe.runtime_paths import RuntimePaths


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


def test_catalogue_includes_ocr_and_detection(tmp_path: Path):
    rt = _rt(tmp_path)
    cat = list_catalogue(runtime=rt)
    ids = {e.definition.prompt_id for e in cat}
    assert "faithful_markdown" in ids
    assert "free_ocr" in ids
    assert "cleanup_strip_leak" in ids
    assert "poetry_detect_text_v1" in ids
    assert "todo_lists_detect_text_v1" in ids
    assert "beer_labels_detect_text_v1" in ids


def test_override_wins_over_detector_version_pin(tmp_path: Path):
    """Workspace override always wins even when caller pins builtin version."""
    rt = _rt(tmp_path)
    base = resolve_prompt("poetry_detect_text_v1", version="1", runtime=rt)
    assert base is not None
    ov = PromptDefinition(
        prompt_id=base.prompt_id,
        version="9",
        title=base.title,
        description=base.description,
        system_prompt=base.system_prompt + "\nOverride v9.",
        user_template=base.user_template,
        input_mode=base.input_mode,
        response_schema_id=base.response_schema_id,
        model_requirements=base.model_requirements,
        prompt_family=PromptFamily.DETECTION,
        is_override=True,
        is_builtin=False,
    )
    save_override(ov, runtime=rt)
    resolved = resolve_prompt("poetry_detect_text_v1", version="1", runtime=rt)
    assert resolved is not None
    assert resolved.version == "9"
    assert "Override v9." in resolved.system_prompt


def test_override_bumps_and_resolves(tmp_path: Path):
    rt = _rt(tmp_path)
    base = resolve_prompt("poetry_detect_text_v1", runtime=rt)
    assert base is not None
    ov = PromptDefinition(
        prompt_id=base.prompt_id,
        version="2",
        title=base.title,
        description=base.description,
        system_prompt=base.system_prompt + "\nExtra.",
        user_template=base.user_template,
        input_mode=base.input_mode,
        response_schema_id=base.response_schema_id,
        model_requirements=base.model_requirements,
        prompt_family=PromptFamily.DETECTION,
        is_override=True,
        is_builtin=False,
    )
    assert not validate_prompt_definition(ov)
    save_override(ov, runtime=rt)
    resolved = resolve_prompt("poetry_detect_text_v1", runtime=rt)
    assert resolved is not None
    assert resolved.version == "2"
    assert "Extra." in resolved.system_prompt
    delete_override("poetry_detect_text_v1", runtime=rt)
    assert "poetry_detect_text_v1" not in load_overrides(rt)


def test_system_prompt_slots_rejected():
    bad = PromptDefinition(
        prompt_id="x",
        version="1",
        title="x",
        description="",
        system_prompt="See {{content}}",
        user_template="{{content}}",
        input_mode=InputMode.TEXT,
        response_schema_id="custom_finding_v1",
        model_requirements=ModelRequirements(capability=ModelCapability.TEXT),
    )
    errs = validate_prompt_definition(bad)
    assert any("system_prompt" in e for e in errs)


def test_ocr_render_sha_stable_without_override(tmp_path: Path):
    rt = _rt(tmp_path)
    from transcribe.prompts import render_prompt

    a = ocr_render_for_job(prompt_id="faithful_markdown", runtime=rt)
    b = render_prompt(prompt_id="faithful_markdown")
    assert a[0] == b[0]
    assert a[2] == b[2]


def test_custom_prompt_save(tmp_path: Path):
    rt = _rt(tmp_path)
    defn = PromptDefinition(
        prompt_id="custom/test_prompt",
        version="1",
        title="Test",
        description="",
        system_prompt="JSON only.",
        user_template="{{content}}",
        input_mode=InputMode.TEXT,
        response_schema_id="custom_finding_v1",
        prompt_family=PromptFamily.CUSTOM,
        is_builtin=False,
    )
    save_custom_prompt(defn, runtime=rt)
    resolved = resolve_prompt("custom/test_prompt", runtime=rt)
    assert resolved is not None
    assert resolved.title == "Test"
