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

    @property
    def ref(self) -> PromptRef:
        return PromptRef(prompt_id=self.prompt_id, version=self.version)

    def as_dict(self) -> dict[str, Any]:
        return {
            "prompt_id": self.prompt_id,
            "version": self.version,
            "title": self.title,
            "description": self.description,
            "input_mode": self.input_mode.value,
            "response_schema_id": self.response_schema_id,
            "model_requirements": {
                "capability": self.model_requirements.capability.value,
            },
        }
