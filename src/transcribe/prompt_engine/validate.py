"""Structured response validation for prompt outputs."""

from __future__ import annotations

from typing import Any


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


def validate_poetry_window_response_v1(obj: dict[str, Any]) -> dict[str, Any] | None:
    detected = _as_bool(obj.get("detected"))
    confidence = _as_float(obj.get("confidence"))
    if detected is None or confidence is None:
        return None
    starts = _as_bool(obj.get("starts_on_this_window"))
    before = _as_bool(obj.get("continues_before"))
    after = _as_bool(obj.get("continues_after"))
    if starts is None or before is None or after is None:
        return None
    boundaries = obj.get("boundaries")
    bnd: dict[str, Any] = {}
    if isinstance(boundaries, dict):
        bnd = {
            "start_page_hint": _as_str(boundaries.get("start_page_hint")),
            "end_page_hint": _as_str(boundaries.get("end_page_hint")),
        }
    return {
        "detected": detected,
        "confidence": max(0.0, min(1.0, confidence)),
        "starts_on_this_window": starts,
        "continues_before": before,
        "continues_after": after,
        "boundaries": bnd,
        "title": _as_str(obj.get("title")),
        "reason": _as_str(obj.get("reason")) or "",
    }


def validate_custom_finding_v1(obj: dict[str, Any]) -> dict[str, Any] | None:
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
        "reason": _as_str(obj.get("reason")) or "",
    }


_VALIDATORS: dict[str, Any] = {
    "poetry_window_response_v1": validate_poetry_window_response_v1,
    "custom_finding_v1": validate_custom_finding_v1,
}


def validate_response(schema_id: str, obj: dict[str, Any]) -> dict[str, Any] | None:
    fn = _VALIDATORS.get(schema_id)
    if fn is None:
        return None
    return fn(obj)
