"""Live Ollama vision-model probes (optional integration lane)."""

from __future__ import annotations

from pathlib import Path

import pytest

from transcribe.providers.ollama import OllamaVisionProvider, ollama_healthcheck
from transcribe.prompts import REGISTRY
from transcribe.services.model_advice import is_thinking_ocr_risk_name
from transcribe.services.ocr_model_recipes import recipe_for_model, recipe_prompt

pytestmark = pytest.mark.integration


@pytest.fixture(scope="module")
def ollama_available() -> str:
    base = "http://localhost:11434"
    if not ollama_healthcheck(base):
        pytest.skip("Ollama not reachable at localhost:11434")
    return base


def test_thinking_tags_classified_as_risk() -> None:
    assert is_thinking_ocr_risk_name("gemma4:26b")
    assert not is_thinking_ocr_risk_name("glm-ocr:latest")


def test_mini_page_probe_on_installed_vision_models(ollama_available: str) -> None:
    fixture = Path(__file__).resolve().parents[1] / "fixtures" / "mini_page.png"
    image_bytes = fixture.read_bytes()
    provider = OllamaVisionProvider(ollama_available, request_timeout=240.0)
    discovery = provider.list_vision_models(refresh=True)
    assert discovery.models, "expected at least one vision model from Ollama discovery"
    faithful = REGISTRY["faithful_markdown"].body
    passed = 0
    for model in discovery.models:
        name = model.name
        if is_thinking_ocr_risk_name(name):
            continue
        recipe = recipe_for_model(name)
        prompt = recipe_prompt(recipe)[2] if recipe else faithful
        try:
            provider.probe_vision_model_load(model=name)
            res = provider.transcribe_image(
                model=name,
                prompt=prompt,
                image_bytes=image_bytes,
                options={"temperature": 0.0, "num_predict": 256},
            )
        except Exception:
            continue
        if (res.text or "").strip():
            passed += 1
    assert passed >= 1, "no non-thinking vision model returned text on mini_page fixture"
