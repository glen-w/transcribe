"""Tests for TranscriptX-ported analysis UI presets."""

from __future__ import annotations

from transcribe.analysis.presets import (
    BUILTIN_PRESET_POLICIES,
    compute_effective_modules,
    expand_with_hard_parents,
    prune_modules_with_unsatisfied_deps,
    resolve_analysis_preset,
)


def test_builtin_policies_match_transcriptx_defaults():
    quick = BUILTIN_PRESET_POLICIES["quick"]
    assert quick.allow_llm is False
    assert quick.allow_heavy is False
    assert quick.allow_detection is False

    balanced = BUILTIN_PRESET_POLICIES["balanced"]
    assert balanced.allow_llm is True
    assert balanced.llm_module_ids == ("llm_summary",)
    assert balanced.heavy_module_ids == ("semantic_similarity",)
    assert balanced.allow_detection is False

    thorough = BUILTIN_PRESET_POLICIES["thorough"]
    assert thorough.allow_llm is True
    assert thorough.allow_heavy is True
    assert thorough.include_excluded_from_default is True
    assert thorough.llm_module_ids == ()
    assert thorough.heavy_module_ids == ()
    assert thorough.allow_detection is True


def test_quick_excludes_llm_and_heavy():
    resolved = resolve_analysis_preset("quick")
    assert "llm_summary" not in resolved.module_ids
    assert "semantic_similarity" not in resolved.module_ids
    assert "topic_modeling" not in resolved.module_ids
    assert "stats" in resolved.module_ids
    assert "sentiment" in resolved.module_ids


def test_balanced_allows_llm_summary_and_semantic_similarity_only_among_heavies():
    resolved = resolve_analysis_preset("balanced")
    assert "llm_summary" in resolved.module_ids
    assert "llm_action_items" not in resolved.module_ids
    assert "semantic_similarity" in resolved.module_ids
    assert "topic_modeling" not in resolved.module_ids
    assert "bertopic" not in resolved.module_ids
    # insights requires topic_modeling → pruned
    assert "insights" not in resolved.module_ids


def test_thorough_includes_heavies_and_llm_suite():
    resolved = resolve_analysis_preset("thorough")
    assert "topic_modeling" in resolved.module_ids
    assert "semantic_similarity" in resolved.module_ids
    assert "llm_summary" in resolved.module_ids
    assert "llm_action_items" in resolved.module_ids
    assert "narrative_summary" in resolved.module_ids
    assert "insights" in resolved.module_ids
    assert resolved.detector_ids
    assert "poetry" in resolved.detector_ids


def test_custom_seeds_from_balanced_when_empty():
    resolved = resolve_analysis_preset("custom", custom_modules=[])
    balanced = resolve_analysis_preset("balanced")
    assert resolved.module_ids == balanced.module_ids


def test_custom_qa_fold_in():
    resolved = resolve_analysis_preset("quick")
    plan = compute_effective_modules(resolved, custom_qa_execution=True)
    assert "llm_custom_qa" in plan.module_ids
    assert plan.custom_qa_execution is True
    stripped = compute_effective_modules(resolved, custom_qa_execution=False)
    assert "llm_custom_qa" not in stripped.module_ids


def test_expand_hard_parents_for_insights():
    expanded = expand_with_hard_parents(["insights"])
    assert "insights" in expanded
    assert "highlights" in expanded
    assert "topic_modeling" in expanded


def test_prune_unsatisfied_deps():
    pruned = prune_modules_with_unsatisfied_deps(["insights", "highlights"])
    assert "insights" not in pruned
    assert "highlights" in pruned
