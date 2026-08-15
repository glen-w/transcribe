"""Web-only analysis module grouping (presentation; TranscriptX family layout)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Iterator

TECHNICAL_OTHER_TITLE = "Technical / Other"
TECHNICAL_OTHER_KEY = "technical_other"


@dataclass(frozen=True)
class ModuleUIGroup:
    """One cognitive group in the Run Analysis review / picker."""

    key: str
    title: str
    module_ids: tuple[str, ...]


# Same family titles/order as TranscriptX ``module_ui_groups``, filtered to
# notebook core module ids (speaker/audio-only TX modules omitted).
MODULE_UI_GROUPS: tuple[ModuleUIGroup, ...] = (
    ModuleUIGroup(
        "summary_synthesis",
        "Summary & Synthesis",
        (
            "llm_summary",
            "narrative_summary",
            "llm_action_items",
            "llm_custom_qa",
            "summary",
            "highlights",
            "insights",
        ),
    ),
    ModuleUIGroup(
        "foundations",
        "Foundations",
        ("stats",),
    ),
    ModuleUIGroup(
        "language_meaning",
        "Language & Meaning",
        (
            "sentiment",
            "emotion",
            "contextual_emotion",
            "fine_grained_emotion",
            "ner",
            "entity_sentiment",
            "topic_modeling",
            "bertopic",
            "semantic_similarity",
            "understandability",
            "lexical_diversity",
            "epistemic_markers",
            "keyphrases",
        ),
    ),
    ModuleUIGroup(
        "dynamics_flow",
        "Dynamics & Flow",
        ("topic_shift", "moments", "affect_tension"),
    ),
    ModuleUIGroup(
        "visualizations",
        "Visualisations",
        ("wordclouds",),
    ),
)


def _build_maps() -> tuple[tuple[str, ...], frozenset[str]]:
    flat: list[str] = []
    for group in MODULE_UI_GROUPS:
        flat.extend(group.module_ids)
    return tuple(flat), frozenset(flat)


_FLAT_SPEC_ORDER, _SPEC_SET = _build_maps()


def _str_ids_only(iterable: Iterable[object]) -> Iterator[str]:
    for item in iterable:
        if isinstance(item, str) and item:
            yield item


def format_detector_label(detector_id: str) -> str:
    """Human label for a detector id (built-in or custom)."""
    from transcribe.detection.api import DetectionService

    for info in DetectionService.list_detectors():
        if info.detector_id == detector_id:
            return f"{info.title} ({info.detector_id})"
    return detector_id


def group_modules_for_ui(iterable: Iterable[object]) -> list[tuple[str, list[str]]]:
    """Non-empty (group title, [module ids]) in TX family order."""
    want = frozenset(_str_ids_only(iterable))
    if not want:
        return []
    result: list[tuple[str, list[str]]] = []
    for group in MODULE_UI_GROUPS:
        present = [mid for mid in group.module_ids if mid in want]
        if present:
            result.append((group.title, present))
    unknown = sorted(want - _SPEC_SET)
    if unknown:
        result.append((TECHNICAL_OTHER_TITLE, unknown))
    return result


def group_plan_for_ui(
    module_ids: Iterable[object],
    detector_ids: Iterable[object] = (),
) -> list[tuple[str, list[str]]]:
    """Module groups plus a Detection section when detectors are selected."""
    result = group_modules_for_ui(module_ids)
    dets = [d for d in _str_ids_only(detector_ids)]
    if dets:
        result.append(("Detection", dets))
    return result


def order_module_ids(iterable: Iterable[str]) -> list[str]:
    """Known ids in spec order, then unknown ids alphabetically."""
    want = frozenset(_str_ids_only(iterable))
    if not want:
        return []
    out: list[str] = [mid for mid in _FLAT_SPEC_ORDER if mid in want]
    out.extend(sorted(want - _SPEC_SET))
    return out
