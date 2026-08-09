"""Structural input fingerprint for OCR skip/resume."""

from __future__ import annotations

import hashlib
import json
from typing import Any


def canonical_json_bytes(obj: dict[str, Any]) -> bytes:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode(
        "utf-8"
    )


def compute_input_fingerprint(
    *,
    provider: str,
    model_name: str,
    model_digest: str | None,
    model_identity_verified: bool,
    input_sha256: str,
    prompt_sha256: str,
    preprocess_profile: str,
    preprocess_version: int,
    generation_options: dict[str, Any],
    cleanup: dict[str, Any] | None = None,
) -> tuple[str, dict[str, Any]]:
    """Return (hex digest, canonical fingerprint object).

    When cleanup is enabled, pass a dict with frozen cleanup identity fields.
    When disabled, omit ``cleanup`` (None) so fingerprints stay compatible with
    pre-cleanup attempts.
    """
    payload: dict[str, Any] = {
        "provider": provider,
        "model_name": model_name,
        "model_digest": model_digest,
        "model_identity_verified": model_identity_verified,
        "input_sha256": input_sha256,
        "prompt_sha256": prompt_sha256,
        "preprocess": {"profile": preprocess_profile, "version": preprocess_version},
        "generation_options": generation_options,
    }
    if cleanup is not None:
        payload["cleanup"] = cleanup
    digest = hashlib.sha256(canonical_json_bytes(payload)).hexdigest()
    return digest, payload


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_text(text: str) -> str:
    return sha256_bytes(text.encode("utf-8"))
