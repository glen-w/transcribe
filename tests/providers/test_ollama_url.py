from __future__ import annotations

import pytest

from transcribe.errors import ProviderError
from transcribe.providers.ollama import is_loopback_host, normalize_base_url


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
