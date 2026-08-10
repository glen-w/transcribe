"""Built-in and resolved detector registry."""

from __future__ import annotations

from transcribe.detection.definition import (
    AggregationStrategy,
    CandidateStrategy,
    DetectorDefinition,
    DetectorScope,
    ModelMode,
    PromptRef,
)
from transcribe.detection.custom import compile_custom_detector, load_custom_detectors

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

_BUILTIN: dict[str, DetectorDefinition] = {
    POETRY_DETECTOR.detector_id: POETRY_DETECTOR,
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


__all__ = [
    "POETRY_DETECTOR",
    "compile_custom_detector",
    "get_builtin_detector",
    "get_builtin_detectors",
    "list_all_detectors",
    "load_custom_detectors",
    "resolve_detector",
]
