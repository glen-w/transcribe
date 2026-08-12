"""Built-in and resolved detector registry."""

from __future__ import annotations

from transcribe.detection.custom import compile_custom_detector, load_custom_detectors
from transcribe.detection.definition import (
    AggregationStrategy,
    CandidateStrategy,
    DetectorDefinition,
    DetectorScope,
    ModelMode,
    PromptRef,
)

POETRY_DETECTOR = DetectorDefinition(
    detector_id="poetry",
    version="1",
    title="Poetry",
    description="Detect poems that may span consecutive notebook pages.",
    prompt_ref=PromptRef(prompt_id="poetry_detect_text_v1", version="1"),
    scope=DetectorScope.PAGE_WINDOW,
    input_mode=ModelMode.AUTO,
    candidate_strategy=CandidateStrategy.ALL_PAGES,
    window_size=3,
    window_overlap=1,
    confidence_threshold=0.7,
    finding_type="poetry",
    aggregation_strategy=AggregationStrategy.MERGE_ADJACENT_SPANS,
)

TODO_LISTS_DETECTOR = DetectorDefinition(
    detector_id="todo_lists",
    version="1",
    title="To-do lists",
    description="Detect checklists and to-do blocks, including cross-page continuations.",
    prompt_ref=PromptRef(prompt_id="todo_lists_detect_text_v1", version="1"),
    scope=DetectorScope.PAGE_WINDOW,
    input_mode=ModelMode.AUTO,
    candidate_strategy=CandidateStrategy.ALL_PAGES,
    window_size=2,
    window_overlap=1,
    confidence_threshold=0.7,
    finding_type="todo_lists",
    aggregation_strategy=AggregationStrategy.MERGE_ADJACENT_SPANS,
)

LISTS_DETECTOR = DetectorDefinition(
    detector_id="lists",
    version="1",
    title="Lists",
    description="Detect non-todo lists such as shopping lists, inventories, and outlines.",
    prompt_ref=PromptRef(prompt_id="lists_detect_text_v1", version="1"),
    scope=DetectorScope.PAGE_WINDOW,
    input_mode=ModelMode.AUTO,
    candidate_strategy=CandidateStrategy.ALL_PAGES,
    window_size=2,
    window_overlap=1,
    confidence_threshold=0.7,
    finding_type="lists",
    aggregation_strategy=AggregationStrategy.MERGE_ADJACENT_SPANS,
)

QUOTATIONS_DETECTOR = DetectorDefinition(
    detector_id="quotations",
    version="1",
    title="Quotations",
    description="Detect quoted material, block quotes, and attributions across pages.",
    prompt_ref=PromptRef(prompt_id="quotations_detect_text_v1", version="1"),
    scope=DetectorScope.PAGE_WINDOW,
    input_mode=ModelMode.AUTO,
    candidate_strategy=CandidateStrategy.ALL_PAGES,
    window_size=3,
    window_overlap=1,
    confidence_threshold=0.7,
    finding_type="quotations",
    aggregation_strategy=AggregationStrategy.MERGE_ADJACENT_SPANS,
)

BEER_LABELS_DETECTOR = DetectorDefinition(
    detector_id="beer_labels",
    version="1",
    title="Beer labels",
    description="Detect beer bottle/can labels and beer branding on notebook pages.",
    prompt_ref=PromptRef(prompt_id="beer_labels_detect_text_v1", version="1"),
    scope=DetectorScope.PAGE_WINDOW,
    input_mode=ModelMode.AUTO,
    candidate_strategy=CandidateStrategy.ALL_PAGES,
    window_size=2,
    window_overlap=1,
    confidence_threshold=0.7,
    finding_type="beer_labels",
    aggregation_strategy=AggregationStrategy.MERGE_ADJACENT_SPANS,
)

_BUILTIN: dict[str, DetectorDefinition] = {
    d.detector_id: d
    for d in (
        POETRY_DETECTOR,
        TODO_LISTS_DETECTOR,
        LISTS_DETECTOR,
        QUOTATIONS_DETECTOR,
        BEER_LABELS_DETECTOR,
    )
}


def get_builtin_detectors() -> list[DetectorDefinition]:
    return list(_BUILTIN.values())


def get_builtin_detector(detector_id: str) -> DetectorDefinition | None:
    return _BUILTIN.get(detector_id)


def resolve_detector(
    detector_id: str,
    *,
    custom_detectors: list[DetectorDefinition] | None = None,
) -> DetectorDefinition | None:
    builtin = get_builtin_detector(detector_id)
    if builtin is not None:
        return builtin
    if custom_detectors:
        for d in custom_detectors:
            if d.detector_id == detector_id:
                return d
    return None


def list_all_detectors() -> list[DetectorDefinition]:
    custom = load_custom_detectors()
    return get_builtin_detectors() + custom


def detectors_using_prompt(prompt_id: str) -> list[DetectorDefinition]:
    return [d for d in list_all_detectors() if d.prompt_ref.prompt_id == prompt_id]


__all__ = [
    "BEER_LABELS_DETECTOR",
    "LISTS_DETECTOR",
    "POETRY_DETECTOR",
    "QUOTATIONS_DETECTOR",
    "TODO_LISTS_DETECTOR",
    "compile_custom_detector",
    "detectors_using_prompt",
    "get_builtin_detector",
    "get_builtin_detectors",
    "list_all_detectors",
    "load_custom_detectors",
    "resolve_detector",
]
