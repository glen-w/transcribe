"""Cache identity composition (analysis-run-storage contract)."""

from __future__ import annotations

import hashlib
from typing import Any

from transcribe.analysis import ADAPTER_VERSION, CACHE_IDENTITY_VERSION
from transcribe.analysis.document import (
    CONTENT_FINGERPRINT_VERSION,
    AnalysisDocument,
    content_fingerprint,
)
from transcribe.domain.fingerprint import canonical_json_bytes


def config_fingerprint(config: dict[str, Any] | None) -> str:
    obj = config or {}
    return hashlib.sha256(canonical_json_bytes(obj)).hexdigest()


def build_cache_identity_object(
    *,
    project_id: str,
    module_id: str,
    module_version: str,
    document: AnalysisDocument,
    config: dict[str, Any] | None = None,
    parents: list[dict[str, Any]] | None = None,
    eligibility_policy_id: str | None = None,
    eligibility_policy_version: str | None = None,
    eligibility_fingerprint: str | None = None,
    lexicon_or_model: Any = None,
    resolved_model_digest: str | None = None,
    llm: dict[str, Any] | None = None,
    adapter_version: str = ADAPTER_VERSION,
) -> dict[str, Any]:
    fp = content_fingerprint(document)
    parents_sorted = sorted(parents or [], key=lambda p: (p["module_id"], p["cache_identity"]))
    return {
        "adapter_version": adapter_version,
        "cache_identity_version": CACHE_IDENTITY_VERSION,
        "config_fingerprint": config_fingerprint(config),
        "content_fingerprint": fp,
        "content_fingerprint_version": CONTENT_FINGERPRINT_VERSION,
        "eligibility_fingerprint": eligibility_fingerprint,
        "eligibility_policy_id": eligibility_policy_id,
        "eligibility_policy_version": eligibility_policy_version,
        "granularity_version": document.granularity_version,
        "lexicon_or_model": lexicon_or_model,
        "llm": llm,
        "module_id": module_id,
        "module_version": module_version,
        "parents": parents_sorted,
        "project_id": project_id,
        "resolved_model_digest": resolved_model_digest,
        "split_profile": document.split_profile,
    }


def cache_identity_hex(identity_obj: dict[str, Any]) -> str:
    return hashlib.sha256(canonical_json_bytes(identity_obj)).hexdigest()
