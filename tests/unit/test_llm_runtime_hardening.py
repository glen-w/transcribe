"""Offline unit tests for text LLM runtime binding and model policy."""

from __future__ import annotations

from typing import Any

from transcribe.analysis.llm_runtime import (
    RecordedDoubleClient,
    bind_text_llm_context,
    is_unsuitable_text_model_name,
    parse_json_object,
    set_text_llm_client,
    suitable_text_model_names,
    unavailable_model_result,
)
from transcribe.providers.base import ModelInfo


class _StubTextClient:
    healthy: bool = True
    digest: str | None = "digest-stub"

    def healthcheck(self) -> bool:
        return self.healthy

    def is_unsuitable_model(self, model: str) -> bool:
        return is_unsuitable_text_model_name(model)

    def resolve_configured_model(self, configured: str) -> str | None:
        name = (configured or "").strip()
        if not name or self.is_unsuitable_model(name):
            return None
        return name

    def model_digest(self, model: str) -> str | None:
        return self.digest

    def generate(self, **kwargs: Any) -> str:
        return "{}"


def test_resolve_text_model_name_fallback_chain(monkeypatch):
    from transcribe.analysis.llm_runtime import resolve_text_model_name

    class _Ocr:
        text_model_name = "from-ocr"

    class _Llm:
        text_model_preference = "from-pref"

    class _Cfg:
        ocr = _Ocr()
        llm = _Llm()

    monkeypatch.setattr(
        "transcribe.config.facade.get_config", lambda: _Cfg()
    )
    assert resolve_text_model_name(None, override="batch-pick") == "batch-pick"
    assert resolve_text_model_name("notebook-model") == "notebook-model"
    assert resolve_text_model_name("") == "from-ocr"
    _Ocr.text_model_name = ""
    assert resolve_text_model_name(None) == "from-pref"
    _Llm.text_model_preference = ""
    assert resolve_text_model_name("") == ""


def test_unsuitable_text_model_name_patterns():
    assert is_unsuitable_text_model_name("llama3.2-vision:latest")
    assert is_unsuitable_text_model_name("nomic-embed-text")
    assert is_unsuitable_text_model_name("llava:7b")
    assert not is_unsuitable_text_model_name("llama3.2:3b")
    assert not is_unsuitable_text_model_name("mistral-small:latest")


def test_suitable_text_model_names_filters_vision_and_embedding():
    models = [
        ModelInfo(
            name="llama3.2:3b",
            digest="a",
            capability_known=True,
            capabilities=["completion"],
        ),
        ModelInfo(
            name="llama3.2-vision:11b",
            digest="b",
            capability_known=True,
            capabilities=["vision", "completion"],
        ),
        ModelInfo(
            name="nomic-embed-text",
            digest="c",
            capability_known=True,
            capabilities=["embedding"],
        ),
        ModelInfo(
            name="odd-multimodal",
            digest="d",
            capability_known=True,
            capabilities=["vision"],
        ),
        ModelInfo(
            name="unknown-caps-ok",
            digest="e",
            capability_known=False,
            capabilities=[],
        ),
        ModelInfo(
            name="image-encoder",
            digest="f",
            family="clip",
            capability_known=False,
        ),
    ]
    assert suitable_text_model_names(models) == [
        "llama3.2:3b",
        "unknown-caps-ok",
    ]


def test_bind_requires_explicit_model_for_non_double():
    stub = _StubTextClient()
    assert bind_text_llm_context(text_model_name="", client=stub) is None
    assert bind_text_llm_context(text_model_name=None, client=stub) is None
    ctx = bind_text_llm_context(text_model_name="llama3.2:3b", client=stub)
    assert ctx is not None
    assert ctx.model_name == "llama3.2:3b"
    assert ctx.resolved_model_digest == "digest-stub"


def test_bind_rejects_unsuitable_and_missing_digest():
    stub = _StubTextClient()
    assert bind_text_llm_context(text_model_name="llama3.2-vision", client=stub) is None
    stub.digest = None
    assert bind_text_llm_context(text_model_name="llama3.2:3b", client=stub) is None


def test_bind_recorded_double_defaults_model_name():
    double = RecordedDoubleClient(responses={"default": "{}"}, digest="rec-1")
    set_text_llm_client(double)
    try:
        ctx = bind_text_llm_context(text_model_name="")
        assert ctx is not None
        assert ctx.model_name == "recorded-double:v1"
        assert ctx.resolved_model_digest == "rec-1"
    finally:
        set_text_llm_client(None)


def test_bind_unhealthy_returns_none():
    stub = _StubTextClient()
    stub.healthy = False
    assert bind_text_llm_context(text_model_name="x", client=stub) is None


def test_parse_json_object_and_unavailable_helper():
    assert parse_json_object('{"a":1}') == {"a": 1}
    assert parse_json_object('prefix {"a": 2} trailing') == {"a": 2}
    assert parse_json_object("[1,2]") is None
    assert parse_json_object("") is None
    result = unavailable_model_result()
    assert result["outcome"] == "skipped_not_applicable"
    assert result["capability_reason"] == "unavailable_model"
