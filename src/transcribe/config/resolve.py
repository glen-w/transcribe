"""Per-key precedence: defaults → workspace → profile → project → env."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from transcribe.config.defaults import default_effective_dict
from transcribe.config.env_allowlist import read_env_overlays
from transcribe.config.models import (
    EffectiveConfig,
    ProfileActivations,
    deep_merge_dict,
)
from transcribe.config.profiles import load_profile_overlay
from transcribe.domain.models import OCRSettings
from transcribe.runtime_paths import RuntimePaths

# Closed allowlist of project OCR fields that may override workspace/env.
PROJECT_OCR_OVERRIDE_KEYS: frozenset[str] = frozenset(
    {
        "model_name",
        "text_model_name",
        "base_url",
        "prompt_id",
        "custom_prompt",
        "language",
        "preprocess_profile",
        "max_workers",
        "generation_options",
        "allow_non_loopback",
        "cleanup_enabled",
        "cleanup_mode",
        "cleanup_model_name",
    }
)


@dataclass(frozen=True)
class ResolvedConfig:
    effective: EffectiveConfig
    provenance: dict[str, str]
    workspace_config: dict[str, Any]
    activations: ProfileActivations
    readonly_recovery: bool = False
    recovery_code: str | None = None
    recovery_message: str | None = None


def _flatten_provenance(
    layer: Mapping[str, Any],
    source: str,
    *,
    prefix: str = "",
    into: dict[str, str],
) -> None:
    for key, value in layer.items():
        path = f"{prefix}.{key}" if prefix else key
        if isinstance(value, Mapping) and not isinstance(value, (str, bytes)):
            # Skip writing provenance for intermediate dicts; leaves only
            _flatten_provenance(value, source, prefix=path, into=into)
        else:
            into[path] = source


def _project_ocr_overlay(settings: OCRSettings | None) -> dict[str, Any]:
    if settings is None:
        return {}
    raw = settings.as_dict()
    # Only allowlisted keys; base_url empty means "not set" for override purposes
    out: dict[str, Any] = {}
    for key in PROJECT_OCR_OVERRIDE_KEYS:
        if key not in raw:
            continue
        value = raw[key]
        if key == "base_url" and (not value or not str(value).strip()):
            continue
        out[key] = value
    return {"ocr": out} if out else {}


def resolve_effective_config(
    *,
    workspace_config: Mapping[str, Any],
    activations: ProfileActivations,
    project_settings: OCRSettings | None = None,
    runtime: RuntimePaths | None = None,
    environ: Mapping[str, str] | None = None,
    readonly_recovery: bool = False,
    recovery_code: str | None = None,
    recovery_message: str | None = None,
) -> ResolvedConfig:
    """Merge layers into an immutable EffectiveConfig + provenance map."""
    provenance: dict[str, str] = {}

    # 1) defaults
    merged = default_effective_dict()
    # Strip activation keys from merge body; track separately
    for act_key in (
        "active_workflow_profile",
        "active_ocr_profile",
        "active_llm_profile",
    ):
        merged.pop(act_key, None)
    _flatten_provenance(
        {"analysis": merged["analysis"], "llm": merged["llm"], "ocr": merged["ocr"]},
        "default",
        into=provenance,
    )

    # 2) workspace
    ws = {
        "analysis": dict(workspace_config.get("analysis") or {}),
        "llm": dict(workspace_config.get("llm") or {}),
        "ocr": dict(workspace_config.get("ocr") or {}),
    }
    if any(ws.values()):
        merged = deep_merge_dict(merged, ws)
        _flatten_provenance(ws, "workspace", into=provenance)

    # 3) active profiles (overlay; do not copy into workspace)
    for target, name in (
        ("workflow", activations.workflow),
        ("ocr", activations.ocr),
        ("llm", activations.llm),
    ):
        overlay = load_profile_overlay(target, name, runtime=runtime)
        if overlay:
            merged = deep_merge_dict(merged, overlay)
            _flatten_provenance(
                overlay,
                f"profile:{target}/{name}",
                into=provenance,
            )

    # 4) project OCR allowlist
    proj = _project_ocr_overlay(project_settings)
    if proj:
        merged = deep_merge_dict(merged, proj)
        _flatten_provenance(proj, "project", into=provenance)

    # 5) env allowlist
    env_overlay, env_prov = read_env_overlays(environ=environ)
    if env_overlay:
        merged = deep_merge_dict(merged, env_overlay)
        provenance.update(env_prov)

    effective = EffectiveConfig.from_dict({**merged, **activations.as_dict()})
    # Activations themselves
    provenance["active_workflow_profile"] = "workspace"
    provenance["active_ocr_profile"] = "workspace"
    provenance["active_llm_profile"] = "workspace"

    return ResolvedConfig(
        effective=effective,
        provenance=dict(provenance),
        workspace_config=dict(ws),
        activations=activations,
        readonly_recovery=readonly_recovery,
        recovery_code=recovery_code,
        recovery_message=recovery_message,
    )
