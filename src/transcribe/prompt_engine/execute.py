"""Prompt execution against text or vision models."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

from transcribe.analysis.llm_runtime import parse_json_object
from transcribe.prompt_engine.definition import InputMode, PromptDefinition
from transcribe.prompt_engine.render import RenderedPrompt, render_prompt
from transcribe.prompt_engine.validate import validate_response


class TextExecutor(Protocol):
    def generate(
        self,
        *,
        model: str,
        prompt: str,
        system: str | None = None,
        options: dict[str, Any] | None = None,
    ) -> str: ...


class VisionExecutor(Protocol):
    def analyze_images(
        self,
        *,
        model: str,
        prompt: str,
        system: str | None = None,
        image_bytes_list: list[bytes],
        options: dict[str, Any] | None = None,
    ) -> str: ...


@dataclass(frozen=True)
class PromptExecutionResult:
    parsed: dict[str, Any] | None
    raw_text: str
    warning: dict[str, str] | None = None


def execute_prompt(
    definition: PromptDefinition,
    *,
    slots: dict[str, str],
    model: str,
    executor: TextExecutor | VisionExecutor,
    input_mode: InputMode,
    generation_options: dict[str, Any] | None = None,
    image_bytes_list: list[bytes] | None = None,
) -> PromptExecutionResult:
    rendered: RenderedPrompt = render_prompt(definition, slots)
    options = generation_options or definition.default_generation_options

    if input_mode == InputMode.VISION:
        if image_bytes_list is None or not hasattr(executor, "analyze_images"):
            return PromptExecutionResult(
                parsed=None,
                raw_text="",
                warning={
                    "code": "vision_unavailable",
                    "message": "vision executor or images missing",
                },
            )
        raw = executor.analyze_images(  # type: ignore[union-attr]
            model=model,
            prompt=rendered.user_prompt,
            system=rendered.system_prompt,
            image_bytes_list=image_bytes_list,
            options=options,
        )
    else:
        raw = executor.generate(
            model=model,
            prompt=rendered.user_prompt,
            system=rendered.system_prompt,
            options=options,
        )

    obj = parse_json_object(raw)
    if obj is None:
        return PromptExecutionResult(
            parsed=None,
            raw_text=raw[:2000],
            warning={
                "code": "abstain_unparseable",
                "message": "model response was not valid JSON",
            },
        )
    validated = validate_response(definition.response_schema_id, obj)
    if validated is None:
        return PromptExecutionResult(
            parsed=None,
            raw_text=raw[:2000],
            warning={
                "code": "abstain_unparseable",
                "message": "model JSON failed schema validation",
            },
        )
    return PromptExecutionResult(parsed=validated, raw_text=raw[:2000])
