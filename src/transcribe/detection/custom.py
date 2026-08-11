"""Declarative custom detector definitions."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from transcribe.detection.definition import (
    AggregationStrategy,
    CandidateStrategy,
    DetectorDefinition,
    DetectorScope,
    ModelMode,
    PromptRef,
)
from transcribe.persistence.atomic import read_json
from transcribe.runtime_paths import build_runtime_paths

_MAX_INSTRUCTION_LEN = 4000
_SLUG_RE = re.compile(r"[^a-z0-9]+")


@dataclass(frozen=True)
class CustomDetectorDefinition:
    name: str
    instruction: str
    scope: str = "notebook"
    adjacent_page_detection: bool = True
    model_mode: str = "auto"
    confidence_threshold: float = 0.7
    custom_id: str = ""

    def slug(self) -> str:
        if self.custom_id:
            return _SLUG_RE.sub("-", self.custom_id.strip().lower()).strip("-")
        base = _SLUG_RE.sub("-", self.name.strip().lower()).strip("-") or "custom"
        digest = hashlib.sha256(self.instruction.encode()).hexdigest()[:8]
        return f"{base}-{digest}"


def _custom_config_dir() -> Path:
    return build_runtime_paths().data_dir / "config" / "detection" / "custom"


def load_custom_detectors() -> list[DetectorDefinition]:
    root = _custom_config_dir()
    if not root.exists():
        return []
    out: list[DetectorDefinition] = []
    for path in sorted(root.glob("*.json")):
        try:
            payload = read_json(path)
            compiled = compile_custom_detector(payload)
            if compiled is not None:
                out.append(compiled)
        except (OSError, ValueError, TypeError):
            continue
    return out


def compile_custom_detector(payload: dict[str, Any] | CustomDetectorDefinition) -> DetectorDefinition | None:
    if isinstance(payload, CustomDetectorDefinition):
        custom = payload
    else:
        custom = CustomDetectorDefinition(
            name=str(payload.get("name") or "Custom"),
            instruction=str(payload.get("instruction") or ""),
            scope=str(payload.get("scope") or "notebook"),
            adjacent_page_detection=bool(payload.get("adjacent_page_detection", True)),
            model_mode=str(payload.get("model_mode") or "auto"),
            confidence_threshold=float(payload.get("confidence_threshold") or 0.7),
            custom_id=str(payload.get("custom_id") or payload.get("id") or ""),
        )
    instruction = custom.instruction.strip()
    if not instruction or len(instruction) > _MAX_INSTRUCTION_LEN:
        return None
    slug = custom.slug()
    scope = DetectorScope.NOTEBOOK if custom.scope == "notebook" else DetectorScope.PAGE
    if custom.adjacent_page_detection and scope == DetectorScope.NOTEBOOK:
        scope = DetectorScope.PAGE_WINDOW
    try:
        model_mode = ModelMode(custom.model_mode)
    except ValueError:
        model_mode = ModelMode.AUTO
    prompt_id = (
        "custom_detect_vision_v1"
        if model_mode == ModelMode.VISION
        else "custom_detect_v1"
    )
    version = "1"
    if isinstance(payload, dict) and payload.get("version"):
        version = str(payload["version"])
    return DetectorDefinition(
        detector_id=f"custom/{slug}",
        version=version,
        title=custom.name,
        description=instruction[:200],
        prompt_ref=PromptRef(prompt_id=prompt_id, version="1"),
        scope=scope,
        input_mode=model_mode,
        candidate_strategy=CandidateStrategy.ALL_PAGES,
        window_size=3 if custom.adjacent_page_detection else 1,
        window_overlap=1 if custom.adjacent_page_detection else 0,
        confidence_threshold=max(0.0, min(1.0, custom.confidence_threshold)),
        finding_type=f"custom:{slug}",
        aggregation_strategy=AggregationStrategy.MERGE_ADJACENT_SPANS,
        extra_config={"instruction": instruction},
    )


def save_custom_detector(definition: CustomDetectorDefinition) -> Path:
    from transcribe.persistence.atomic import write_json_atomic

    root = _custom_config_dir()
    root.mkdir(parents=True, exist_ok=True)
    slug = definition.slug()
    path = root / f"{slug}.json"
    payload = {
        "format": "transcribe.custom-detector",
        "schema_version": 1,
        "name": definition.name,
        "instruction": definition.instruction,
        "scope": definition.scope,
        "adjacent_page_detection": definition.adjacent_page_detection,
        "model_mode": definition.model_mode,
        "confidence_threshold": definition.confidence_threshold,
        "custom_id": slug,
        "version": "1",
    }
    write_json_atomic(path, payload)
    return path


def delete_custom_detector(custom_id: str) -> bool:
    root = _custom_config_dir()
    path = root / f"{custom_id}.json"
    if not path.exists():
        # try slugified
        slug = _SLUG_RE.sub("-", custom_id.strip().lower()).strip("-")
        path = root / f"{slug}.json"
    if not path.exists():
        return False
    path.unlink(missing_ok=True)
    return True


def list_custom_detector_payloads() -> list[dict[str, Any]]:
    root = _custom_config_dir()
    if not root.exists():
        return []
    out: list[dict[str, Any]] = []
    for path in sorted(root.glob("*.json")):
        try:
            out.append(read_json(path))
        except (OSError, ValueError, TypeError):
            continue
    return out
