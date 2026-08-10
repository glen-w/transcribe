"""Detection freshness for UI/API."""

from __future__ import annotations

from typing import Any, Literal

FreshnessStatus = Literal["ok", "stale", "missing", "unavailable"]


def detector_freshness(
    *,
    published: dict[str, Any] | None,
    planned_cache_identity: str,
    detector_version: str,
) -> FreshnessStatus:
    if published is None:
        return "missing"
    if published.get("detector_version") != detector_version:
        return "stale"
    if published.get("cache_identity") != planned_cache_identity:
        return "stale"
    outcome = published.get("outcome")
    if outcome not in ("success", "skipped_not_applicable", "insufficient_data"):
        if outcome == "unavailable_dependency":
            return "unavailable"
        return "stale"
    return "ok"
