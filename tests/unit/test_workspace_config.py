"""Workspace config: defaults parity, precedence, persistence, profiles."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from transcribe.analysis.cache_identity import config_fingerprint
from transcribe.analysis.presets import BUILTIN_PRESET_POLICIES, resolve_analysis_preset
from transcribe.config.defaults import RESERVED_PROFILE_NAMES, builtin_profile_config
from transcribe.config.errors import (
    PROFILE_RESERVED_NAME,
    SETTINGS_CORRUPT,
    SETTINGS_SCHEMA_UNSUPPORTED,
    ConfigError,
)
from transcribe.config.facade import (
    bind_operation_config,
    clear_config_cache,
    get_config,
    reload_config,
    require_operation_config,
    snapshot_for_operation,
)
from transcribe.config.knobs import module_knob_dict
from transcribe.config.models import EffectiveConfig, ProfileActivations
from transcribe.config.persistence import (
    load_workspace_settings,
    save_workspace_settings,
    settings_path,
)
from transcribe.config.profiles import save_user_profile, validate_profile_name
from transcribe.config.resolve import resolve_effective_config
from transcribe.config.versions import ANALYSIS_CONFIG_VERSION, CURRENT_SETTINGS_SCHEMA_VERSION
from transcribe.domain.models import OCRSettings
from transcribe.runtime_paths import RuntimePaths


@pytest.fixture()
def runtime(tmp_path: Path) -> RuntimePaths:
    clear_config_cache()
    data = tmp_path / "data"
    data.mkdir()
    (data / "config").mkdir()
    return RuntimePaths(
        repo_root=tmp_path,
        data_dir=data,
        projects_dir=tmp_path / "projects",
        inbox_dir=tmp_path / "inbox",
        export_dir=tmp_path / "exports",
    )


def test_defaults_parity_matches_shipped_presets(runtime: RuntimePaths) -> None:
    view = reload_config(runtime=runtime)
    policies = view.effective.analysis.ui_presets
    assert policies.quick.allow_llm is False
    assert policies.balanced.llm_module_ids == ("llm_summary",)
    assert policies.balanced.heavy_module_ids == ("semantic_similarity",)
    assert policies.thorough.include_excluded_from_default is True
    assert view.effective.analysis.keyphrases.top_n == 25
    assert view.effective.analysis.highlights.top_n == 12
    assert view.effective.analysis.moments.top_n == 10
    assert view.effective.analysis.semantic_similarity.motif_threshold == 0.55
    assert view.effective.analysis.topic_shift.shift_threshold == 0.25
    assert view.effective.analysis.wordclouds.max_tokens == 100
    assert view.effective.analysis.topic_modeling.n_topics == 5
    assert view.effective.llm.num_predict == 1024
    assert BUILTIN_PRESET_POLICIES["balanced"].llm_module_ids == ("llm_summary",)


def test_resolve_preset_uses_effective_config(runtime: RuntimePaths) -> None:
    reload_config(runtime=runtime)
    snap = snapshot_for_operation(runtime=runtime)
    with bind_operation_config(snap):
        quick = resolve_analysis_preset("quick", effective=snap)
        balanced = resolve_analysis_preset("balanced", effective=snap)
    assert "llm_summary" not in quick.module_ids
    assert "llm_summary" in balanced.module_ids


def test_precedence_workspace_over_defaults(runtime: RuntimePaths) -> None:
    save_workspace_settings(
        config={"analysis": {"keyphrases": {"top_n": 7}}, "llm": {}, "ocr": {}},
        activations=ProfileActivations(),
        runtime=runtime,
    )
    resolved = resolve_effective_config(
        workspace_config={"analysis": {"keyphrases": {"top_n": 7}}, "llm": {}, "ocr": {}},
        activations=ProfileActivations(),
        runtime=runtime,
    )
    assert resolved.effective.analysis.keyphrases.top_n == 7
    assert resolved.provenance["analysis.keyphrases.top_n"] == "workspace"


def test_precedence_env_over_workspace(runtime: RuntimePaths, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TRANSCRIBE_OLLAMA_BASE_URL", "http://127.0.0.1:11434")
    resolved = resolve_effective_config(
        workspace_config={
            "analysis": {},
            "llm": {},
            "ocr": {"base_url": "http://workspace:11434"},
        },
        activations=ProfileActivations(),
        runtime=runtime,
        environ={"TRANSCRIBE_OLLAMA_BASE_URL": "http://127.0.0.1:11434"},
    )
    assert resolved.effective.ocr.base_url == "http://127.0.0.1:11434"
    assert resolved.provenance["ocr.base_url"] == "env:TRANSCRIBE_OLLAMA_BASE_URL"


def test_precedence_project_beats_env(runtime: RuntimePaths) -> None:
    resolved = resolve_effective_config(
        workspace_config={"analysis": {}, "llm": {}, "ocr": {}},
        activations=ProfileActivations(),
        project_settings=OCRSettings(base_url="http://project:11434"),
        runtime=runtime,
        environ={"TRANSCRIBE_OLLAMA_BASE_URL": "http://host.docker.internal:11434"},
    )
    assert resolved.effective.ocr.base_url == "http://project:11434"
    assert resolved.provenance["ocr.base_url"] == "project"


def test_project_override_ocr_only(runtime: RuntimePaths) -> None:
    project = OCRSettings(base_url="http://project:11434", max_workers=2)
    resolved = resolve_effective_config(
        workspace_config={
            "analysis": {"keyphrases": {"top_n": 9}},
            "llm": {},
            "ocr": {"base_url": "http://workspace:11434", "max_workers": 1},
        },
        activations=ProfileActivations(),
        project_settings=project,
        runtime=runtime,
        environ={},
    )
    assert resolved.effective.ocr.base_url == "http://project:11434"
    assert resolved.effective.ocr.max_workers == 2
    assert resolved.effective.analysis.keyphrases.top_n == 9


def test_corrupt_settings_preserved(runtime: RuntimePaths) -> None:
    path = settings_path(runtime)
    path.write_text("{not json", encoding="utf-8")
    with pytest.raises(ConfigError) as exc:
        load_workspace_settings(runtime=runtime, recovery="raise")
    assert exc.value.code == SETTINGS_CORRUPT
    assert path.read_text(encoding="utf-8") == "{not json"
    loaded = load_workspace_settings(runtime=runtime, recovery="defaults_readonly")
    assert loaded.readonly_recovery is True
    assert path.read_text(encoding="utf-8") == "{not json"


def test_unsupported_schema_refused(runtime: RuntimePaths) -> None:
    path = settings_path(runtime)
    path.write_text(
        json.dumps(
            {
                "format": "transcribe.settings",
                "schema_version": CURRENT_SETTINGS_SCHEMA_VERSION + 99,
                "config": {},
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(ConfigError) as exc:
        load_workspace_settings(runtime=runtime, recovery="raise")
    assert exc.value.code == SETTINGS_SCHEMA_UNSUPPORTED


def test_save_as_rejects_reserved_names(runtime: RuntimePaths) -> None:
    for name in sorted(RESERVED_PROFILE_NAMES):
        with pytest.raises(ConfigError) as exc:
            validate_profile_name(name, for_save_as=True)
        assert exc.value.code == PROFILE_RESERVED_NAME


def test_profile_activation_overlay(runtime: RuntimePaths) -> None:
    overlay = builtin_profile_config("llm", "short")
    assert overlay is not None
    assert overlay["llm"]["num_predict"] == 512
    resolved = resolve_effective_config(
        workspace_config={"analysis": {}, "llm": {}, "ocr": {}},
        activations=ProfileActivations(llm="short"),
        runtime=runtime,
        environ={},
    )
    assert resolved.effective.llm.num_predict == 512
    assert "profile:llm/short" in resolved.provenance["llm.num_predict"]


def test_operation_snapshot_immutable_for_modules(runtime: RuntimePaths) -> None:
    reload_config(runtime=runtime)
    snap = snapshot_for_operation(runtime=runtime)
    with bind_operation_config(snap):
        assert require_operation_config() is snap
        knobs = module_knob_dict(snap, "keyphrases")
        assert knobs["top_n"] == 25
        assert knobs["analysis_config_version"] == ANALYSIS_CONFIG_VERSION
        fp1 = config_fingerprint(knobs)
        fp2 = config_fingerprint(dict(reversed(list(knobs.items()))))
        assert fp1 == fp2


def test_threshold_change_changes_fingerprint(runtime: RuntimePaths) -> None:
    from transcribe.config.models import AnalysisConfig, KeyphrasesConfig

    cfg_a = EffectiveConfig()
    cfg_b = EffectiveConfig(
        analysis=AnalysisConfig(keyphrases=KeyphrasesConfig(top_n=3))
    )
    fp_a = config_fingerprint(module_knob_dict(cfg_a, "keyphrases"))
    fp_b = config_fingerprint(module_knob_dict(cfg_b, "keyphrases"))
    assert fp_a != fp_b


def test_user_profile_save_and_path_safety(runtime: RuntimePaths) -> None:
    path = save_user_profile(
        "workflow",
        "my_house",
        {"analysis": {"ui_presets": EffectiveConfig().analysis.ui_presets.as_dict()}},
        runtime=runtime,
    )
    assert path.name == "my_house.json"
    assert "workflow" in str(path)
    with pytest.raises(ConfigError):
        validate_profile_name("../evil", for_save_as=True)
