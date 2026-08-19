"""Result envelope builder — ports supply payloads only."""

from __future__ import annotations

import math
from typing import Any

from transcribe import __version__ as APP_VERSION
from transcribe.analysis import ADAPTER_VERSION
from transcribe.persistence.schema import require_format

OUTCOMES = frozenset(
    {
        "success",
        "skipped_not_applicable",
        "unavailable_dependency",
        "insufficient_data",
        "failed",
    }
)
ATTEMPT_STATES = frozenset({"running", "succeeded", "failed", "cancelled", "interrupted"})
CACHEABLE_OUTCOMES = frozenset(
    {
        "success",
        "skipped_not_applicable",
        "unavailable_dependency",
        "insufficient_data",
    }
)


def round_floats(obj: Any, ndigits: int = 6) -> Any:
    if isinstance(obj, float):
        if not math.isfinite(obj):
            return obj
        return round(obj, ndigits)
    if isinstance(obj, dict):
        return {k: round_floats(v, ndigits) for k, v in obj.items()}
    if isinstance(obj, list):
        return [round_floats(v, ndigits) for v in obj]
    return obj


CAPABILITIES = frozenset(
    {
        "available",
        "success",
        "partial",
        "unavailable_extra",
        "unavailable_model",
        "skipped_not_applicable",
        "invalid_input",
        "insufficient_data",
        "unavailable_dependency",
        "failed",
    }
)


def derive_capability(
    *,
    outcome: str,
    partial: bool = False,
    reason: str | None = None,
) -> str:
    if outcome == "success":
        return "partial" if partial else "success"
    if outcome == "insufficient_data":
        return "insufficient_data" if reason != "invalid_document" else "invalid_input"
    if outcome == "unavailable_dependency":
        return "unavailable_dependency"
    if outcome == "skipped_not_applicable":
        if reason == "unavailable_extra":
            return "unavailable_extra"
        if reason == "unavailable_model":
            return "unavailable_model"
        return "skipped_not_applicable"
    if outcome == "failed":
        return "failed"
    return outcome


def filter_live_evidence(
    evidence: list[dict[str, Any]] | None,
    *,
    current_content_fingerprint: str | None,
) -> list[dict[str, Any]]:
    """Return only evidence citations matching the current document fingerprint.

    Missing ``current_content_fingerprint`` → treat all citations as stale (empty).
    """
    if not evidence:
        return []
    if current_content_fingerprint is None:
        return []
    return [
        e
        for e in evidence
        if isinstance(e, dict) and e.get("content_fingerprint") == current_content_fingerprint
    ]


def build_envelope(
    *,
    project_id: str,
    module_id: str,
    module_version: str,
    cache_identity: str,
    content_fingerprint: str,
    attempt_state: str,
    outcome: str,
    payload: dict[str, Any],
    provenance: dict[str, Any],
    config_fingerprint: str,
    parents: list[dict[str, Any]] | None = None,
    warnings: list[dict[str, str]] | None = None,
    partial: bool = False,
    capability_reason: str | None = None,
    attempt_id: str | None = None,
    published: bool | None = None,
    lexicon_or_model: Any = None,
    resolved_model_digest: str | None = None,
    llm: dict[str, Any] | None = None,
    evidence: list[dict[str, Any]] | None = None,
    recorded_at: str | None = None,
) -> dict[str, Any]:
    if attempt_state not in ATTEMPT_STATES:
        raise ValueError(f"invalid attempt_state: {attempt_state}")
    if outcome not in OUTCOMES:
        raise ValueError(f"invalid outcome: {outcome}")
    env: dict[str, Any] = {
        "format": "transcribe.analysis-result",
        "schema_version": 1,
        "project_id": project_id,
        "module_id": module_id,
        "module_version": module_version,
        "cache_identity": cache_identity,
        "content_fingerprint": content_fingerprint,
        "attempt_state": attempt_state,
        "outcome": outcome,
        "capability": derive_capability(outcome=outcome, partial=partial, reason=capability_reason),
        "provenance": {
            **provenance,
            "module_version": module_version,
            "adapter_version": ADAPTER_VERSION,
            "app_version": APP_VERSION,
        },
        "warnings": warnings or [],
        "parents": parents or [],
        "config_fingerprint": config_fingerprint,
        "payload": round_floats(payload),
    }
    if partial:
        env["partial"] = True
    if attempt_id is not None:
        env["attempt_id"] = attempt_id
    if published is not None:
        env["published"] = published
    if lexicon_or_model is not None:
        env["lexicon_or_model"] = lexicon_or_model
    if resolved_model_digest is not None:
        env["resolved_model_digest"] = resolved_model_digest
    if llm is not None:
        env["llm"] = llm
    if evidence is not None:
        env["evidence"] = evidence
    if recorded_at is not None:
        env["recorded_at"] = recorded_at
    return require_format(env, "transcribe.analysis-result")
