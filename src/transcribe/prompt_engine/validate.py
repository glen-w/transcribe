"""Structured response validation for prompt outputs."""

from __future__ import annotations

from typing import Any

_MAX_ITEMS = 40
_MAX_SAMPLE = 12
_MAX_EXCERPT = 500
_MAX_REASON = 2000


def _as_bool(value: Any) -> bool | None:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        lower = value.strip().lower()
        if lower in {"true", "yes", "1"}:
            return True
        if lower in {"false", "no", "0"}:
            return False
    return None


def _as_float(value: Any) -> float | None:
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value.strip())
        except ValueError:
            return None
    return None


def _as_str(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        s = value.strip()
        return s if s else None
    return str(value)


def _as_int(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, str):
        try:
            return int(value.strip())
        except ValueError:
            return None
    return None


def _window_base(obj: dict[str, Any]) -> dict[str, Any] | None:
    detected = _as_bool(obj.get("detected"))
    confidence = _as_float(obj.get("confidence"))
    if detected is None or confidence is None:
        return None
    starts = _as_bool(obj.get("starts_on_this_window"))
    before = _as_bool(obj.get("continues_before"))
    after = _as_bool(obj.get("continues_after"))
    if starts is None or before is None or after is None:
        return None
    return {
        "detected": detected,
        "confidence": max(0.0, min(1.0, confidence)),
        "starts_on_this_window": starts,
        "continues_before": before,
        "continues_after": after,
        "reason": (_as_str(obj.get("reason")) or "")[:_MAX_REASON],
    }


def validate_poetry_window_response_v1(obj: dict[str, Any]) -> dict[str, Any] | None:
    base = _window_base(obj)
    if base is None:
        return None
    boundaries = obj.get("boundaries")
    bnd: dict[str, Any] = {}
    if isinstance(boundaries, dict):
        bnd = {
            "start_page_hint": _as_str(boundaries.get("start_page_hint")),
            "end_page_hint": _as_str(boundaries.get("end_page_hint")),
        }
    return {
        **base,
        "boundaries": bnd,
        "title": _as_str(obj.get("title")),
    }


def validate_custom_finding_v1(obj: dict[str, Any]) -> dict[str, Any] | None:
    return _window_base(obj)


def validate_todo_window_response_v1(obj: dict[str, Any]) -> dict[str, Any] | None:
    base = _window_base(obj)
    if base is None:
        return None
    items_raw = obj.get("items")
    items: list[dict[str, Any]] = []
    if isinstance(items_raw, list):
        for row in items_raw[:_MAX_ITEMS]:
            if not isinstance(row, dict):
                continue
            text = _as_str(row.get("text"))
            if not text:
                continue
            status = (_as_str(row.get("status")) or "unknown").lower()
            if status not in {"open", "done", "unknown"}:
                status = "unknown"
            items.append(
                {
                    "text": text[:500],
                    "status": status,
                    "page_hint": _as_str(row.get("page_hint")),
                }
            )
    style = (_as_str(obj.get("list_style")) or "mixed").lower()
    if style not in {
        "checkbox",
        "todo_keyword",
        "numbered",
        "bulleted_action",
        "mixed",
    }:
        style = "mixed"
    return {**base, "items": items, "list_style": style}


def validate_lists_window_response_v1(obj: dict[str, Any]) -> dict[str, Any] | None:
    base = _window_base(obj)
    if base is None:
        return None
    kind = (_as_str(obj.get("list_kind")) or "other").lower()
    if kind not in {"shopping", "inventory", "outline", "mixed", "other"}:
        kind = "other"
    count = _as_int(obj.get("item_count_estimate"))
    if count is None:
        count = 0
    samples_raw = obj.get("sample_items")
    samples: list[str] = []
    if isinstance(samples_raw, list):
        for s in samples_raw[:_MAX_SAMPLE]:
            t = _as_str(s)
            if t:
                samples.append(t[:300])
    return {
        **base,
        "list_kind": kind,
        "item_count_estimate": max(0, count),
        "sample_items": samples,
    }


def validate_quotations_window_response_v1(obj: dict[str, Any]) -> dict[str, Any] | None:
    base = _window_base(obj)
    if base is None:
        return None
    kind = (_as_str(obj.get("quote_kind")) or "unknown").lower()
    if kind not in {"block", "inline", "epigraph", "dialogue", "unknown"}:
        kind = "unknown"
    excerpt = _as_str(obj.get("excerpt")) or ""
    return {
        **base,
        "quote_kind": kind,
        "attribution": _as_str(obj.get("attribution")),
        "excerpt": excerpt[:_MAX_EXCERPT],
    }


_VALIDATORS: dict[str, Any] = {
    "poetry_window_response_v1": validate_poetry_window_response_v1,
    "custom_finding_v1": validate_custom_finding_v1,
    "todo_window_response_v1": validate_todo_window_response_v1,
    "lists_window_response_v1": validate_lists_window_response_v1,
    "quotations_window_response_v1": validate_quotations_window_response_v1,
}


def validate_response(schema_id: str, obj: dict[str, Any]) -> dict[str, Any] | None:
    if schema_id == "free_text":
        return obj
    fn = _VALIDATORS.get(schema_id)
    if fn is None:
        return None
    return fn(obj)
