"""Tests for ModelValidator pre-job validation (hardening)."""

from __future__ import annotations

import pytest

from transcribe.providers.base import DiscoveryResult, ModelInfo
from transcribe.services.model_selection import ModelValidator


class FakeVisionProvider:
    """Mock vision provider for testing."""

    def __init__(self, models: list[ModelInfo] | None = None, error: str = ""):
        self.models = models or []
        self.error = error

    def list_models(self) -> DiscoveryResult:
        return DiscoveryResult(models=self.models, error=self.error)

    def list_vision_models(self) -> DiscoveryResult:
        return DiscoveryResult(models=self.models, error=self.error)


class FakeTextProvider:
    """Mock text provider for testing."""

    def __init__(self, models: list[ModelInfo] | None = None, unsuitable_names: set[str] | None = None):
        self.models = models or []
        self.unsuitable_names = unsuitable_names or set()

    def list_models(self) -> DiscoveryResult:
        return DiscoveryResult(models=self.models, error="")

    def is_unsuitable_model(self, model: str) -> bool:
        return model in self.unsuitable_names

    def resolve_configured_model(self, configured: str) -> str | None:
        names = {m.name for m in self.models}
        return configured if configured in names else None


class TestModelValidator:
    """Pre-job validation for vision and text models."""

    def test_validate_vision_model_empty(self) -> None:
        """Empty vision model should fail validation."""
        provider = FakeVisionProvider()
        validator = ModelValidator(provider)
        is_valid, msg = validator.validate_vision_model("")
        assert not is_valid
        assert "No vision model selected" in msg

    def test_validate_vision_model_not_found(self) -> None:
        """Non-existent vision model should fail validation."""
        models = [ModelInfo(name="glm-ocr", family="glm", capabilities=["vision"])]
        provider = FakeVisionProvider(models=models)
        validator = ModelValidator(provider)
        is_valid, msg = validator.validate_vision_model("nonexistent-model")
        assert not is_valid
        assert "not found in Ollama" in msg

    def test_validate_vision_model_success(self) -> None:
        """Valid OCR vision model should pass validation."""
        models = [ModelInfo(name="glm-ocr", family="glm", capabilities=["vision"])]
        provider = FakeVisionProvider(models=models)
        validator = ModelValidator(provider)
        is_valid, msg = validator.validate_vision_model("glm-ocr")
        assert is_valid
        assert not msg

    def test_validate_text_model_empty(self) -> None:
        """Empty text model is acceptable (optional)."""
        provider = FakeTextProvider()
        validator = ModelValidator(FakeVisionProvider(), text_provider=provider)
        is_valid, msg = validator.validate_text_model("")
        assert is_valid

    def test_validate_text_model_unsuitable(self) -> None:
        """Vision model used as text model should fail."""
        provider = FakeTextProvider(unsuitable_names={"llava-vision"})
        validator = ModelValidator(FakeVisionProvider(), text_provider=provider)
        is_valid, msg = validator.validate_text_model("llava-vision")
        assert not is_valid
        assert "not a text completion model" in msg

    def test_validate_text_model_not_found(self) -> None:
        """Non-existent text model should fail."""
        models = [ModelInfo(name="mistral", family="mistral", capabilities=["completion"])]
        provider = FakeTextProvider(models=models)
        validator = ModelValidator(FakeVisionProvider(), text_provider=provider)
        is_valid, msg = validator.validate_text_model("nonexistent-llm")
        assert not is_valid
        assert "not found in Ollama" in msg

    def test_validate_job_config_all_valid(self) -> None:
        """Valid job config should pass validation."""
        vision_models = [ModelInfo(name="glm-ocr", family="glm", capabilities=["vision"])]
        text_models = [ModelInfo(name="mistral", family="mistral", capabilities=["completion"])]
        vision_provider = FakeVisionProvider(models=vision_models)
        text_provider = FakeTextProvider(models=text_models)
        validator = ModelValidator(vision_provider, text_provider=text_provider)
        errors = validator.validate_job_config("glm-ocr", "mistral")
        assert not errors

    def test_validate_job_config_multiple_errors(self) -> None:
        """Multiple validation errors should be collected."""
        vision_provider = FakeVisionProvider(models=[])
        text_provider = FakeTextProvider(unsuitable_names={"embedding-model"})
        validator = ModelValidator(vision_provider, text_provider=text_provider)
        errors = validator.validate_job_config("nonexistent", "embedding-model")
        assert len(errors) >= 2
        assert any("Vision model" in e for e in errors)
        assert any("Text model" in e for e in errors)

    def test_validate_job_config_vision_model_only(self) -> None:
        """Job config with only vision model (text optional)."""
        vision_models = [ModelInfo(name="glm-ocr", family="glm", capabilities=["vision"])]
        vision_provider = FakeVisionProvider(models=vision_models)
        validator = ModelValidator(vision_provider)
        errors = validator.validate_job_config("glm-ocr", "")
        assert not errors
