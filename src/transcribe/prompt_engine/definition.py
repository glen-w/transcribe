"""PromptDefinition and related types."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class InputMode(str, Enum):
    TEXT = "text"
    VISION = "vision"
    HYBRID = "hybrid"


class ModelCapability(str, Enum):
    TEXT = "text"
    VISION = "vision"


class PromptFamily(str, Enum):
    OCR = "ocr"
    CLEANUP = "cleanup"
    DETECTION = "detection"
    CUSTOM = "custom"


# Free-text responses (OCR / cleanup) use this schema id sentinel.
FREE_TEXT_SCHEMA = "free_text"

_MAX_SYSTEM_LEN = 8000
_MAX_TEMPLATE_LEN = 16000


@dataclass(frozen=True)
class ModelRequirements:
    capability: ModelCapability = ModelCapability.TEXT


@dataclass(frozen=True)
class PromptRef:
    prompt_id: str
    version: str

    def as_dict(self) -> dict[str, str]:
        return {"prompt_id": self.prompt_id, "version": self.version}


@dataclass(frozen=True)
class PromptDefinition:
    prompt_id: str
    version: str
    title: str
    description: str
    system_prompt: str
    user_template: str
    input_mode: InputMode
    response_schema_id: str
    model_requirements: ModelRequirements = field(
        default_factory=lambda: ModelRequirements()
    )
    default_generation_options: dict[str, Any] = field(default_factory=dict)
    prompt_family: PromptFamily = PromptFamily.DETECTION
    is_builtin: bool = True
    is_override: bool = False

    @property
    def ref(self) -> PromptRef:
        return PromptRef(prompt_id=self.prompt_id, version=self.version)

    def as_dict(self) -> dict[str, Any]:
        return {
            "format": "transcribe.prompt-definition",
            "schema_version": 1,
            "prompt_id": self.prompt_id,
            "version": self.version,
            "title": self.title,
            "description": self.description,
            "system_prompt": self.system_prompt,
            "user_template": self.user_template,
            "input_mode": self.input_mode.value,
            "response_schema_id": self.response_schema_id,
            "model_requirements": {
                "capability": self.model_requirements.capability.value,
            },
            "default_generation_options": dict(self.default_generation_options),
            "prompt_family": self.prompt_family.value,
            "is_builtin": self.is_builtin,
            "is_override": self.is_override,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> PromptDefinition:
        req = data.get("model_requirements") or {}
        cap = str(req.get("capability") or "text")
        family = str(data.get("prompt_family") or "detection")
        return cls(
            prompt_id=str(data["prompt_id"]),
            version=str(data.get("version") or "1"),
            title=str(data.get("title") or data["prompt_id"]),
            description=str(data.get("description") or ""),
            system_prompt=str(data.get("system_prompt") or ""),
            user_template=str(data.get("user_template") or ""),
            input_mode=InputMode(str(data.get("input_mode") or "text")),
            response_schema_id=str(data.get("response_schema_id") or FREE_TEXT_SCHEMA),
            model_requirements=ModelRequirements(
                capability=ModelCapability(cap)
                if cap in ("text", "vision")
                else ModelCapability.TEXT
            ),
            default_generation_options=dict(data.get("default_generation_options") or {}),
            prompt_family=PromptFamily(family)
            if family in {f.value for f in PromptFamily}
            else PromptFamily.CUSTOM,
            is_builtin=bool(data.get("is_builtin", False)),
            is_override=bool(data.get("is_override", False)),
        )


def validate_prompt_definition(defn: PromptDefinition) -> list[str]:
    """Return validation error messages (empty = ok)."""
    errors: list[str] = []
    if not defn.prompt_id.strip():
        errors.append("prompt_id required")
    if "{{" in defn.system_prompt and "}}" in defn.system_prompt:
        errors.append("system_prompt must not contain template slots")
    if len(defn.system_prompt) > _MAX_SYSTEM_LEN:
        errors.append(f"system_prompt exceeds {_MAX_SYSTEM_LEN} chars")
    if len(defn.user_template) > _MAX_TEMPLATE_LEN:
        errors.append(f"user_template exceeds {_MAX_TEMPLATE_LEN} chars")
    if defn.prompt_family == PromptFamily.DETECTION and not defn.response_schema_id:
        errors.append("detection prompts require response_schema_id")
    return errors
