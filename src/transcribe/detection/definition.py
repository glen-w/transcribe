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
    NONE = "none"


class DetectorEngine(str, Enum):
    PROMPT = "prompt"
    LEXICAL_COUNT = "lexical_count"


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
    scope: DetectorScope
    input_mode: ModelMode
    prompt_ref: PromptRef | None = None
    engine: DetectorEngine = DetectorEngine.PROMPT
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
        if self.engine == DetectorEngine.PROMPT and self.prompt_ref is None:
            raise ValueError(
                f"detector {self.detector_id!r} requires prompt_ref for prompt engine"
            )
        if self.engine == DetectorEngine.LEXICAL_COUNT:
            matcher = (self.extra_config or {}).get("lexical_matcher")
            if not matcher:
                raise ValueError(
                    f"detector {self.detector_id!r} requires extra_config.lexical_matcher"
                )

    def cache_config(self) -> dict[str, Any]:
        return {
            "confidence_threshold": self.confidence_threshold,
            "window_size": self.window_size,
            "window_overlap": self.window_overlap,
            "candidate_strategy": self.candidate_strategy.value,
            "input_mode": self.input_mode.value,
            "scope": self.scope.value,
            "engine": self.engine.value,
            "aggregation_strategy": self.aggregation_strategy.value,
            **self.extra_config,
        }
