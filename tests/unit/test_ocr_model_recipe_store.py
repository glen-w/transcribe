"""Workspace OCR recipe overlay merge, save, and corrupt fallback."""

from __future__ import annotations

from pathlib import Path

import pytest

from transcribe.config.errors import (
    OCR_RECIPES_CORRUPT,
    OCR_RECIPES_INVALID,
    OCR_RECIPES_SCHEMA_UNSUPPORTED,
    ConfigError,
)
from transcribe.domain.models import AttemptProvenance
from transcribe.persistence.atomic import write_json_atomic
from transcribe.persistence.schema import SUPPORTED
from transcribe.runtime_paths import RuntimePaths
from transcribe.services.ocr_model_recipe_store import (
    load_recipes,
    recipes_path,
    reset_overlay,
    save_overlay_rows,
    set_recipe_enabled,
    upsert_overlay_row,
)
from transcribe.services.ocr_model_recipes import RECIPES, recipe_for_model


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


def test_missing_file_uses_builtins(tmp_path: Path) -> None:
    runtime = _rt(tmp_path)
    loaded = load_recipes(runtime)
    assert loaded.ok
    assert loaded.overlay_rows == ()
    ids = [r.recipe_id for r in loaded.effective]
    assert ids == [r.recipe_id for r in RECIPES]
    assert recipe_for_model("glm-ocr:latest", runtime=runtime) is not None


def test_disable_builtin(tmp_path: Path) -> None:
    runtime = _rt(tmp_path)
    set_recipe_enabled("glm_ocr", False, runtime=runtime)
    assert recipe_for_model("glm-ocr:latest", runtime=runtime) is None
    loaded = load_recipes(runtime)
    glm = next(r for r in loaded.effective if r.recipe_id == "glm_ocr")
    assert glm.enabled is False
    assert glm.source == "override"


def test_overlay_replaces_repeat_penalty(tmp_path: Path) -> None:
    runtime = _rt(tmp_path)
    upsert_overlay_row(
        {"recipe_id": "glm_ocr", "generation_options": {"repeat_penalty": 1.35}},
        runtime=runtime,
    )
    recipe = recipe_for_model("glm-ocr", runtime=runtime)
    assert recipe is not None
    assert recipe.generation_options.get("repeat_penalty") == 1.35
    assert recipe.generation_options.get("stop") == ["```"]
    assert recipe.source == "override"


def test_custom_recipe_matches_first(tmp_path: Path) -> None:
    runtime = _rt(tmp_path)
    upsert_overlay_row(
        {
            "recipe_id": "got_ocr_short",
            "title": "GOT OCR",
            "match_tokens": ["got-ocr"],
            "prompt_id": "free_ocr",
            "freeze_prompt": True,
            "warnings": ["Short prompt for GOT-OCR-style tags."],
        },
        runtime=runtime,
    )
    recipe = recipe_for_model("got-ocr:latest", runtime=runtime)
    assert recipe is not None
    assert recipe.recipe_id == "got_ocr_short"
    assert recipe.source == "custom"
    assert recipe.freeze_prompt is True
    glm = recipe_for_model("glm-ocr", runtime=runtime)
    assert glm is not None
    assert glm.recipe_id == "glm_ocr"


def test_corrupt_file_falls_back_to_builtins(tmp_path: Path) -> None:
    runtime = _rt(tmp_path)
    path = recipes_path(runtime)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("{not json", encoding="utf-8")
    loaded = load_recipes(runtime)
    assert loaded.error_code == OCR_RECIPES_CORRUPT
    assert [r.recipe_id for r in loaded.effective] == [r.recipe_id for r in RECIPES]
    assert path.read_text(encoding="utf-8") == "{not json"


def test_unsupported_schema_falls_back(tmp_path: Path) -> None:
    runtime = _rt(tmp_path)
    path = recipes_path(runtime)
    path.parent.mkdir(parents=True, exist_ok=True)
    write_json_atomic(
        path,
        {
            "format": "transcribe.ocr-model-recipes",
            "schema_version": 2,
            "recipes": [],
        },
    )
    loaded = load_recipes(runtime)
    assert loaded.error_code == OCR_RECIPES_SCHEMA_UNSUPPORTED
    assert recipe_for_model("deepseek-ocr", runtime=runtime) is not None


def test_unknown_prompt_id_rejected(tmp_path: Path) -> None:
    runtime = _rt(tmp_path)
    with pytest.raises(ConfigError) as exc:
        upsert_overlay_row(
            {
                "recipe_id": "bad_prompt",
                "title": "Bad",
                "match_tokens": ["nope"],
                "prompt_id": "not_a_real_prompt",
                "freeze_prompt": True,
            },
            runtime=runtime,
        )
    assert exc.value.code == OCR_RECIPES_INVALID


def test_reset_overlay_writes_empty(tmp_path: Path) -> None:
    runtime = _rt(tmp_path)
    set_recipe_enabled("glm_ocr", False, runtime=runtime)
    reset_overlay(runtime=runtime)
    loaded = load_recipes(runtime)
    assert loaded.ok
    assert loaded.overlay_rows == ()
    glm = recipe_for_model("glm-ocr", runtime=runtime)
    assert glm is not None
    assert glm.enabled is True


def test_format_registered() -> None:
    assert SUPPORTED.get("transcribe.ocr-model-recipes") == 1


def test_provenance_recipe_id_roundtrip() -> None:
    prov = AttemptProvenance(
        model_name="glm-ocr",
        model_digest="d" * 64,
        model_identity_verified=True,
        prompt_id="faithful_markdown",
        prompt_version="2",
        prompt_sha256="a" * 64,
        prompt_text="p",
        input_sha256="b" * 64,
        preprocess_profile="none",
        preprocess_version=1,
        generation_options={"repeat_penalty": 1.2},
        application_version="1.0.0",
        ollama_host="http://localhost:11434",
        request_id="r1",
        render_id="render1",
        recipe_id="glm_ocr",
    )
    loaded = AttemptProvenance.from_dict(prov.as_dict())
    assert loaded.recipe_id == "glm_ocr"
    payload = prov.as_dict()
    payload.pop("recipe_id")
    legacy = AttemptProvenance.from_dict(payload)
    assert legacy.recipe_id == ""


def test_save_rejects_unsupported_option_key(tmp_path: Path) -> None:
    runtime = _rt(tmp_path)
    with pytest.raises(ConfigError) as exc:
        save_overlay_rows(
            [
                {
                    "recipe_id": "glm_ocr",
                    "generation_options": {"mirostat": 1},
                }
            ],
            runtime=runtime,
        )
    assert exc.value.code == OCR_RECIPES_INVALID
