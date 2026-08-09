"""Offline unit tests for text LLM runtime binding and model policy."""

from __future__ import annotations

from typing import Any

from transcribe.analysis.llm_runtime import (
    RecordedDoubleClient,
    bind_text_llm_context,
    is_unsuitable_text_model_name,
    parse_json_object,
    set_text_llm_client,
    unavailable_model_result,
)


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


def test_unsuitable_text_model_name_patterns():
    assert is_unsuitable_text_model_name("llama3.2-vision:latest")
    assert is_unsuitable_text_model_name("nomic-embed-text")
    assert is_unsuitable_text_model_name("llava:7b")
    assert not is_unsuitable_text_model_name("llama3.2:3b")
    assert not is_unsuitable_text_model_name("mistral-small:latest")


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
    assert parse_json_object("prefix {\"a\": 2} trailing") == {"a": 2}
    assert parse_json_object("[1,2]") is None
    assert parse_json_object("") is None
    result = unavailable_model_result()
    assert result["outcome"] == "skipped_not_applicable"
    assert result["capability_reason"] == "unavailable_model"
