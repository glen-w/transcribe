"""UI/catalog metadata for core analysis modules (ported from TranscriptX)."""

from __future__ import annotations

from dataclasses import dataclass

from transcribe.analysis.parents import HARD_PARENTS


@dataclass(frozen=True)
class ModuleInfo:
    """Catalogue row for preset policy + Run Analysis UI."""

    module_id: str
    label: str
    category: str = "medium"  # light | medium | heavy
    cost_tier: str = "normal"  # cheap | normal | heavy
    requires_llm: bool = False
    exclude_from_default: bool = False
    dependencies: tuple[str, ...] = ()


# Display labels adapted from TranscriptX ``build_module_label`` for core module ids.
_CATALOG: dict[str, ModuleInfo] = {
    "stats": ModuleInfo("stats", "Statistical Analysis", category="light"),
    "lexical_diversity": ModuleInfo(
        "lexical_diversity",
        "Lexical diversity",
        category="light",
    ),
    "understandability": ModuleInfo(
        "understandability",
        "Understandability",
        category="medium",
    ),
    "wordclouds": ModuleInfo("wordclouds", "Word clouds", category="light"),
    "ner": ModuleInfo("ner", "Named entity recognition", category="medium"),
    "sentiment": ModuleInfo("sentiment", "Sentiment", category="medium"),
    "epistemic_markers": ModuleInfo(
        "epistemic_markers",
        "Hedging / certainty markers",
        category="light",
    ),
    "keyphrases": ModuleInfo("keyphrases", "Keyphrases", category="medium"),
    "entity_sentiment": ModuleInfo(
        "entity_sentiment",
        "Entity sentiment",
        category="heavy",
    ),
    "topic_modeling": ModuleInfo(
        "topic_modeling",
        "Topic modeling",
        category="heavy",
    ),
    "bertopic": ModuleInfo("bertopic", "BERTopic", category="heavy"),
    "semantic_similarity": ModuleInfo(
        "semantic_similarity",
        "Semantic similarity",
        category="heavy",
    ),
    "topic_shift": ModuleInfo("topic_shift", "Topic shifts", category="medium"),
    "emotion": ModuleInfo("emotion", "Emotion vocabulary", category="medium"),
    "contextual_emotion": ModuleInfo(
        "contextual_emotion",
        "Contextual emotion",
        category="heavy",
    ),
    "fine_grained_emotion": ModuleInfo(
        "fine_grained_emotion",
        "Fine-grained emotion",
        category="heavy",
    ),
    "affect_tension": ModuleInfo(
        "affect_tension",
        "Affect tension",
        category="medium",
    ),
    "moments": ModuleInfo("moments", "Moments worth revisiting", category="light"),
    "highlights": ModuleInfo("highlights", "Highlights", category="light"),
    "summary": ModuleInfo("summary", "Executive summary", category="light"),
    "insights": ModuleInfo("insights", "Insights", category="light"),
    "llm_summary": ModuleInfo(
        "llm_summary",
        "LLM summary",
        category="medium",
        requires_llm=True,
    ),
    "llm_action_items": ModuleInfo(
        "llm_action_items",
        "LLM action items",
        category="medium",
        requires_llm=True,
    ),
    "llm_custom_qa": ModuleInfo(
        "llm_custom_qa",
        "Ask notebook (LLM QA)",
        category="medium",
        requires_llm=True,
    ),
    "narrative_summary": ModuleInfo(
        "narrative_summary",
        "Narrative summary (LLM)",
        category="medium",
        requires_llm=True,
    ),
}


def _hard_deps(module_id: str) -> tuple[str, ...]:
    specs = HARD_PARENTS.get(module_id) or []
    return tuple(parent_id for parent_id, _ok in specs)


def get_module_info(module_id: str) -> ModuleInfo | None:
    base = _CATALOG.get(module_id)
    if base is None:
        return None
    deps = _hard_deps(module_id)
    if deps == base.dependencies:
        return base
    return ModuleInfo(
        module_id=base.module_id,
        label=base.label,
        category=base.category,
        cost_tier=base.cost_tier,
        requires_llm=base.requires_llm,
        exclude_from_default=base.exclude_from_default,
        dependencies=deps,
    )


def list_catalog_modules() -> list[ModuleInfo]:
    """All catalogued core modules in stable registry order."""
    from transcribe.analysis.modules import get_registered_modules

    registered = get_registered_modules()
    out: list[ModuleInfo] = []
    for mid in registered:
        info = get_module_info(mid)
        if info is not None:
            out.append(info)
    return out


def is_heavy_module(info: ModuleInfo | None) -> bool:
    """Match TranscriptX: heavy via ``cost_tier`` or ``category``."""
    if info is None:
        return False
    return info.cost_tier == "heavy" or info.category == "heavy"


def format_module_label(module_id: str) -> str:
    info = get_module_info(module_id)
    if info is None:
        return module_id
    suffix = " (heavy)" if is_heavy_module(info) else ""
    llm = " · LLM" if info.requires_llm else ""
    return f"{info.label}{suffix}{llm}"
