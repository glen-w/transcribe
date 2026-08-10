"""Prompt-backed notebook detection."""

from transcribe.detection.api import DetectionService
from transcribe.detection.definition import (
    AggregationStrategy,
    CandidateStrategy,
    DetectorDefinition,
    DetectorScope,
    ModelMode,
    PromptRef,
)
from transcribe.detection.findings import DetectionFinding
from transcribe.detection.freshness import detector_freshness
from transcribe.detection.registry import get_builtin_detectors, resolve_detector
from transcribe.detection.runner import DetectionRunner

__all__ = [
    "AggregationStrategy",
    "CandidateStrategy",
    "DetectionFinding",
    "DetectionRunner",
    "DetectionService",
    "DetectorDefinition",
    "DetectorScope",
    "ModelMode",
    "PromptRef",
    "detector_freshness",
    "get_builtin_detectors",
    "resolve_detector",
]
