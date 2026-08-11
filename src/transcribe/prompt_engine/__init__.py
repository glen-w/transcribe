"""Generic prompt infrastructure for Transcribe."""

from transcribe.prompt_engine.definition import (
    FREE_TEXT_SCHEMA,
    InputMode,
    ModelCapability,
    ModelRequirements,
    PromptDefinition,
    PromptFamily,
    PromptRef,
    validate_prompt_definition,
)
from transcribe.prompt_engine.execute import PromptExecutionResult, execute_prompt
from transcribe.prompt_engine.hub import (
    PromptCatalogueEntry,
    cleanup_render_for_job,
    list_catalogue,
    ocr_render_for_job,
    resolve_for_input_mode,
    resolve_prompt,
    resolve_prompt_ref,
)
from transcribe.prompt_engine.registry import get_prompt, list_builtin_prompts
from transcribe.prompt_engine.render import PromptRenderer, render_prompt
from transcribe.prompt_engine.validate import validate_response

__all__ = [
    "FREE_TEXT_SCHEMA",
    "InputMode",
    "ModelCapability",
    "ModelRequirements",
    "PromptCatalogueEntry",
    "PromptDefinition",
    "PromptExecutionResult",
    "PromptFamily",
    "PromptRef",
    "PromptRenderer",
    "cleanup_render_for_job",
    "execute_prompt",
    "get_prompt",
    "list_builtin_prompts",
    "list_catalogue",
    "ocr_render_for_job",
    "render_prompt",
    "resolve_for_input_mode",
    "resolve_prompt",
    "resolve_prompt_ref",
    "validate_prompt_definition",
    "validate_response",
]
