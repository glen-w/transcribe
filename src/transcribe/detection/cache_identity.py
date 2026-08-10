"""Detection cache identity composition."""

from __future__ import annotations

import hashlib
from typing import Any

from transcribe.analysis.cache_identity import config_fingerprint
from transcribe.detection.definition import DetectorDefinition
from transcribe.detection.inputs import PageInput, scope_fingerprint
from transcribe.domain.fingerprint import canonical_json_bytes

CACHE_IDENTITY_VERSION = 1


def build_cache_identity_object(
    *,
    notebook_id: str,
    detector: DetectorDefinition,
    prompt_id: str,
    prompt_version: str,
    page_inputs: list[PageInput],
    model_digest: str | None,
    generation_settings: dict[str, Any],
) -> dict[str, Any]:
    return {
        "cache_identity_version": CACHE_IDENTITY_VERSION,
        "notebook_id": notebook_id,
        "detector_id": detector.detector_id,
        "detector_version": detector.version,
        "prompt_id": prompt_id,
        "prompt_version": prompt_version,
        "config_fingerprint": config_fingerprint(detector.cache_config()),
        "model_digest": model_digest,
        "scope_fingerprint": scope_fingerprint(page_inputs),
        "generation_settings": generation_settings,
    }


def cache_identity_hex(identity_obj: dict[str, Any]) -> str:
    return hashlib.sha256(canonical_json_bytes(identity_obj)).hexdigest()
