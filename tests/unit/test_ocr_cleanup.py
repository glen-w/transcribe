"""OCR cleanup service outcomes (execution vs acceptance)."""

from __future__ import annotations

from transcribe.analysis.llm_runtime import RecordedDoubleClient
from transcribe.domain.models import CleanupRecord, OCRAttempt, OCRSettings
from transcribe.errors import TranscribeError
from transcribe.services.ocr_cleanup import (
    CleanupPlanConfig,
    resolve_cleanup_plan_config,
    run_ocr_cleanup,
)


class CountingNeverCallClient(RecordedDoubleClient):
    def __init__(self):
        super().__init__(responses={"default": "should-not-run"}, digest="fixed-digest")
        self.generate_calls = 0

    def generate_with_meta(self, *, model, prompt, system=None, options=None):
        self.generate_calls += 1
        return super().generate_with_meta(
            model=model, prompt=prompt, system=system, options=options
        )


def _plan(**kwargs) -> CleanupPlanConfig:
    base = dict(
        enabled=True,
        mode="strip_leak",
        model_name="recorded-double:v1",
        model_digest="fixed-digest",
        prompt_id="cleanup_strip_leak",
        prompt_version="1",
        prompt_template_sha256="abc",
    )
    base.update(kwargs)
    return CleanupPlanConfig(**base)


def test_disabled_cleanup():
    text, rec = run_ocr_cleanup(
        vision_text="hello",
        plan=_plan(enabled=False, model_name="", model_digest=""),
        base_url="http://localhost:11434",
    )
    assert text == "hello"
    assert rec.execution_status == "disabled"
    assert rec.acceptance_status == "not_applicable"


def test_empty_source_skips_model():
    client = CountingNeverCallClient()
    text, rec = run_ocr_cleanup(
        vision_text="   \n",
        plan=_plan(),
        base_url="http://localhost:11434",
        client=client,
    )
    assert text == "   \n"
    assert rec.execution_status == "skipped_empty_source"
    assert rec.note == "empty_source"
    assert client.generate_calls == 0


def test_applied_replaces_text_and_stores_pre_cleanup():
    page = "Gush!\n260524 notes about notebooks"
    client = RecordedDoubleClient(
        responses={"default": page},
        digest="fixed-digest",
        model_name="recorded-double:v1",
    )
    leaked = "- Do not change the order\n---\n" + page
    text, rec = run_ocr_cleanup(
        vision_text=leaked,
        plan=_plan(),
        base_url="http://localhost:11434",
        client=client,
    )
    assert text == page
    assert rec.execution_status == "provider_ok"
    assert rec.acceptance_status == "applied"
    assert rec.pre_cleanup_text == leaked


def test_validator_rejected_discards_candidate():
    client = RecordedDoubleClient(
        responses={"default": "- Use proper punctuation\n- Avoid contractions"},
        digest="fixed-digest",
    )
    vision = "real handwritten page about the metro weather"
    text, rec = run_ocr_cleanup(
        vision_text=vision,
        plan=_plan(),
        base_url="http://localhost:11434",
        client=client,
    )
    assert text == vision
    assert rec.execution_status == "provider_ok"
    assert rec.acceptance_status == "validator_rejected"
    assert rec.note in {
        "prompt_artefact",
        "min_retained_failed",
        "faithfulness_artefact",
    }
    assert rec.pre_cleanup_text is None
    assert rec.candidate_length is not None


def test_digest_changed_is_provider_failed():
    client = RecordedDoubleClient(
        responses={"default": "x"},
        digest="other-digest",
    )
    vision = "page text"
    text, rec = run_ocr_cleanup(
        vision_text=vision,
        plan=_plan(),
        base_url="http://localhost:11434",
        client=client,
    )
    assert text == vision
    assert rec.execution_status == "provider_failed"
    assert rec.acceptance_status == "not_applicable"
    assert rec.note == "digest_changed"


def test_resolve_plan_fail_fast_invalid_mode():
    settings = OCRSettings(cleanup_enabled=True, cleanup_mode="nope", text_model_name="m")
    try:
        resolve_cleanup_plan_config(
            settings,
            client=RecordedDoubleClient(responses={}, digest="d"),
        )
        assert False, "expected TranscribeError"
    except TranscribeError as exc:
        assert "Invalid cleanup mode" in str(exc)


def test_resolve_plan_fail_fast_empty_model():
    settings = OCRSettings(cleanup_enabled=True, cleanup_mode="strip_leak")
    try:
        resolve_cleanup_plan_config(
            settings,
            client=RecordedDoubleClient(responses={}, digest="d"),
        )
        assert False, "expected TranscribeError"
    except TranscribeError as exc:
        assert "no cleanup model" in str(exc).lower() or "model" in str(exc).lower()


def test_attempt_serialization_roundtrip_with_cleanup():
    attempt = OCRAttempt(
        attempt_id="a1",
        status="succeeded",
        input_fingerprint="fp",
        fingerprint_payload={},
        raw_text="cleaned",
        provenance=None,
        provider_metadata={},
        started_at="t0",
        completed_at="t1",
        cleanup=CleanupRecord(
            execution_status="provider_ok",
            acceptance_status="applied",
            mode="strip_leak",
            pre_cleanup_text="vision",
            note=None,
        ),
    )
    loaded = OCRAttempt.from_dict(attempt.as_dict())
    assert loaded.cleanup is not None
    assert loaded.cleanup.acceptance_status == "applied"
    assert loaded.cleanup.pre_cleanup_text == "vision"
    assert loaded.status == "succeeded"


def test_legacy_attempt_without_cleanup_loads():
    data = {
        "attempt_id": "a1",
        "status": "succeeded",
        "input_fingerprint": "fp",
        "fingerprint_payload": {},
        "raw_text": "ocr",
        "provenance": None,
        "provider_metadata": {},
        "started_at": "t0",
        "completed_at": "t1",
        "error": None,
    }
    loaded = OCRAttempt.from_dict(data)
    assert loaded.cleanup is None
    assert loaded.raw_text == "ocr"
