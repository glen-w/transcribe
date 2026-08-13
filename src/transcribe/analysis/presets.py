"""Analysis UI presets (Quick / Balanced / Thorough / Custom) — ported from TranscriptX.

Policy defaults mirror TranscriptX ``AnalysisUiPresetsModel``:
- Quick: no LLM, no heavy
- Balanced: ``llm_summary`` only + heavy allowlist ``semantic_similarity``
- Thorough: all suitable (LLM + heavy)
- Custom: caller selection (seeded from Balanced when empty)

Resolved policies come from ``EffectiveConfig.analysis.ui_presets`` (workspace →
profile → defaults). Builtin ``BUILTIN_PRESET_POLICIES`` remain the model defaults.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Any, Literal, Sequence

from transcribe.analysis.module_catalog import (
    format_module_label,
    get_module_info,
    is_heavy_module,
    list_catalog_modules,
)
from transcribe.config.facade import require_operation_config
from transcribe.config.models import EffectiveConfig, PresetPolicyConfig
from transcribe.config.versions import PRESET_POLICY_VERSION
from transcribe.domain.fingerprint import canonical_json_bytes

AnalysisPreset = Literal["quick", "balanced", "thorough", "custom"]
VALID_PRESETS: tuple[AnalysisPreset, ...] = (
    "quick",
    "balanced",
    "thorough",
    "custom",
)

PRESET_LABELS: dict[AnalysisPreset, str] = {
    "quick": "Quick",
    "balanced": "Balanced",
    "thorough": "Thorough",
    "custom": "Custom",
}

PRESET_HELP = (
    "**Quick** — no LLM, no heavy modules.\n\n"
    "**Balanced** — limited heavy modules + LLM summary only.\n\n"
    "**Thorough** — all suitable modules for this notebook.\n\n"
    "**Custom** — pick modules."
)

_CUSTOM_QA_MODULE = "llm_custom_qa"


@dataclass(frozen=True)
class PresetPolicy:
    """One UI analysis preset policy (TX ``PresetPolicyModel`` defaults)."""

    allow_llm: bool = False
    llm_module_ids: tuple[str, ...] = ()
    allow_heavy: bool = False
    heavy_module_ids: tuple[str, ...] = ()
    include_excluded_from_default: bool = False
    module_ids: tuple[str, ...] | None = None
    content_version: int = 1


def _policy_from_config(cfg: PresetPolicyConfig) -> PresetPolicy:
    return PresetPolicy(
        allow_llm=cfg.allow_llm,
        llm_module_ids=cfg.llm_module_ids,
        allow_heavy=cfg.allow_heavy,
        heavy_module_ids=cfg.heavy_module_ids,
        include_excluded_from_default=cfg.include_excluded_from_default,
        module_ids=cfg.module_ids,
        content_version=int(cfg.content_version),
    )


def preset_policy_fingerprint(policy: PresetPolicy | PresetPolicyConfig) -> str:
    """SHA-256 of policy body excluding content_version."""
    if isinstance(policy, PresetPolicyConfig):
        body = policy.policy_body_dict()
    else:
        body = {
            "allow_llm": policy.allow_llm,
            "llm_module_ids": list(policy.llm_module_ids),
            "allow_heavy": policy.allow_heavy,
            "heavy_module_ids": list(policy.heavy_module_ids),
            "include_excluded_from_default": policy.include_excluded_from_default,
            "module_ids": (None if policy.module_ids is None else list(policy.module_ids)),
        }
    return hashlib.sha256(canonical_json_bytes(body)).hexdigest()


def custom_modules_fingerprint(module_ids: Sequence[str]) -> str:
    """Stable identity surrogate for Custom preset selections."""
    return hashlib.sha256(canonical_json_bytes({"module_ids": list(module_ids)})).hexdigest()


def bump_preset_content_versions(
    previous: dict[str, Any],
    next_draft: dict[str, Any],
) -> dict[str, Any]:
    """Return saved preset dicts with content_version bumped when policy body changes."""
    out: dict[str, Any] = {}
    for key in ("quick", "balanced", "thorough"):
        prev_cfg = PresetPolicyConfig.from_dict(previous.get(key))
        next_cfg = PresetPolicyConfig.from_dict(next_draft.get(key))
        version = int(prev_cfg.content_version)
        if prev_cfg.policy_body_dict() != next_cfg.policy_body_dict():
            version = version + 1
        out[key] = {**next_cfg.policy_body_dict(), "content_version": version}
    return out


# Builtin policies — same defaults as TranscriptX ``ui_presets.py`` / model defaults.
BUILTIN_PRESET_POLICIES: dict[str, PresetPolicy] = {
    "quick": _policy_from_config(EffectiveConfig().analysis.ui_presets.quick),
    "balanced": _policy_from_config(EffectiveConfig().analysis.ui_presets.balanced),
    "thorough": _policy_from_config(EffectiveConfig().analysis.ui_presets.thorough),
}


def policies_from_effective(cfg: EffectiveConfig) -> dict[str, PresetPolicy]:
    presets = cfg.analysis.ui_presets
    return {
        "quick": _policy_from_config(presets.quick),
        "balanced": _policy_from_config(presets.balanced),
        "thorough": _policy_from_config(presets.thorough),
    }


@dataclass(frozen=True)
class ResolvedAnalysisPreset:
    preset: AnalysisPreset
    module_ids: tuple[str, ...]
    content_version: int = 1
    policy_fingerprint: str = ""


@dataclass(frozen=True)
class EffectiveModulePlan:
    module_ids: tuple[str, ...]
    llm_count: int
    heavy_count: int
    custom_qa_execution: bool


def _dedupe_preserve_order(modules: Sequence[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for mid in modules:
        if mid not in seen:
            seen.add(mid)
            out.append(mid)
    return out


def suitable_module_ids(
    *,
    include_heavy: bool = True,
    include_excluded_from_default: bool = True,
) -> tuple[str, ...]:
    """Registered core modules that may appear in a preset."""
    out: list[str] = []
    for info in list_catalog_modules():
        if not include_excluded_from_default and info.exclude_from_default:
            continue
        if not include_heavy and is_heavy_module(info):
            continue
        out.append(info.module_id)
    return tuple(out)


def reconcile_custom_modules(
    selected: Sequence[str],
    *,
    suitable: Sequence[str],
) -> tuple[tuple[str, ...], tuple[str, ...]]:
    suitable_set = set(suitable)
    kept: list[str] = []
    removed: list[str] = []
    seen: set[str] = set()
    for mid in selected:
        if mid in seen:
            continue
        seen.add(mid)
        if mid in suitable_set:
            kept.append(mid)
        else:
            removed.append(mid)
    return tuple(kept), tuple(removed)


def _module_passes_policy(mid: str, policy: PresetPolicy) -> bool:
    info = get_module_info(mid)
    if info is None:
        return False
    if info.exclude_from_default and not policy.include_excluded_from_default:
        return False
    if info.requires_llm:
        if not policy.allow_llm:
            return False
        if policy.llm_module_ids and mid not in policy.llm_module_ids:
            return False
    if is_heavy_module(info):
        if not policy.allow_heavy:
            return False
        if policy.heavy_module_ids and mid not in policy.heavy_module_ids:
            return False
    return True


def _required_dependencies(mid: str) -> tuple[str, ...]:
    info = get_module_info(mid)
    if info is None:
        return ()
    return info.dependencies


def prune_modules_with_unsatisfied_deps(
    module_ids: Sequence[str],
) -> tuple[str, ...]:
    """Drop modules whose hard parents are not also selected (TX behaviour)."""
    selected = _dedupe_preserve_order(module_ids)
    changed = True
    while changed:
        changed = False
        selected_set = set(selected)
        kept: list[str] = []
        for mid in selected:
            deps = _required_dependencies(mid)
            if any(dep not in selected_set for dep in deps):
                changed = True
                continue
            kept.append(mid)
        selected = kept
    return tuple(selected)


def expand_with_hard_parents(module_ids: Sequence[str]) -> tuple[str, ...]:
    """Add missing hard parents transitively so a Custom run can succeed."""
    selected = _dedupe_preserve_order(module_ids)
    selected_set = set(selected)
    changed = True
    while changed:
        changed = False
        for mid in list(selected):
            for dep in _required_dependencies(mid):
                if dep not in selected_set and get_module_info(dep) is not None:
                    selected.append(dep)
                    selected_set.add(dep)
                    changed = True
    return tuple(_dedupe_preserve_order(selected))


def _modules_from_policy(
    suitable: Sequence[str],
    policy: PresetPolicy,
) -> tuple[str, ...]:
    if policy.module_ids is not None:
        kept, _ = reconcile_custom_modules(policy.module_ids, suitable=suitable)
        return prune_modules_with_unsatisfied_deps(kept)
    selected = tuple(mid for mid in suitable if _module_passes_policy(mid, policy))
    return prune_modules_with_unsatisfied_deps(selected)


def resolve_analysis_preset(
    preset: AnalysisPreset | str,
    *,
    custom_modules: Sequence[str] | None = None,
    effective: EffectiveConfig | None = None,
) -> ResolvedAnalysisPreset:
    """Resolve Quick / Balanced / Thorough / Custom into ordered module ids."""
    if preset not in VALID_PRESETS:
        preset = "balanced"
    preset_key: AnalysisPreset = preset  # type: ignore[assignment]

    suitable = suitable_module_ids(
        include_heavy=True,
        include_excluded_from_default=True,
    )

    cfg = effective if effective is not None else require_operation_config()
    policies = policies_from_effective(cfg)

    if preset_key == "custom":
        kept, _ = reconcile_custom_modules(list(custom_modules or ()), suitable=suitable)
        if not kept:
            balanced = resolve_analysis_preset("balanced", effective=cfg)
            kept = balanced.module_ids
        fp = custom_modules_fingerprint(kept)
        return ResolvedAnalysisPreset(
            preset="custom",
            module_ids=kept,
            content_version=0,
            policy_fingerprint=fp,
        )

    policy = policies[preset_key]
    modules = _modules_from_policy(suitable, policy)
    cfg_policy = getattr(cfg.analysis.ui_presets, preset_key)
    return ResolvedAnalysisPreset(
        preset=preset_key,
        module_ids=modules,
        content_version=int(cfg_policy.content_version),
        policy_fingerprint=preset_policy_fingerprint(cfg_policy),
    )


def _count_llm_and_heavy(module_ids: Sequence[str]) -> tuple[int, int]:
    llm = 0
    heavy = 0
    for mid in module_ids:
        info = get_module_info(mid)
        if info is None:
            continue
        if info.requires_llm:
            llm += 1
        if is_heavy_module(info):
            heavy += 1
    return llm, heavy


def compute_effective_modules(
    resolved: ResolvedAnalysisPreset,
    *,
    custom_qa_execution: bool,
) -> EffectiveModulePlan:
    modules = list(resolved.module_ids)
    if custom_qa_execution:
        if _CUSTOM_QA_MODULE not in modules:
            modules.append(_CUSTOM_QA_MODULE)
    else:
        modules = [m for m in modules if m != _CUSTOM_QA_MODULE]
    deduped = tuple(_dedupe_preserve_order(modules))
    llm_count, heavy_count = _count_llm_and_heavy(deduped)
    return EffectiveModulePlan(
        module_ids=deduped,
        llm_count=llm_count,
        heavy_count=heavy_count,
        custom_qa_execution=bool(custom_qa_execution),
    )


def label_to_preset(label: str) -> AnalysisPreset:
    for key, text in PRESET_LABELS.items():
        if text == label:
            return key
    return "balanced"


def format_preset_label(preset: AnalysisPreset | str) -> str:
    if preset in PRESET_LABELS:
        return PRESET_LABELS[preset]  # type: ignore[index]
    return str(preset).title()


# Re-export for UI convenience
__all__ = [
    "AnalysisPreset",
    "BUILTIN_PRESET_POLICIES",
    "EffectiveModulePlan",
    "PRESET_HELP",
    "PRESET_LABELS",
    "PRESET_POLICY_VERSION",
    "PresetPolicy",
    "ResolvedAnalysisPreset",
    "VALID_PRESETS",
    "bump_preset_content_versions",
    "compute_effective_modules",
    "custom_modules_fingerprint",
    "expand_with_hard_parents",
    "format_module_label",
    "format_preset_label",
    "label_to_preset",
    "policies_from_effective",
    "preset_policy_fingerprint",
    "prune_modules_with_unsatisfied_deps",
    "reconcile_custom_modules",
    "resolve_analysis_preset",
    "suitable_module_ids",
]
