"""Parent resolution — optional enrichments and hard DAG (analysis-run-storage)."""

from __future__ import annotations

from typing import Any

from transcribe.analysis.storage import AnalysisStorage

_BASELINE_NEVER_CONSUME = frozenset({"wordclouds", "topic_modeling", "bertopic"})

HARD_PARENTS: dict[str, list[tuple[str, frozenset[str]]]] = {
    "entity_sentiment": [
        ("ner", frozenset({"success"})),
        ("sentiment", frozenset({"success"})),
    ],
    "affect_tension": [
        ("emotion", frozenset({"success"})),
        ("sentiment", frozenset({"success"})),
    ],
    "summary": [("highlights", frozenset({"success"}))],
    "insights": [
        ("highlights", frozenset({"success"})),
        ("topic_modeling", frozenset({"success"})),
    ],
    "narrative_summary": [("summary", frozenset({"success"}))],
}


def _snapshot_row(parent_id: str, pub: dict[str, Any]) -> dict[str, Any]:
    """Identity + payload together from a single published read."""
    return {
        "module_id": parent_id,
        "cache_identity": pub.get("cache_identity"),
        "outcome": pub.get("outcome"),
        "payload": pub.get("payload") or {},
    }


def parents_for_identity(parents: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Strip payloads before hashing into cache identity."""
    return [
        {
            "module_id": p["module_id"],
            "cache_identity": p.get("cache_identity"),
            "outcome": p.get("outcome"),
        }
        for p in parents
    ]


def resolve_optional_parents(
    module_id: str,
    *,
    enrichment_mode: str,
    storage: AnalysisStorage,
) -> list[dict[str, Any]]:
    """Return optional parents actually consumed for identity + compute."""
    if module_id in _BASELINE_NEVER_CONSUME and enrichment_mode in {
        "baseline",
        "none",
    }:
        if module_id in {"wordclouds", "topic_modeling", "bertopic"}:
            _ = storage.read_published("keyphrases")
        return []

    consumed: list[dict[str, Any]] = []
    # LLM modules ground on document / hard parents only — do not record unused soft parents.
    if module_id == "moments":
        for mid in ("emotion", "sentiment", "topic_shift"):
            pub = storage.read_published(mid)
            if pub and pub.get("outcome") == "success":
                consumed.append(_snapshot_row(mid, pub))
    return consumed


def resolve_hard_parents(
    module_id: str,
    *,
    storage: AnalysisStorage,
) -> tuple[bool, list[dict[str, Any]], dict[str, Any] | None]:
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
        parents.append(_snapshot_row(parent_id, pub))
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


def parent_payloads(parents: list[dict[str, Any]]) -> dict[str, Any]:
    """Map parent module_id → snapshot payload (no second published read)."""
    return {row["module_id"]: row.get("payload") or {} for row in parents}


def batch_module_order(module_ids: list[str]) -> list[str]:
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
        "semantic_similarity": 51,
        "topic_shift": 52,
        "bertopic": 53,
        "emotion": 54,
        "contextual_emotion": 55,
        "fine_grained_emotion": 56,
        "affect_tension": 57,
        "moments": 58,
        "highlights": 60,
        "summary": 61,
        "insights": 62,
        "llm_summary": 70,
        "llm_action_items": 71,
        "llm_custom_qa": 72,
        "narrative_summary": 73,
    }
    return sorted(module_ids, key=lambda m: (rank.get(m, 1000), m))
