"""Config / settings error codes (stable strings for UI and tests)."""

from __future__ import annotations

from transcribe.errors import TranscribeError


class ConfigError(TranscribeError):
    """Workspace settings / profile / resolve failure."""

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        super().__init__(message)


# Stable codes
SETTINGS_CORRUPT = "settings_corrupt"
SETTINGS_SCHEMA_UNSUPPORTED = "settings_schema_unsupported"
SETTINGS_SAVE_VERIFY_FAILED = "settings_save_verify_failed"
SETTINGS_LOCK_TIMEOUT = "settings_lock_timeout"
PROFILE_CORRUPT = "profile_corrupt"
PROFILE_SCHEMA_UNSUPPORTED = "profile_schema_unsupported"
PROFILE_NAME_INVALID = "profile_name_invalid"
PROFILE_TARGET_INVALID = "profile_target_invalid"
PROFILE_RESERVED_NAME = "profile_reserved_name"
PROFILE_NOT_FOUND = "profile_not_found"
ENV_INVALID = "env_invalid"
APPLY_OCR_INVALID = "apply_ocr_invalid"
