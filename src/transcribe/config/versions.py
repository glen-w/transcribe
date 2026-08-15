"""Config and analysis-fingerprint version constants."""

from __future__ import annotations

# Workspace settings.json / profile file schema versions this build can read.
SUPPORTED_SETTINGS_SCHEMA_VERSIONS: frozenset[int] = frozenset({1})
SUPPORTED_PROFILE_SCHEMA_VERSIONS: frozenset[int] = frozenset({1})
CURRENT_SETTINGS_SCHEMA_VERSION = 1
CURRENT_PROFILE_SCHEMA_VERSION = 1

SETTINGS_FORMAT = "transcribe.settings"
PROFILE_FORMAT = "transcribe.profile"

# Bump when fingerprint-included analysis keys/types/semantics change.
ANALYSIS_CONFIG_VERSION = "1"

# Subset version for ui_presets policy shape (bump when policy body keys change).
PRESET_POLICY_VERSION = "2"
