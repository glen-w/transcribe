"""notebook_eligibility_v1 — sole core stand-in for TX insight_eligibility."""

from __future__ import annotations

import hashlib
from typing import Any, Iterable

from transcribe.analysis.document import AnalysisUnit
from transcribe.domain.fingerprint import canonical_json_bytes

POLICY_ID = "notebook_eligibility_v1"
POLICY_VERSION = "1"


def evaluate_notebook_eligibility_v1(
    units: Iterable[AnalysisUnit],
    *,
    excluded_page_ids: set[str] | None = None,
) -> dict[str, Any]:
    """Deterministic eligibility decisions (contract notebook-eligibility)."""
    excluded = excluded_page_ids or set()
    decisions: list[dict[str, Any]] = []
    for unit in units:
        page_id = None
        ref = unit.source_ref
        if isinstance(ref, dict) and ref.get("kind") in {"page", "page_span"}:
            page_id = ref.get("page_id")
        if page_id is not None and page_id in excluded:
            decisions.append({"unit_id": unit.unit_id, "eligible": False, "reason": "excluded"})
            continue
        if unit.text == "" or unit.text.strip() == "":
            decisions.append(
                {
                    "unit_id": unit.unit_id,
                    "eligible": False,
                    "reason": "empty_or_whitespace",
                }
            )
            continue
        if len(unit.text.strip()) < 3:
            decisions.append({"unit_id": unit.unit_id, "eligible": False, "reason": "too_short"})
            continue
        decisions.append({"unit_id": unit.unit_id, "eligible": True, "reason": "ok"})

    decisions.sort(key=lambda d: d["unit_id"])
    eligible = sorted(d["unit_id"] for d in decisions if d["eligible"])
    return {
        "policy_id": POLICY_ID,
        "policy_version": POLICY_VERSION,
        "eligible_unit_ids": eligible,
        "decisions": decisions,
    }


def eligibility_fingerprint(output: dict[str, Any]) -> str:
    return hashlib.sha256(canonical_json_bytes(output)).hexdigest()
