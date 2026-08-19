"""Current vs stale merged-draft (composite) helpers.

A composite is an LLM reconciliation of independent vision OCR attempts, not
another vote. It is current only while its source_attempt_ids match the
succeeded vision attempts that would feed a new merge (latest succeeded
vision per model identity). Stale composites are retained; they are never
treated as the live merged draft.
"""

from __future__ import annotations

from transcribe.domain.fingerprint import sha256_text
from transcribe.domain.models import OCRAttempt, PageResult


def is_vision_attempt(attempt: OCRAttempt) -> bool:
    return (attempt.attempt_kind or "vision") != "composite"


def succeeded_vision_with_text(attempts: list[OCRAttempt]) -> list[OCRAttempt]:
    return [
        attempt
        for attempt in attempts
        if is_vision_attempt(attempt)
        and attempt.status == "succeeded"
        and (attempt.raw_text or "").strip()
    ]


def _model_key(attempt: OCRAttempt) -> tuple[str, str | None]:
    model = ""
    digest = None
    if attempt.provenance is not None:
        model = attempt.provenance.model_name or ""
        digest = attempt.provenance.model_digest
    if not model:
        model = attempt.attempt_id
    return (model, digest)


def merge_input_vision_attempts(result: PageResult) -> list[OCRAttempt]:
    """Latest succeeded vision attempt per (model_name, digest) with text."""
    latest: dict[tuple[str, str | None], OCRAttempt] = {}
    for attempt in succeeded_vision_with_text(result.attempts):
        key = _model_key(attempt)
        prev = latest.get(key)
        if prev is None or attempt.started_at >= prev.started_at:
            latest[key] = attempt
    return sorted(latest.values(), key=lambda a: a.started_at)


def merge_input_ids(result: PageResult) -> frozenset[str]:
    return frozenset(attempt.attempt_id for attempt in merge_input_vision_attempts(result))


def is_composite_current(attempt: OCRAttempt, result: PageResult) -> bool:
    if (attempt.attempt_kind or "vision") != "composite":
        return False
    if attempt.status != "succeeded":
        return False
    sources = merge_input_ids(result)
    if not sources:
        return False
    return frozenset(attempt.source_attempt_ids) == sources


def current_composite_attempt(result: PageResult) -> OCRAttempt | None:
    """The unique current merged draft, or None if missing/stale.

    If several composites match the current source set, the latest ``started_at``
    wins; older matches stay on disk as history.
    """
    matches = [
        attempt
        for attempt in result.attempts
        if is_composite_current(attempt, result)
    ]
    if not matches:
        return None
    matches.sort(key=lambda a: a.started_at, reverse=True)
    return matches[0]


def stale_composite_attempts(result: PageResult) -> list[OCRAttempt]:
    current = current_composite_attempt(result)
    current_id = current.attempt_id if current else None
    return [
        attempt
        for attempt in result.attempts
        if (attempt.attempt_kind or "vision") == "composite"
        and attempt.status == "succeeded"
        and attempt.attempt_id != current_id
    ]


def evidence_fingerprint(result: PageResult) -> str:
    """Identity of OCR evidence for review invalidation."""
    source_ids = sorted(merge_input_ids(result))
    composite = current_composite_attempt(result)
    composite_id = composite.attempt_id if composite else ""
    return sha256_text("\n".join([*source_ids, f"composite:{composite_id}"]))


def reviewed_text_fingerprint(text: str) -> str:
    return sha256_text(text)


def seed_editor_text(result: PageResult) -> str:
    """Initial Transcription buffer: edit overlay, else current draft, else active source."""
    if result.edited_text is not None:
        return result.edited_text
    current = current_composite_attempt(result)
    active = result.active_attempt()
    if current is not None and (
        result.active_attempt_id == current.attempt_id
        or (active is not None and (active.attempt_kind or "vision") == "composite")
    ):
        return current.raw_text or ""
    if current is not None and active is None:
        return current.raw_text or ""
    if active is not None and (active.attempt_kind or "vision") == "composite":
        if current is not None:
            return current.raw_text or ""
        # Stale composite is active: fall back to latest merge-input vision text.
        inputs = merge_input_vision_attempts(result)
        if inputs:
            return inputs[-1].raw_text or ""
        return active.raw_text or ""
    if active is not None:
        return active.raw_text or ""
    if current is not None:
        return current.raw_text or ""
    return ""
