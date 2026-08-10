"""OCR and cleanup adapters projecting legacy templates into PromptDefinition."""

from __future__ import annotations

from transcribe.prompt_engine.definition import (
    FREE_TEXT_SCHEMA,
    InputMode,
    ModelCapability,
    ModelRequirements,
    PromptDefinition,
    PromptFamily,
)
from transcribe.prompts import FAITHFUL_MARKDOWN, FAITHFUL_TEXT, REGISTRY as OCR_REGISTRY


def ocr_templates_as_definitions() -> list[PromptDefinition]:
    out: list[PromptDefinition] = []
    for tmpl in OCR_REGISTRY.values():
        out.append(
            PromptDefinition(
                prompt_id=tmpl.prompt_id,
                version=tmpl.version,
                title=tmpl.prompt_id.replace("_", " ").title(),
                description="OCR transcription prompt (vision).",
                system_prompt="",
                user_template=tmpl.body,
                input_mode=InputMode.VISION,
                response_schema_id=FREE_TEXT_SCHEMA,
                model_requirements=ModelRequirements(capability=ModelCapability.VISION),
                prompt_family=PromptFamily.OCR,
                is_builtin=True,
            )
        )
    return out


def cleanup_templates_as_definitions() -> list[PromptDefinition]:
    # Lazy import to avoid services ↔ prompt_engine circular import
    from transcribe.services.cleanup_prompts import CLEANUP_REGISTRY

    out: list[PromptDefinition] = []
    for mode, tmpl in CLEANUP_REGISTRY.items():
        body = tmpl.body.replace("{ocr_text}", "{{ocr_text}}")
        out.append(
            PromptDefinition(
                prompt_id=tmpl.prompt_id,
                version=tmpl.version,
                title=f"Cleanup: {mode}",
                description=f"Post-OCR cleanup mode `{mode}`.",
                system_prompt="",
                user_template=body,
                input_mode=InputMode.TEXT,
                response_schema_id=FREE_TEXT_SCHEMA,
                model_requirements=ModelRequirements(capability=ModelCapability.TEXT),
                prompt_family=PromptFamily.CLEANUP,
                is_builtin=True,
            )
        )
    return out


def resolve_ocr_prompt_text(
    *,
    prompt_id: str,
    custom_prompt: str | None = None,
    override: PromptDefinition | None = None,
) -> tuple[str, str, str]:
    """Return (prompt_id, version, exact prompt text) for OCR JobPlan freeze."""
    if custom_prompt and custom_prompt.strip():
        return "custom", "1", custom_prompt.strip()
    if override is not None and override.prompt_id == prompt_id:
        return override.prompt_id, override.version, override.user_template
    tmpl = OCR_REGISTRY.get(prompt_id, FAITHFUL_MARKDOWN)
    return tmpl.prompt_id, tmpl.version, tmpl.body


def resolve_cleanup_prompt_text(
    *,
    mode: str,
    ocr_text: str,
    override: PromptDefinition | None = None,
) -> tuple[str, str, str]:
    from transcribe.services.cleanup_prompts import CLEANUP_REGISTRY

    tmpl = CLEANUP_REGISTRY.get(mode)
    if tmpl is None:
        raise KeyError(f"unknown cleanup mode: {mode}")
    if override is not None and override.prompt_id == tmpl.prompt_id:
        text = override.user_template.replace("{{ocr_text}}", ocr_text)
        return override.prompt_id, override.version, text
    return tmpl.prompt_id, tmpl.version, tmpl.body.format(ocr_text=ocr_text)


__all__ = [
    "FAITHFUL_MARKDOWN",
    "FAITHFUL_TEXT",
    "cleanup_templates_as_definitions",
    "ocr_templates_as_definitions",
    "resolve_cleanup_prompt_text",
    "resolve_ocr_prompt_text",
]
