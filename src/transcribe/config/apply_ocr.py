"""Apply workspace OCR defaults to an open project (allowlisted patch)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from transcribe.config.errors import APPLY_OCR_INVALID, ConfigError
from transcribe.config.models import OcrWorkspaceConfig
from transcribe.config.resolve import PROJECT_OCR_OVERRIDE_KEYS
from transcribe.domain.models import CLEANUP_MODES, OCRSettings

# Fields Apply-to-project may copy from workspace OCR into project settings.
APPLY_OCR_FIELD_ALLOWLIST: frozenset[str] = frozenset(
    {
        "base_url",
        "prompt_id",
        "language",
        "preprocess_profile",
        "max_workers",
        "cleanup_enabled",
        "cleanup_mode",
        "cleanup_model_name",
        "text_model_name",
        "prefer_mode",
        "auto_activate_composite",
    }
)


@dataclass(frozen=True)
class ApplyOcrPlan:
    fields: dict[str, Any]
    before: dict[str, Any]
    after: dict[str, Any]

    @property
    def changed(self) -> dict[str, tuple[Any, Any]]:
        out: dict[str, tuple[Any, Any]] = {}
        for key, new in self.fields.items():
            old = self.before.get(key)
            if old != new:
                out[key] = (old, new)
        return out


def preview_apply_ocr(
    project: OCRSettings,
    workspace_ocr: OcrWorkspaceConfig,
    *,
    fields: set[str] | frozenset[str] | None = None,
) -> ApplyOcrPlan:
    want = set(fields) if fields is not None else set(APPLY_OCR_FIELD_ALLOWLIST)
    unknown = want - APPLY_OCR_FIELD_ALLOWLIST
    if unknown:
        raise ConfigError(
            APPLY_OCR_INVALID,
            f"fields not in Apply allowlist: {sorted(unknown)}",
        )
    ws = workspace_ocr.as_dict()
    before = project.as_dict()
    patch: dict[str, Any] = {}
    for key in sorted(want):
        if key not in ws:
            continue
        value = ws[key]
        if key == "base_url" and not str(value or "").strip():
            continue
        if key == "cleanup_mode" and value not in CLEANUP_MODES:
            raise ConfigError(APPLY_OCR_INVALID, f"invalid cleanup_mode: {value!r}")
        if key == "prefer_mode":
            from transcribe.domain.models import PREFER_MODES

            if value not in PREFER_MODES:
                raise ConfigError(APPLY_OCR_INVALID, f"invalid prefer_mode: {value!r}")
        if key == "max_workers" and int(value) not in (1, 2):
            raise ConfigError(APPLY_OCR_INVALID, "max_workers must be 1 or 2")
        patch[key] = value
    after = dict(before)
    after.update(patch)
    return ApplyOcrPlan(fields=patch, before=before, after=after)


def apply_ocr_patch(project: OCRSettings, plan: ApplyOcrPlan) -> OCRSettings:
    """Return a new OCRSettings with allowlisted fields patched (no wholesale replace)."""
    data = project.as_dict()
    for key, value in plan.fields.items():
        if key not in APPLY_OCR_FIELD_ALLOWLIST:
            raise ConfigError(APPLY_OCR_INVALID, f"refusing non-allowlisted field {key}")
        if key not in PROJECT_OCR_OVERRIDE_KEYS and key != "text_model_name":
            # text_model_name is in both
            pass
        data[key] = value
    return OCRSettings.from_dict(data)
