"""DetectorDefinition and related types."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from transcribe.prompt_engine.definition import ModelRequirements


class DetectorScope(str, Enum):
    PAGE = "page"
    PAGE_WINDOW = "page_window"
    NOTEBOOK = "notebook"


class CandidateStrategy(str, Enum):
    ALL_PAGES = "all_pages"


class AggregationStrategy(str, Enum):
    MERGE_ADJACENT_SPANS = "merge_adjacent_spans"


class ModelMode(str, Enum):
    AUTO = "auto"
    TEXT = "text"
    VISION = "vision"


@dataclass(frozen=True)
class PromptRef:
    prompt_id: str
    version: str

    def as_dict(self) -> dict[str, str]:
        return {"prompt_id": self.prompt_id, "version": self.version}


@dataclass(frozen=True)
class DetectorDefinition:
    detector_id: str
    version: str
    title: str
    description: str
    prompt_ref: PromptRef
    scope: DetectorScope
    input_mode: ModelMode
    candidate_strategy: CandidateStrategy = CandidateStrategy.ALL_PAGES
    window_size: int = 3
    window_overlap: int = 1
    confidence_threshold: float = 0.7
    finding_type: str = ""
    aggregation_strategy: AggregationStrategy = AggregationStrategy.MERGE_ADJACENT_SPANS
    model_requirements: ModelRequirements | None = None
    extra_config: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.finding_type:
            object.__setattr__(self, "finding_type", self.detector_id)

    def cache_config(self) -> dict[str, Any]:
        return {
            "confidence_threshold": self.confidence_threshold,
            "window_size": self.window_size,
            "window_overlap": self.window_overlap,
            "candidate_strategy": self.candidate_strategy.value,
            "input_mode": self.input_mode.value,
            "scope": self.scope.value,
            **self.extra_config,
        }
