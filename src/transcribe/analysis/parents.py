"""Parent resolution — optional enrichments and hard DAG (analysis-run-storage)."""

from __future__ import annotations

from typing import Any

from transcribe.analysis.storage import AnalysisStorage

# Wave 1.2: wordclouds baseline never consumes keyphrases.
_BASELINE_NEVER_CONSUME = frozenset({"wordclouds"})

# Hard parents: consumer → ordered list of (parent_id, acceptable outcomes)
HARD_PARENTS: dict[str, list[tuple[str, frozenset[str]]]] = {
    "entity_sentiment": [
        ("ner", frozenset({"success"})),
        ("sentiment", frozenset({"success"})),
    ],
    "summary": [("highlights", frozenset({"success"}))],
    "insights": [
        ("highlights", frozenset({"success"})),
        ("topic_modeling", frozenset({"success"})),
    ],
    "narrative_summary": [("summary", frozenset({"success"}))],
}

# Modules that optionally ground on deterministic synthesis when present.
_OPTIONAL_LLM_GROUNDING = frozenset(
    {"llm_summary", "llm_action_items", "llm_custom_qa"}
)


def resolve_optional_parents(
    module_id: str,
    *,
    enrichment_mode: str,
    storage: AnalysisStorage,
) -> list[dict[str, Any]]:
    """Return optional parents actually consumed for identity."""
    if module_id in _BASELINE_NEVER_CONSUME and enrichment_mode == "baseline":
        _ = storage.read_published("keyphrases")
        return []

    consumed: list[dict[str, Any]] = []
    if module_id in _OPTIONAL_LLM_GROUNDING:
        for mid in ("highlights", "summary"):
            pub = storage.read_published(mid)
            if pub and pub.get("outcome") == "success":
                consumed.append(
                    {
                        "module_id": mid,
                        "cache_identity": pub.get("cache_identity"),
                        "outcome": pub.get("outcome"),
                    }
                )
    return consumed


def resolve_hard_parents(
    module_id: str,
    *,
    storage: AnalysisStorage,
) -> tuple[bool, list[dict[str, Any]], dict[str, Any] | None]:
    """Resolve required hard parents.

    Returns ``(ok, parents, failure)`` where ``failure`` is a run-result dict
    suitable for publishing ``unavailable_dependency`` when ``ok`` is False.
    """
    specs = HARD_PARENTS.get(module_id)
    if not specs:
        return True, [], None

    parents: list[dict[str, Any]] = []
    missing: list[str] = []
    for parent_id, acceptable in specs:
        pub = storage.read_published(parent_id)
        if pub is None or pub.get("outcome") not in acceptable:
            missing.append(parent_id)
            continue
        parents.append(
            {
                "module_id": parent_id,
                "cache_identity": pub.get("cache_identity"),
                "outcome": pub.get("outcome"),
            }
        )
    if missing:
        return (
            False,
            [],
            {
                "outcome": "unavailable_dependency",
                "payload": {
                    "error": {
                        "code": "unavailable_dependency",
                        "message": f"missing hard parents: {', '.join(missing)}",
                        "missing_parents": missing,
                    }
                },
                "warnings": [
                    {
                        "code": "unavailable_dependency",
                        "message": f"missing hard parents: {', '.join(missing)}",
                    }
                ],
                "capability_reason": "unavailable_dependency",
            },
        )
    return True, parents, None


def parent_payloads(storage: AnalysisStorage, parents: list[dict[str, Any]]) -> dict[str, Any]:
    """Map parent module_id → published payload (empty dict if missing)."""
    out: dict[str, Any] = {}
    for row in parents:
        mid = row["module_id"]
        pub = storage.read_published(mid)
        out[mid] = (pub or {}).get("payload") or {}
    return out


def batch_module_order(module_ids: list[str]) -> list[str]:
    """Topological-ish order so hard parents run before consumers."""
    rank = {
        "stats": 10,
        "lexical_diversity": 11,
        "understandability": 12,
        "wordclouds": 20,
        "ner": 30,
        "sentiment": 31,
        "epistemic_markers": 32,
        "keyphrases": 40,
        "entity_sentiment": 41,
        "topic_modeling": 50,
        "highlights": 60,
        "summary": 61,
        "insights": 62,
        "llm_summary": 70,
        "llm_action_items": 71,
        "llm_custom_qa": 72,
        "narrative_summary": 73,
    }
    return sorted(module_ids, key=lambda m: (rank.get(m, 1000), m))
