from __future__ import annotations

import pytest

from transcribe.errors import ProviderError
from transcribe.providers.ollama import (
    OllamaVisionProvider,
    is_local_machine_host,
    is_loopback_host,
    normalize_base_url,
    ollama_healthcheck,
    resolve_reachable_ollama_base_url,
)


def test_normalize_rejects_api_path():
    with pytest.raises(ProviderError) as exc:
        normalize_base_url("http://localhost:11434/api/generate")
    assert "server root" in str(exc.value).lower()


def test_normalize_strips_trailing_slash():
    assert normalize_base_url("http://localhost:11434/") == "http://localhost:11434"


def test_loopback_detection():
    assert is_loopback_host("http://localhost:11434")
    assert is_loopback_host("http://127.0.0.1:11434")
    assert not is_loopback_host("http://192.168.1.10:11434")
    assert not is_loopback_host("http://host.docker.internal:11434")


def test_local_machine_includes_docker_host_gateway():
    assert is_local_machine_host("http://localhost:11434")
    assert is_local_machine_host("http://host.docker.internal:11434")
    assert not is_local_machine_host("http://192.168.1.10:11434")


def test_resolve_reachable_prefers_healthy_configured(monkeypatch):
    monkeypatch.setattr(
        "transcribe.providers.ollama.ollama_healthcheck",
        lambda url: url == "http://127.0.0.1:11434",
    )
    got = resolve_reachable_ollama_base_url(
        "http://127.0.0.1:11434",
        fallback="http://host.docker.internal:11434",
    )
    assert got == "http://127.0.0.1:11434"


def test_resolve_reachable_falls_back_when_configured_unhealthy(monkeypatch):
    monkeypatch.setattr(
        "transcribe.providers.ollama.ollama_healthcheck",
        lambda url: url == "http://host.docker.internal:11434",
    )
    got = resolve_reachable_ollama_base_url(
        "http://127.0.0.1:11434",
        fallback="http://host.docker.internal:11434",
    )
    assert got == "http://host.docker.internal:11434"


def test_ollama_healthcheck_returns_false_on_unreachable(monkeypatch):
    def boom(_self) -> None:
        raise ProviderError("down", code="connection")

    monkeypatch.setattr(OllamaVisionProvider, "healthcheck", boom)
    assert not ollama_healthcheck("http://127.0.0.1:11434")
