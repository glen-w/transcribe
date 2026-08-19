"""Workspace config: defaults parity, precedence, persistence, profiles."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from transcribe.analysis.cache_identity import config_fingerprint
from transcribe.analysis.presets import BUILTIN_PRESET_POLICIES, resolve_analysis_preset
from transcribe.config.defaults import RESERVED_PROFILE_NAMES, builtin_profile_config
from transcribe.config.errors import (
    PROFILE_CORRUPT,
    PROFILE_NOT_FOUND,
    PROFILE_RESERVED_NAME,
    PROFILE_SCHEMA_UNSUPPORTED,
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
from transcribe.config.models import (
    EffectiveConfig,
    IngestConfig,
    PresetPolicyConfig,
    ProfileActivations,
    UiConfig,
)
from transcribe.config.persistence import (
    load_workspace_settings,
    save_workspace_settings,
    settings_path,
)
from transcribe.config.profiles import (
    load_profile_overlay,
    list_user_profile_names,
    save_user_profile,
    validate_profile_name,
)
from transcribe.config.resolve import resolve_effective_config
from transcribe.config.versions import (
    ANALYSIS_CONFIG_VERSION,
    CURRENT_PROFILE_SCHEMA_VERSION,
    CURRENT_SETTINGS_SCHEMA_VERSION,
    PROFILE_FORMAT,
)
from transcribe.domain.models import OCRSettings
from transcribe.persistence.atomic import write_json_atomic
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
    assert policies.quick.allow_detection is False
    assert policies.balanced.allow_detection is False
    assert policies.thorough.allow_detection is True
    assert view.effective.analysis.keyphrases.top_n == 25
    assert view.effective.analysis.highlights.top_n == 12
    assert view.effective.analysis.moments.top_n == 10
    assert view.effective.analysis.semantic_similarity.motif_threshold == 0.55
    assert view.effective.analysis.topic_shift.shift_threshold == 0.25
    assert view.effective.analysis.wordclouds.max_tokens == 100
    assert view.effective.analysis.topic_modeling.n_topics == 5
    assert view.effective.llm.num_predict == 1024
    assert view.effective.ingest.render_dpi == 200
    assert BUILTIN_PRESET_POLICIES["balanced"].llm_module_ids == ("llm_summary",)


def test_preset_policy_from_dict_accepts_legacy_body_without_detection() -> None:
    legacy = PresetPolicyConfig.from_dict(
        {
            "allow_llm": True,
            "llm_module_ids": ["llm_summary"],
            "allow_heavy": True,
            "heavy_module_ids": ["semantic_similarity"],
            "include_excluded_from_default": False,
            "content_version": 3,
        }
    )
    assert legacy.allow_detection is False
    assert legacy.detector_ids == ()
    assert "allow_detection" in legacy.as_dict()
    assert "detector_ids" in legacy.as_dict()


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
        workspace_config={
            "analysis": {"keyphrases": {"top_n": 7}},
            "llm": {},
            "ocr": {},
        },
        activations=ProfileActivations(),
        runtime=runtime,
    )
    assert resolved.effective.analysis.keyphrases.top_n == 7
    assert resolved.provenance["analysis.keyphrases.top_n"] == "workspace"


def test_ingest_render_dpi_workspace_override(runtime: RuntimePaths) -> None:
    save_workspace_settings(
        config={"analysis": {}, "llm": {}, "ocr": {}, "ingest": {"render_dpi": 150}},
        activations=ProfileActivations(),
        runtime=runtime,
    )
    view = reload_config(runtime=runtime)
    assert view.effective.ingest.render_dpi == 150
    assert view.provenance["ingest.render_dpi"] == "workspace"


def test_ingest_config_clamps_render_dpi() -> None:
    assert IngestConfig.from_dict({"render_dpi": 50}).render_dpi == 72
    assert IngestConfig.from_dict({"render_dpi": 900}).render_dpi == 600
    assert IngestConfig.from_dict(None).render_dpi == 200
    assert IngestConfig.from_dict({"render_dpi": 200}).as_dict() == {
        "render_dpi": 200,
        "visual_declutter_enabled": True,
    }


def test_visual_declutter_missing_defaults_true() -> None:
    assert IngestConfig.from_dict({}).visual_declutter_enabled is True
    assert IngestConfig.from_dict({"render_dpi": 150}).visual_declutter_enabled is True
    assert (
        IngestConfig.from_dict({"visual_declutter_enabled": False}).visual_declutter_enabled
        is False
    )


def test_ui_config_archive_notebooks_initial_defaults_all() -> None:
    assert UiConfig.from_dict(None).archive_notebooks_initial == 0
    assert UiConfig.from_dict({}).archive_notebooks_initial == 0
    assert UiConfig.from_dict({"archive_notebooks_initial": -3}).archive_notebooks_initial == 0
    assert UiConfig.from_dict({"archive_notebooks_initial": 12}).archive_notebooks_initial == 12
    assert UiConfig.from_dict({"archive_notebooks_initial": "bad"}).archive_notebooks_initial == 0


def test_archive_notebooks_initial_workspace_round_trip(runtime: RuntimePaths) -> None:
    save_workspace_settings(
        config={
            "analysis": {},
            "llm": {},
            "ocr": {},
            "ingest": {},
            "ui": {"archive_notebooks_initial": 18},
        },
        activations=ProfileActivations(),
        runtime=runtime,
    )
    clear_config_cache()
    view = get_config(runtime=runtime)
    assert view.effective.ui.archive_notebooks_initial == 18
    assert view.provenance["ui.archive_notebooks_initial"] == "workspace"


def test_overview_cards_sanitise_default_and_round_trip(runtime: RuntimePaths) -> None:
    from transcribe.config.knobs import analysis_fingerprint_base, module_knob_dict
    from transcribe.config.models import (
        OVERVIEW_CARD_IDS,
        EffectiveConfig,
        UiConfig,
        sanitise_overview_cards,
    )

    assert sanitise_overview_cards(None) == OVERVIEW_CARD_IDS
    assert sanitise_overview_cards([]) == OVERVIEW_CARD_IDS
    assert sanitise_overview_cards(["bogus"]) == OVERVIEW_CARD_IDS
    assert sanitise_overview_cards(["ner", "stats", "ner", "nope"]) == ("stats", "ner")
    assert sanitise_overview_cards("wordclouds") == ("wordclouds",)

    save_workspace_settings(
        config={
            "analysis": {},
            "llm": {},
            "ocr": {},
            "ingest": {},
            "ui": {"overview_cards": ["ner", "stats"]},
        },
        activations=ProfileActivations(),
        runtime=runtime,
    )
    clear_config_cache()
    view = get_config(runtime=runtime)
    assert view.effective.ui.overview_cards == ("stats", "ner")
    assert view.provenance["ui.overview_cards"] == "workspace"

    slim = EffectiveConfig(ui=UiConfig(overview_cards=("ner",)))
    full = EffectiveConfig()
    assert config_fingerprint(module_knob_dict(slim, "stats")) == config_fingerprint(
        module_knob_dict(full, "stats")
    )
    base = analysis_fingerprint_base(slim)
    assert "overview_cards" not in base
    assert "view_show_advanced" not in base
    assert "ui" not in base


def test_view_show_advanced_round_trip(runtime: RuntimePaths) -> None:
    from transcribe.config.models import UiConfig

    view = get_config(runtime=runtime)
    assert view.effective.ui.view_show_advanced is False

    save_workspace_settings(
        config={
            "analysis": {},
            "llm": {},
            "ocr": {},
            "ingest": {},
            "ui": {"view_show_advanced": True},
        },
        activations=ProfileActivations(),
        runtime=runtime,
    )
    clear_config_cache()
    view = get_config(runtime=runtime)
    assert view.effective.ui.view_show_advanced is True
    assert view.provenance["ui.view_show_advanced"] == "workspace"

    assert UiConfig.from_dict({}).view_show_advanced is False
    assert UiConfig.from_dict({"view_show_advanced": 1}).view_show_advanced is True
    assert UiConfig.from_dict({"overview_show_advanced": True}).view_show_advanced is True


def test_chart_colors_round_trip(runtime: RuntimePaths) -> None:
    from transcribe.config.models import ChartColorsConfig, UiConfig
    from transcribe.ui.chart_colors import DEFAULT_EMOTION_COLORS, DEFAULT_SENTIMENT_COLORS

    view = get_config(runtime=runtime)
    assert view.effective.ui.chart_colors.resolved()["sentiment"] == DEFAULT_SENTIMENT_COLORS

    save_workspace_settings(
        config={
            "analysis": {},
            "llm": {},
            "ocr": {},
            "ingest": {},
            "ui": {
                "chart_colors": {
                    "sentiment": {"negative": "#aa0000"},
                    "emotion": {"joy": "#00aa00", "anger": "not-a-color"},
                }
            },
        },
        activations=ProfileActivations(),
        runtime=runtime,
    )
    clear_config_cache()
    view = get_config(runtime=runtime)
    resolved = view.effective.ui.chart_colors.resolved()
    assert resolved["sentiment"]["negative"] == "#aa0000"
    assert resolved["sentiment"]["positive"] == DEFAULT_SENTIMENT_COLORS["positive"]
    assert resolved["emotion"]["joy"] == "#00aa00"
    assert resolved["emotion"]["anger"] == DEFAULT_EMOTION_COLORS["anger"]
    assert view.provenance["ui.chart_colors.sentiment.negative"] == "workspace"

    assert UiConfig.from_dict({}).chart_colors == ChartColorsConfig()
    assert ChartColorsConfig.from_dict(None).as_dict() == {}


def test_visual_declutter_workspace_round_trip(runtime: RuntimePaths) -> None:
    save_workspace_settings(
        config={
            "analysis": {},
            "llm": {},
            "ocr": {},
            "ingest": {"render_dpi": 180, "visual_declutter_enabled": False},
        },
        activations=ProfileActivations(),
        runtime=runtime,
    )
    clear_config_cache()
    view = get_config(runtime=runtime)
    assert view.effective.ingest.visual_declutter_enabled is False
    assert view.effective.ingest.render_dpi == 180
    loaded = load_workspace_settings(runtime=runtime)
    assert loaded.config["ingest"]["visual_declutter_enabled"] is False


def test_precedence_env_over_workspace(
    runtime: RuntimePaths, monkeypatch: pytest.MonkeyPatch
) -> None:
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
    cfg_b = EffectiveConfig(analysis=AnalysisConfig(keyphrases=KeyphrasesConfig(top_n=3)))
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


def test_load_profile_overlay_errors(runtime: RuntimePaths) -> None:
    with pytest.raises(ConfigError) as missing:
        load_profile_overlay("workflow", "no_such_profile", runtime=runtime)
    assert missing.value.code == PROFILE_NOT_FOUND

    path = save_user_profile(
        "ocr",
        "custom_ocr",
        {"ocr": {"max_workers": 2}},
        runtime=runtime,
    )
    assert "custom_ocr" in list_user_profile_names("ocr", runtime=runtime)

    write_json_atomic(
        path,
        {
            "format": PROFILE_FORMAT,
            "schema_version": CURRENT_PROFILE_SCHEMA_VERSION + 99,
            "target_id": "ocr",
            "name": "custom_ocr",
            "config": {"ocr": {}},
        },
    )
    with pytest.raises(ConfigError) as unsupported:
        load_profile_overlay("ocr", "custom_ocr", runtime=runtime)
    assert unsupported.value.code == PROFILE_SCHEMA_UNSUPPORTED

    write_json_atomic(path, {"format": "wrong.format", "schema_version": 1})
    with pytest.raises(ConfigError) as corrupt:
        load_profile_overlay("ocr", "custom_ocr", runtime=runtime)
    assert corrupt.value.code == PROFILE_CORRUPT
