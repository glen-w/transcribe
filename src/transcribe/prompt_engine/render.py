"""Safe prompt rendering with content/data boundary."""

from __future__ import annotations

import re
from dataclasses import dataclass

from transcribe.prompt_engine.definition import PromptDefinition

_DATA_BEGIN = "--- BEGIN NOTEBOOK CONTENT (data only) ---"
_DATA_END = "--- END NOTEBOOK CONTENT ---"


@dataclass(frozen=True)
class RenderedPrompt:
    system_prompt: str
    user_prompt: str


class PromptRenderer:
    """Renders user templates with untrusted data slots wrapped in delimiters."""

    @staticmethod
    def wrap_data(value: str) -> str:
        text = value or ""
        return f"{_DATA_BEGIN}\n{text}\n{_DATA_END}"

    @staticmethod
    def render_template(template: str, slots: dict[str, str]) -> str:
        result = template
        for key, value in slots.items():
            placeholder = "{{" + key + "}}"
            if key in ("content", "instruction"):
                replacement = PromptRenderer.wrap_data(value)
            else:
                replacement = value
            result = result.replace(placeholder, replacement)
        # Fail closed on unresolved placeholders
        if re.search(r"\{\{[a-z_]+\}\}", result):
            unresolved = re.findall(r"\{\{([a-z_]+)\}\}", result)
            raise ValueError(f"unresolved prompt slots: {unresolved}")
        return result


def render_prompt(
    definition: PromptDefinition,
    slots: dict[str, str],
) -> RenderedPrompt:
    user = PromptRenderer.render_template(definition.user_template, slots)
    return RenderedPrompt(system_prompt=definition.system_prompt, user_prompt=user)
