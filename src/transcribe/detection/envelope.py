"""Detection result envelope builder."""

from __future__ import annotations

from typing import Any

from transcribe import __version__ as APP_VERSION
from transcribe.analysis.envelope import (
    ATTEMPT_STATES,
    CACHEABLE_OUTCOMES,
    OUTCOMES,
    derive_capability,
    round_floats,
)
from transcribe.persistence.schema import require_format

DETECTION_FORMAT = "transcribe.detection-result"


def build_detection_envelope(
    *,
    notebook_id: str,
    detector_id: str,
    detector_version: str,
    cache_identity: str,
    scope_fingerprint: str,
    attempt_state: str,
    outcome: str,
    findings: list[dict[str, Any]],
    pages_scanned: list[str],
    windows_scanned: int,
    provenance: dict[str, Any] | None = None,
    config_fingerprint: str,
    warnings: list[dict[str, str]] | None = None,
    partial: bool = False,
    capability_reason: str | None = None,
    attempt_id: str | None = None,
    published: bool | None = None,
    prompt_provenance: dict[str, str] | None = None,
    model_provenance: dict[str, Any] | None = None,
    generation_settings: dict[str, Any] | None = None,
    stale_at_publish: bool | None = None,
) -> dict[str, Any]:
    if attempt_state not in ATTEMPT_STATES:
        raise ValueError(f"invalid attempt_state: {attempt_state}")
    if outcome not in OUTCOMES:
        raise ValueError(f"invalid outcome: {outcome}")
    env: dict[str, Any] = {
        "format": DETECTION_FORMAT,
        "schema_version": 1,
        "notebook_id": notebook_id,
        "detector_id": detector_id,
        "detector_version": detector_version,
        "cache_identity": cache_identity,
        "scope_fingerprint": scope_fingerprint,
        "attempt_state": attempt_state,
        "outcome": outcome,
        "capability": derive_capability(outcome=outcome, partial=partial, reason=capability_reason),
        "provenance": {
            **(provenance or {}),
            "detector_version": detector_version,
            "app_version": APP_VERSION,
        },
        "warnings": warnings or [],
        "config_fingerprint": config_fingerprint,
        "findings": round_floats(findings),
        "pages_scanned": pages_scanned,
        "windows_scanned": windows_scanned,
    }
    if partial:
        env["partial"] = True
    if attempt_id is not None:
        env["attempt_id"] = attempt_id
    if published is not None:
        env["published"] = published
    if prompt_provenance is not None:
        env["prompt_provenance"] = prompt_provenance
    if model_provenance is not None:
        env["model_provenance"] = model_provenance
    if generation_settings is not None:
        env["generation_settings"] = generation_settings
    if stale_at_publish:
        env["stale_at_publish"] = True
    return require_format(env, DETECTION_FORMAT)


CACHEABLE_DETECTION_OUTCOMES = CACHEABLE_OUTCOMES
