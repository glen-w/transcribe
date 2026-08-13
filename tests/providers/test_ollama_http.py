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


def test_call_with_retries_succeeds_after_retriable_failures():
    sleeps: list[float] = []
    attempts = {"n": 0}

    def op():
        attempts["n"] += 1
        if attempts["n"] < 3:
            raise ProviderError("connection", retriable=True, code="connection")
        return "ok"

    from transcribe.providers.ollama import call_with_retries

    result, retry_count = call_with_retries(op, sleep=sleeps.append)
    assert result == "ok"
    assert retry_count == 2
    assert sleeps == [0.5, 1.0]


def test_call_with_retries_does_not_retry_non_retriable():
    from transcribe.providers.ollama import call_with_retries

    calls = {"n": 0}

    def op():
        calls["n"] += 1
        raise ProviderError("model missing", retriable=False, code="model_missing")

    with pytest.raises(ProviderError) as exc:
        call_with_retries(op, sleep=lambda _s: None)
    assert exc.value.code == "model_missing"
    assert calls["n"] == 1


def test_call_with_retries_exhausts_attempts():
    from transcribe.providers.ollama import call_with_retries

    calls = {"n": 0}

    def op():
        calls["n"] += 1
        raise ProviderError("connection", retriable=True, code="connection")

    with pytest.raises(ProviderError) as exc:
        call_with_retries(op, max_retries=3, sleep=lambda _s: None)
    assert exc.value.code == "connection"
    assert calls["n"] == 3


def test_call_with_retries_does_not_retry_timeout():
    from transcribe.providers.ollama import call_with_retries

    calls = {"n": 0}

    def op():
        calls["n"] += 1
        raise ProviderError("Ollama request timed out", retriable=False, code="timeout")

    with pytest.raises(ProviderError) as exc:
        call_with_retries(op, max_retries=3, sleep=lambda _s: None)
    assert exc.value.code == "timeout"
    assert calls["n"] == 1


def test_text_client_does_not_retry_timeouts():
    from transcribe.analysis.llm_runtime import OllamaTextClient

    client = OllamaTextClient(base_url="http://localhost:11434", max_retries=3)
    calls = {"n": 0}

    def fake_post(path, body, *, timeout):
        calls["n"] += 1
        raise ProviderError("Ollama request timed out", retriable=False, code="timeout")

    with (
        patch.object(client._provider, "_http_post", side_effect=fake_post),
        patch("transcribe.providers.ollama.time.sleep", lambda _s: None),
    ):
        with pytest.raises(ProviderError) as exc:
            client.generate_with_meta(model="m", prompt="p")
    assert exc.value.code == "timeout"
    assert calls["n"] == 1


def test_transcribe_image_fills_default_num_predict_and_truncated():
    invalidate_discovery_cache()
    captured: dict = {}

    def fake_urlopen(req, timeout=None):
        url = req.full_url
        if url.endswith("/api/tags"):
            return _Resp({"models": [{"name": "m", "digest": "d"}]})
        if url.endswith("/api/show"):
            return _Resp({"capabilities": ["vision"], "details": {}})
        if url.endswith("/api/generate"):
            captured["body"] = json.loads(req.data.decode())
            return _Resp({"response": "hello", "eval_count": 4096})
        raise AssertionError(url)

    provider = OllamaVisionProvider("http://localhost:11434")
    with patch("urllib.request.urlopen", side_effect=fake_urlopen):
        result = provider.transcribe_image(
            model="m",
            prompt="p",
            image_bytes=b"abc",
            options={"temperature": 0.0},
        )
    assert captured["body"]["options"]["num_predict"] == 4096
    assert result.provider_metadata.get("truncated") is True
    assert result.provider_metadata.get("eval_count") == 4096


def test_model_load_http_error_is_not_retriable():
    invalidate_discovery_cache()
    import urllib.error

    body = (
        b'{"error":"llama-server process has terminated: exit status 1: '
        b"error loading model: unknown model architecture: 'mllama'\\n"
        b"error loading model: unknown model architecture: 'mllama'\"}"
    )
    calls = {"n": 0}

    def fake_urlopen(req, timeout=None):
        if req.full_url.endswith("/api/tags"):
            return _Resp({"models": []})
        if req.full_url.endswith("/api/show"):
            return _Resp({"capabilities": ["vision"], "details": {}})
        calls["n"] += 1
        raise urllib.error.HTTPError(
            req.full_url, 500, "Internal Server Error", hdrs=None, fp=BytesIO(body)
        )

    provider = OllamaVisionProvider("http://localhost:11434", max_retries=3)
    with patch("urllib.request.urlopen", side_effect=fake_urlopen):
        with pytest.raises(ProviderError) as exc:
            provider.transcribe_image(
                model="llama3.2-vision:11b",
                prompt="p",
                image_bytes=b"abc",
                options={"temperature": 0},
            )
        assert exc.value.code == "model_load"
        assert exc.value.retriable is False
        assert "architecture unsupported" in str(exc.value).lower()
    assert calls["n"] == 1


def test_is_fatal_model_load_error_markers():
    from transcribe.providers.ollama import (
        friendly_model_load_message,
        is_fatal_model_load_error,
    )

    assert is_fatal_model_load_error("unknown model architecture: 'mllama'")
    assert is_fatal_model_load_error("llama-server process has terminated")
    assert not is_fatal_model_load_error("connection reset")
    assert (
        "architecture unsupported"
        in friendly_model_load_message("unknown model architecture: 'mllama'").lower()
    )

    invalidate_discovery_cache()
    calls = {"n": 0}

    def fake_urlopen(req, timeout=None):
        if req.full_url.endswith("/api/tags"):
            return _Resp({"models": []})
        if req.full_url.endswith("/api/show"):
            return _Resp({"capabilities": ["vision"], "details": {}})
        calls["n"] += 1
        raise TimeoutError("timed out")

    provider = OllamaVisionProvider("http://localhost:11434", max_retries=3)
    with patch("urllib.request.urlopen", side_effect=fake_urlopen):
        with pytest.raises(ProviderError) as exc:
            provider.transcribe_image(
                model="m",
                prompt="p",
                image_bytes=b"abc",
                options={"temperature": 0},
            )
        assert exc.value.code == "timeout"
        assert exc.value.retriable is False
    assert calls["n"] == 1


def test_urlerror_timeout_reason_is_not_retriable():
    invalidate_discovery_cache()
    import urllib.error

    calls = {"n": 0}

    def fake_urlopen(req, timeout=None):
        if req.full_url.endswith("/api/tags"):
            return _Resp({"models": []})
        if req.full_url.endswith("/api/show"):
            return _Resp({"capabilities": ["vision"], "details": {}})
        calls["n"] += 1
        raise urllib.error.URLError(TimeoutError("timed out"))

    provider = OllamaVisionProvider("http://localhost:11434", max_retries=3)
    with patch("urllib.request.urlopen", side_effect=fake_urlopen):
        with pytest.raises(ProviderError) as exc:
            provider.transcribe_image(
                model="m",
                prompt="p",
                image_bytes=b"abc",
                options={"temperature": 0},
            )
        assert exc.value.code == "timeout"
        assert exc.value.retriable is False
    assert calls["n"] == 1


def test_generate_maps_model_missing_404():
    invalidate_discovery_cache()
    import urllib.error

    def fake_urlopen(req, timeout=None):
        if req.full_url.endswith("/api/tags"):
            return _Resp({"models": []})
        raise urllib.error.HTTPError(
            req.full_url,
            404,
            "Not Found",
            hdrs=None,
            fp=BytesIO(b'{"error":"model not found"}'),
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
