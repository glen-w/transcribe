"""Tests for text LLM circuit breaker (hardening)."""

from __future__ import annotations

import pytest

from transcribe.analysis.llm_runtime import OllamaTextClient


class TestTextLLMCircuitBreaker:
    """Prevent cascading failures with LLM circuit breaker."""

    def test_circuit_closed_initially(self) -> None:
        """Circuit should be closed when initialized."""
        client = OllamaTextClient(base_url="http://localhost:11434")
        assert not client.is_circuit_open()
        assert client._llm_failure_count == 0

    def test_circuit_opens_after_three_failures(self) -> None:
        """Circuit opens after 3 failures."""
        client = OllamaTextClient(base_url="http://localhost:11434")

        for i in range(2):
            client.record_llm_failure()
            assert not client.is_circuit_open(), f"Circuit should be open after failure {i+1}"

        client.record_llm_failure()
        assert client.is_circuit_open(), "Circuit should be open after 3 failures"
        assert client._llm_failure_count == 3

    def test_reset_circuit(self) -> None:
        """Can reset circuit after opening."""
        client = OllamaTextClient(base_url="http://localhost:11434")
        for _ in range(3):
            client.record_llm_failure()
        assert client.is_circuit_open()

        client.reset_llm_circuit()
        assert not client.is_circuit_open()
        assert client._llm_failure_count == 0

    def test_failure_count_accumulates(self) -> None:
        """Failure count should accumulate."""
        client = OllamaTextClient(base_url="http://localhost:11434")
        for i in range(5):
            client.record_llm_failure()
            assert client._llm_failure_count == i + 1
