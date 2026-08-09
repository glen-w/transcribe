"""Canonical analysis config subsets for fingerprints and module knobs."""

from __future__ import annotations

from typing import Any

from transcribe.config.models import EffectiveConfig
from transcribe.config.versions import ANALYSIS_CONFIG_VERSION, PRESET_POLICY_VERSION


def analysis_fingerprint_base(cfg: EffectiveConfig) -> dict[str, Any]:
    return {
        "analysis_config_version": ANALYSIS_CONFIG_VERSION,
        "preset_policy_version": PRESET_POLICY_VERSION,
    }


def module_knob_dict(cfg: EffectiveConfig, module_id: str) -> dict[str, Any]:
    """Effective resolved knobs included in a module's config_fingerprint."""
    base = analysis_fingerprint_base(cfg)
    a = cfg.analysis
    if module_id == "keyphrases":
        return {**base, **a.keyphrases.as_dict()}
    if module_id == "highlights":
        return {**base, **a.highlights.as_dict()}
    if module_id == "moments":
        return {**base, **a.moments.as_dict()}
    if module_id == "semantic_similarity":
        return {**base, **a.semantic_similarity.as_dict()}
    if module_id == "topic_shift":
        return {**base, **a.topic_shift.as_dict()}
    if module_id == "wordclouds":
        return {**base, **a.wordclouds.as_dict()}
    if module_id == "topic_modeling":
        return {**base, **a.topic_modeling.as_dict()}
    if module_id in {
        "llm_summary",
        "llm_action_items",
        "llm_custom_qa",
        "narrative_summary",
    }:
        return {
            **base,
            "default_temperature": cfg.llm.default_temperature,
            "num_predict": cfg.llm.num_predict,
            "max_unit_tokens": cfg.llm.max_unit_tokens,
            "max_prompt_tokens": cfg.llm.max_prompt_tokens,
        }
    return base


def ui_presets_fingerprint(cfg: EffectiveConfig) -> dict[str, Any]:
    return {
        **analysis_fingerprint_base(cfg),
        "ui_presets": cfg.analysis.ui_presets.as_dict(),
    }


def llm_generation_options(cfg: EffectiveConfig) -> dict[str, Any]:
    return {
        "temperature": cfg.llm.default_temperature,
        "num_predict": cfg.llm.num_predict,
    }
