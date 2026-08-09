from __future__ import annotations

import json
from io import BytesIO
from unittest.mock import patch

import pytest

from transcribe.errors import ProviderError
from transcribe.providers.base import ModelInfo
from transcribe.providers.ollama import (
    OllamaVisionProvider,
    _discovery_cache,
    get_cached_discovery,
    invalidate_discovery_cache,
)


class _Resp:
    def __init__(self, payload: dict, code: int = 200):
        self._payload = payload
        self.code = code

    def read(self) -> bytes:
        return json.dumps(self._payload).encode()

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def test_discovery_filters_vision_and_caches():
    invalidate_discovery_cache()
    tags = {
        "models": [
            {"name": "vision-a", "digest": "d1", "details": {"family": "x"}},
            {"name": "text-b", "digest": "d2", "details": {"family": "y"}},
        ]
    }
    shows = {
        "vision-a": {"capabilities": ["completion", "vision"], "details": {}},
        "text-b": {"capabilities": ["completion"], "details": {}},
    }
    calls: list[str] = []

    def fake_urlopen(req, timeout=None):
        url = req.full_url
        calls.append(url)
        if url.endswith("/api/tags"):
            return _Resp(tags)
        if url.endswith("/api/show"):
            body = json.loads(req.data.decode())
            return _Resp(shows[body["model"]])
        raise AssertionError(url)

    provider = OllamaVisionProvider("http://localhost:11434", discovery_ttl=60)
    with patch("urllib.request.urlopen", side_effect=fake_urlopen):
        result = provider.list_vision_models(refresh=True)
        assert [m.name for m in result.models] == ["vision-a"]
        n = len(calls)
        # cached on same provider
        result2 = provider.list_vision_models(refresh=False)
        assert [m.name for m in result2.models] == ["vision-a"]
        assert len(calls) == n
        # shared across new provider instances
        other = OllamaVisionProvider("http://localhost:11434", discovery_ttl=60)
        other.list_vision_models(refresh=False)
        assert len(calls) == n
        # refresh forces rediscovery
        provider.list_vision_models(refresh=True)
        assert len(calls) > n


def test_invalidate_discovery_cache_by_url():
    invalidate_discovery_cache()
    models = [
        ModelInfo(
            name="m",
            digest="d",
            size=1,
            family="x",
            parameter_size=None,
            capabilities=["vision"],
            capability_known=True,
        )
    ]
    get_cached_discovery(
        "http://localhost:11434",
        request_timeout=300.0,
        discovery_ttl=60.0,
        refresh=True,
        fetch=lambda: (models, None),
    )
    assert any("localhost:11434" in k for k in _discovery_cache)
    invalidate_discovery_cache("http://localhost:11434")
    assert not any("localhost:11434" in k for k in _discovery_cache)


def test_generate_maps_model_missing_404():
    invalidate_discovery_cache()
    import urllib.error

    def fake_urlopen(req, timeout=None):
        if req.full_url.endswith("/api/tags"):
            return _Resp({"models": []})
        raise urllib.error.HTTPError(
            req.full_url, 404, "Not Found", hdrs=None, fp=BytesIO(b'{"error":"model not found"}')
        )

    provider = OllamaVisionProvider("http://localhost:11434")
    with patch("urllib.request.urlopen", side_effect=fake_urlopen):
        with pytest.raises(ProviderError) as exc:
            provider.transcribe_image(
                model="nope",
                prompt="p",
                image_bytes=b"abc",
                options={"temperature": 0},
            )
        assert exc.value.code == "model_missing"
        assert exc.value.retriable is False
