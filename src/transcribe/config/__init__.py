"""Workspace settings, profiles, and EffectiveConfig facade."""

from __future__ import annotations

from transcribe.config.apply_ocr import (
    APPLY_OCR_FIELD_ALLOWLIST,
    ApplyOcrPlan,
    apply_ocr_patch,
    preview_apply_ocr,
)
from transcribe.config.errors import ConfigError
from transcribe.config.facade import (
    ConfigView,
    bind_operation_config,
    clear_config_cache,
    get_config,
    reload_config,
    require_operation_config,
    snapshot_for_operation,
)
from transcribe.config.knobs import (
    llm_generation_options,
    module_knob_dict,
    ui_presets_fingerprint,
)
from transcribe.config.models import EffectiveConfig, ProfileActivations
from transcribe.config.persistence import (
    load_workspace_settings,
    save_workspace_settings,
    settings_path,
)
from transcribe.config.versions import (
    ANALYSIS_CONFIG_VERSION,
    PRESET_POLICY_VERSION,
)

__all__ = [
    "ANALYSIS_CONFIG_VERSION",
    "APPLY_OCR_FIELD_ALLOWLIST",
    "ApplyOcrPlan",
    "ConfigError",
    "ConfigView",
    "EffectiveConfig",
    "PRESET_POLICY_VERSION",
    "ProfileActivations",
    "apply_ocr_patch",
    "bind_operation_config",
    "clear_config_cache",
    "get_config",
    "llm_generation_options",
    "load_workspace_settings",
    "module_knob_dict",
    "preview_apply_ocr",
    "reload_config",
    "require_operation_config",
    "save_workspace_settings",
    "settings_path",
    "snapshot_for_operation",
    "ui_presets_fingerprint",
]
