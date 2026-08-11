"""Builtin profile definitions (immutable / virtual)."""

from __future__ import annotations

from typing import Any

from transcribe.config.models import (
    PROFILE_TARGETS,
    EffectiveConfig,
    LlmConfig,
    OcrWorkspaceConfig,
    ProfileTargetId,
    UiPresetsConfig,
)

# Reserved names across all targets (Save As must reject).
RESERVED_PROFILE_NAMES: frozenset[str] = frozenset(
    {
        "default",
        "quick",
        "thorough",
        "careful",
        "fast",
        "short",
        "compact",
        "readable",
        "large_print",
    }
)


def _workflow_quick_overlay() -> dict[str, Any]:
    """House style: all three preset policies match Quick defaults."""
    quick = UiPresetsConfig().quick.as_dict()
    return {
        "analysis": {
            "ui_presets": {
                "quick": quick,
                "balanced": quick,
                "thorough": quick,
            }
        }
    }


def _workflow_thorough_overlay() -> dict[str, Any]:
    """House style: all three preset policies match Thorough defaults."""
    thorough = UiPresetsConfig().thorough.as_dict()
    return {
        "analysis": {
            "ui_presets": {
                "quick": thorough,
                "balanced": thorough,
                "thorough": thorough,
            }
        }
    }


def builtin_profile_config(target: ProfileTargetId, name: str) -> dict[str, Any] | None:
    """Return overlay dict for a builtin profile, or None if not a builtin."""
    name = name.lower()
    if target == "workflow":
        if name == "default":
            return {}
        if name == "quick":
            return _workflow_quick_overlay()
        if name == "thorough":
            return _workflow_thorough_overlay()
        return None
    if target == "ocr":
        if name == "default":
            return {}
        if name == "careful":
            return {
                "ocr": OcrWorkspaceConfig(
                    preprocess_profile="gentle_contrast",
                    max_workers=1,
                    cleanup_enabled=True,
                    cleanup_mode="strip_leak",
                ).as_dict()
            }
        if name == "fast":
            return {
                "ocr": OcrWorkspaceConfig(
                    preprocess_profile="none",
                    max_workers=2,
                    cleanup_enabled=False,
                ).as_dict()
            }
        return None
    if target == "llm":
        if name == "default":
            return {}
        if name == "short":
            return {
                "llm": LlmConfig(
                    default_temperature=0.0,
                    num_predict=512,
                    max_unit_tokens=800,
                    max_prompt_tokens=3000,
                ).as_dict()
            }
        return None
    if target == "export":
        from transcribe.services.export_options import ExportConfig, ExportTypography

        if name == "default":
            return {}
        if name == "readable":
            return {"export": ExportConfig().as_dict()}
        if name == "compact":
            return {
                "export": ExportConfig(
                    page_breaks="continuous",
                    typography=ExportTypography(
                        body_font="sans",
                        body_size_pt=10.0,
                        line_height=1.25,
                        paragraph_spacing_em=0.35,
                        margin_in=0.5,
                        heading_scale=1.15,
                    ),
                ).as_dict()
            }
        if name == "large_print":
            return {
                "export": ExportConfig(
                    page_breaks="per_page",
                    typography=ExportTypography(
                        body_font="serif",
                        body_size_pt=14.0,
                        line_height=1.6,
                        paragraph_spacing_em=0.8,
                        margin_in=1.0,
                        heading_scale=1.35,
                    ),
                ).as_dict()
            }
        return None
    return None


def builtin_names_for(target: ProfileTargetId) -> tuple[str, ...]:
    if target == "workflow":
        return ("default", "quick", "thorough")
    if target == "ocr":
        return ("default", "careful", "fast")
    if target == "llm":
        return ("default", "short")
    if target == "export":
        return ("default", "readable", "compact", "large_print")
    return ("default",)


def is_builtin_profile(target: ProfileTargetId, name: str) -> bool:
    return name.lower() in builtin_names_for(target)


def default_effective_dict() -> dict[str, Any]:
    return EffectiveConfig().as_dict()


def validate_target_id(raw: str) -> ProfileTargetId:
    from transcribe.config.errors import PROFILE_TARGET_INVALID, ConfigError

    if raw not in PROFILE_TARGETS:
        raise ConfigError(
            PROFILE_TARGET_INVALID,
            f"unknown profile target: {raw!r}",
        )
    return raw  # type: ignore[return-value]
