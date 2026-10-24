"""Tests for ModelConfiguration validation (hardening)."""

from __future__ import annotations

import pytest

from transcribe.config.models import ModelConfiguration


class TestModelConfiguration:
    """Validate model configuration with timeout and retry constraints."""

    def test_valid_configuration(self) -> None:
        """Valid config with all fields in range."""
        config = ModelConfiguration(
            vision_model="glm-ocr",
            text_model="mistral",
            timeout_s=300.0,
            max_retries=3,
            ollama_base_url="http://localhost:11434",
            remote_ollama_acknowledged=False,
        )
        assert config.vision_model == "glm-ocr"
        assert config.timeout_s == 300.0
        assert config.max_retries == 3

    def test_timeout_too_low(self) -> None:
        """Timeout < 1.0 should fail."""
        with pytest.raises(ValueError, match="timeout_s must be between"):
            ModelConfiguration(
                vision_model="glm-ocr",
                timeout_s=0.5,
                max_retries=3,
            )

    def test_timeout_too_high(self) -> None:
        """Timeout > 3600 should fail."""
        with pytest.raises(ValueError, match="timeout_s must be between"):
            ModelConfiguration(
                vision_model="glm-ocr",
                timeout_s=3601.0,
                max_retries=3,
            )

    def test_max_retries_too_low(self) -> None:
        """max_retries < 1 should fail."""
        with pytest.raises(ValueError, match="max_retries must be between"):
            ModelConfiguration(
                vision_model="glm-ocr",
                timeout_s=300.0,
                max_retries=0,
            )

    def test_max_retries_too_high(self) -> None:
        """max_retries > 10 should fail."""
        with pytest.raises(ValueError, match="max_retries must be between"):
            ModelConfiguration(
                vision_model="glm-ocr",
                timeout_s=300.0,
                max_retries=11,
            )

    def test_validate_empty_vision_model(self) -> None:
        """Validation should catch empty vision_model."""
        config = ModelConfiguration(
            vision_model="",
            text_model="mistral",
            timeout_s=300.0,
            max_retries=3,
        )
        errors = config.validate()
        assert any("vision_model must not be empty" in e for e in errors)

    def test_validate_all_errors(self) -> None:
        """Validation should collect multiple errors."""
        config = ModelConfiguration(
            vision_model="",
            timeout_s=0.5,
            max_retries=11,
        )
        errors = config.validate()
        assert len(errors) == 3  # vision_model, timeout_s, max_retries

    def test_safe_defaults(self) -> None:
        """safe_defaults() should create a valid config."""
        config = ModelConfiguration.safe_defaults()
        errors = config.validate()
        assert not errors, f"Safe defaults have errors: {errors}"
