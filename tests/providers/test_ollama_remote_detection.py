"""Tests for remote Ollama detection and classification (hardening)."""

from __future__ import annotations

import pytest

from transcribe.providers.ollama import (
    ModelLoadClassification,
    classify_model_load_error,
    is_local_ollama_url,
)


class TestIsLocalOllamaUrl:
    """Detect localhost vs remote Ollama instances."""

    def test_localhost_http(self) -> None:
        """http://localhost should be local."""
        assert is_local_ollama_url("http://localhost:11434")

    def test_127_0_0_1(self) -> None:
        """127.0.0.1 should be local."""
        assert is_local_ollama_url("http://127.0.0.1:11434")

    def test_ipv6_loopback(self) -> None:
        """[::1] should be local."""
        assert is_local_ollama_url("http://[::1]:11434")

    def test_empty_url_is_local(self) -> None:
        """Empty URL defaults to local."""
        assert is_local_ollama_url("")

    def test_remote_hostname(self) -> None:
        """example.com should be remote."""
        assert not is_local_ollama_url("http://example.com:11434")

    def test_remote_ip_address(self) -> None:
        """192.168.1.100 should be remote."""
        assert not is_local_ollama_url("http://192.168.1.100:11434")

    def test_remote_public_ip(self) -> None:
        """Public IP should be remote."""
        assert not is_local_ollama_url("http://8.8.8.8:11434")

    def test_normalized_url(self) -> None:
        """Should work with or without http prefix."""
        assert is_local_ollama_url("localhost:11434")
        assert not is_local_ollama_url("example.com:11434")


class TestClassifyModelLoadError:
    """Classify model load errors for recovery hints."""

    def test_unsupported_architecture(self) -> None:
        """Classify unknown model architecture errors."""
        msg = "error: unknown model architecture: mllama"
        classification = classify_model_load_error(msg)
        assert classification == ModelLoadClassification.UNSUPPORTED_ARCHITECTURE

    def test_loader_crash(self) -> None:
        """Classify loader crash errors."""
        msg = "error loading model: llama-server process has terminated"
        classification = classify_model_load_error(msg)
        assert classification == ModelLoadClassification.LOADER_CRASH

    def test_error_loading_model(self) -> None:
        """Classify generic error loading model."""
        msg = "error loading model: out of memory"
        classification = classify_model_load_error(msg)
        assert classification == ModelLoadClassification.LOADER_CRASH

    def test_network_timeout(self) -> None:
        """Classify network timeout errors."""
        msg = "request timed out after 30s"
        classification = classify_model_load_error(msg)
        assert classification == ModelLoadClassification.NETWORK_TIMEOUT

    def test_connectivity_refused(self) -> None:
        """Classify connection refused errors."""
        msg = "connection refused: cannot reach host"
        classification = classify_model_load_error(msg)
        assert classification == ModelLoadClassification.CONNECTIVITY_ERROR

    def test_unknown_error(self) -> None:
        """Classify unknown errors as UNKNOWN."""
        msg = "something unexpected happened"
        classification = classify_model_load_error(msg)
        assert classification == ModelLoadClassification.UNKNOWN

    def test_empty_error_message(self) -> None:
        """Empty error message should be UNKNOWN."""
        classification = classify_model_load_error("")
        assert classification == ModelLoadClassification.UNKNOWN

    def test_case_insensitive(self) -> None:
        """Classification should be case-insensitive."""
        msg = "ERROR: UNKNOWN MODEL ARCHITECTURE: test"
        classification = classify_model_load_error(msg)
        assert classification == ModelLoadClassification.UNSUPPORTED_ARCHITECTURE
