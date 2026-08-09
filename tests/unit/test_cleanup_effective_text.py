"""Effective-text precedence with cleanup applied."""

from __future__ import annotations

from transcribe.domain.models import CleanupRecord, OCRAttempt, PageResult


def _attempt(raw: str, *, cleanup: CleanupRecord | None = None) -> OCRAttempt:
    return OCRAttempt(
        attempt_id="a1",
        status="succeeded",
        input_fingerprint="fp",
        fingerprint_payload={},
        raw_text=raw,
        provenance=None,
        provider_metadata={},
        started_at="t0",
        completed_at="t1",
        cleanup=cleanup,
    )


def test_edited_text_wins_over_cleaned_raw():
    result = PageResult(
        page_id="p1",
        active_attempt_id="a1",
        edited_text="user edit",
        attempts=[
            _attempt(
                "cleaned ocr",
                cleanup=CleanupRecord(
                    execution_status="provider_ok",
                    acceptance_status="applied",
                    pre_cleanup_text="vision ocr",
                ),
            )
        ],
    )
    assert result.effective_text() == "user edit"


def test_effective_text_is_cleaned_when_applied_without_edit():
    result = PageResult(
        page_id="p1",
        active_attempt_id="a1",
        edited_text=None,
        attempts=[
            _attempt(
                "cleaned ocr",
                cleanup=CleanupRecord(
                    execution_status="provider_ok",
                    acceptance_status="applied",
                    pre_cleanup_text="vision ocr",
                ),
            )
        ],
    )
    assert result.effective_text() == "cleaned ocr"


def test_effective_text_stays_vision_when_cleanup_rejected():
    result = PageResult(
        page_id="p1",
        active_attempt_id="a1",
        edited_text=None,
        attempts=[
            _attempt(
                "vision ocr",
                cleanup=CleanupRecord(
                    execution_status="provider_ok",
                    acceptance_status="validator_rejected",
                    note="prompt_artefact",
                    pre_cleanup_text=None,
                ),
            )
        ],
    )
    assert result.effective_text() == "vision ocr"
