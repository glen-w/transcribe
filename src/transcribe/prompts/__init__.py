"""Versioned faithful-transcription prompts.

Prompt wording adapted from Ollama-OCR (MIT), Copyright (c) 2024 Anoop Maurya.
See NOTICE.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class PromptTemplate:
    prompt_id: str
    version: str
    body: str


FAITHFUL_MARKDOWN = PromptTemplate(
    prompt_id="faithful_markdown",
    version="1",
    body=(
        "Extract all text content from this handwritten notebook page in {language} "
        "**exactly as it appears**, without modification, summarization, or omission.\n"
        "Format the output in markdown:\n"
        "- Use headers (#, ##, ###) **only if they appear on the page**\n"
        "- Preserve original lists (-, *, numbered lists) as they are\n"
        "- Maintain text formatting cues exactly as seen\n"
        "- **Do not add, interpret, or restructure any content**\n"
        "- If text is unclear, extract what is visible without guessing"
    ),
)

FAITHFUL_TEXT = PromptTemplate(
    prompt_id="faithful_text",
    version="1",
    body=(
        "Extract all visible text from this handwritten notebook page in {language} "
        "**without any changes**.\n"
        "- **Do not summarize, paraphrase, or infer missing text.**\n"
        "- Retain spacing, punctuation, and line breaks as closely as possible.\n"
        "- If text is unclear or partially visible, extract as much as possible without guessing.\n"
        "- **Include all text, even if it seems irrelevant or repeated.**"
    ),
)

REGISTRY: dict[str, PromptTemplate] = {
    FAITHFUL_MARKDOWN.prompt_id: FAITHFUL_MARKDOWN,
    FAITHFUL_TEXT.prompt_id: FAITHFUL_TEXT,
}


def render_prompt(
    *,
    prompt_id: str,
    language: str = "en",
    custom_prompt: str | None = None,
) -> tuple[str, str, str]:
    """Return (prompt_id, prompt_version, exact prompt text)."""
    if custom_prompt and custom_prompt.strip():
        return "custom", "1", custom_prompt.strip()
    template = REGISTRY.get(prompt_id, FAITHFUL_MARKDOWN)
    return template.prompt_id, template.version, template.body.format(language=language)
