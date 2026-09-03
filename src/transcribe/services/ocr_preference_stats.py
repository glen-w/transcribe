"""Workspace OCR preference ledger and rollup stats."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from transcribe.persistence.atomic import read_json, write_json_atomic
from transcribe.ports import Clock, SystemClock, to_iso
from transcribe.runtime_paths import build_runtime_paths

LEDGER_FORMAT = "transcribe.ocr-preference-ledger"
LEDGER_SCHEMA_VERSION = 1
LEDGER_FILENAME = "ocr_preference_ledger.json"

PREFERENCE_ACTIONS = frozenset({"prefer", "promote", "auto_composite"})


@dataclass
class PreferenceEvent:
    ts: str
    notebook_id: str
    page_id: str
    attempt_id: str
    model_name: str
    model_digest: str | None
    attempt_kind: str
    action: str
    pass_id: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "ts": self.ts,
            "notebook_id": self.notebook_id,
            "page_id": self.page_id,
            "attempt_id": self.attempt_id,
            "model_name": self.model_name,
            "model_digest": self.model_digest,
            "attempt_kind": self.attempt_kind,
            "action": self.action,
            "pass_id": self.pass_id,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> PreferenceEvent:
        return cls(
            ts=str(data.get("ts") or ""),
            notebook_id=str(data.get("notebook_id") or ""),
            page_id=str(data.get("page_id") or ""),
            attempt_id=str(data.get("attempt_id") or ""),
            model_name=str(data.get("model_name") or ""),
            model_digest=data.get("model_digest"),
            attempt_kind=str(data.get("attempt_kind") or "vision"),
            action=str(data.get("action") or "prefer"),
            pass_id=data.get("pass_id"),
        )


@dataclass
class ModelPreferenceStats:
    model_name: str
    prefer_count: int = 0
    promote_count: int = 0
    composite_prefer_count: int = 0
    pages: set[str] = field(default_factory=set)
    last_ts: str | None = None
    digests: set[str] = field(default_factory=set)

    @property
    def pages_covered(self) -> int:
        return len(self.pages)

    def as_dict(self) -> dict[str, Any]:
        return {
            "model_name": self.model_name,
            "prefer_count": self.prefer_count,
            "promote_count": self.promote_count,
            "composite_prefer_count": self.composite_prefer_count,
            "pages_covered": self.pages_covered,
            "last_ts": self.last_ts,
            "digests": sorted(self.digests),
        }


def ledger_path(data_dir: Path | None = None) -> Path:
    root = data_dir or build_runtime_paths().data_dir
    return Path(root) / LEDGER_FILENAME


def load_ledger(path: Path | None = None) -> list[PreferenceEvent]:
    target = path or ledger_path()
    if not target.exists():
        return []
    try:
        payload = read_json(target)
    except Exception:
        return []
    if not isinstance(payload, dict):
        return []
    events = payload.get("events") or []
    out: list[PreferenceEvent] = []
    for raw in events:
        if isinstance(raw, dict):
            out.append(PreferenceEvent.from_dict(raw))
    return out


def save_ledger(events: list[PreferenceEvent], path: Path | None = None) -> None:
    target = path or ledger_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    write_json_atomic(
        target,
        {
            "format": LEDGER_FORMAT,
            "schema_version": LEDGER_SCHEMA_VERSION,
            "events": [e.as_dict() for e in events],
        },
    )


def append_preference_event(
    *,
    notebook_id: str,
    page_id: str,
    attempt_id: str,
    model_name: str,
    model_digest: str | None,
    attempt_kind: str,
    action: str,
    pass_id: str | None = None,
    clock: Clock | None = None,
    path: Path | None = None,
) -> PreferenceEvent:
    if action not in PREFERENCE_ACTIONS:
        action = "prefer"
    clk = clock or SystemClock()
    event = PreferenceEvent(
        ts=to_iso(clk.now()),
        notebook_id=notebook_id,
        page_id=page_id,
        attempt_id=attempt_id,
        model_name=model_name,
        model_digest=model_digest,
        attempt_kind=attempt_kind,
        action=action,
        pass_id=pass_id,
    )
    target = path or ledger_path()
    events = load_ledger(target)
    events.append(event)
    save_ledger(events, target)
    return event


def rollup_preference_stats(
    events: list[PreferenceEvent] | None = None,
    *,
    path: Path | None = None,
) -> dict[str, ModelPreferenceStats]:
    rows = events if events is not None else load_ledger(path)
    by_model: dict[str, ModelPreferenceStats] = {}
    for event in rows:
        key = event.model_name or "(unknown)"
        stats = by_model.get(key)
        if stats is None:
            stats = ModelPreferenceStats(model_name=key)
            by_model[key] = stats
        page_key = f"{event.notebook_id}:{event.page_id}"
        if event.action == "prefer":
            stats.prefer_count += 1
            if event.attempt_kind == "composite":
                stats.composite_prefer_count += 1
        elif event.action == "promote":
            stats.promote_count += 1
        elif event.action == "auto_composite":
            stats.prefer_count += 1
            stats.composite_prefer_count += 1
        stats.pages.add(page_key)
        if event.model_digest:
            stats.digests.add(event.model_digest)
        if not stats.last_ts or event.ts >= stats.last_ts:
            stats.last_ts = event.ts
    return by_model


def _choice_weight(stats: ModelPreferenceStats) -> int:
    """Ledger events that reflect picking a model (prefer, promote, composite)."""
    return stats.prefer_count + stats.promote_count


MODEL_PREFERENCE_HINT_MODES = frozenset({"off", "prefer_only", "all_choices"})
DEFAULT_MODEL_PREFERENCE_HINT_MODE = "all_choices"


def resolve_model_preference_hint_mode(raw: str | None) -> str:
    key = str(raw or DEFAULT_MODEL_PREFERENCE_HINT_MODE).strip()
    if key not in MODEL_PREFERENCE_HINT_MODES:
        return DEFAULT_MODEL_PREFERENCE_HINT_MODE
    return key


def effective_model_preference_hint_mode() -> str:
    from transcribe.config import get_config

    return resolve_model_preference_hint_mode(
        get_config().effective.ui.model_preference_hints
    )


def _prefer_weight(stats: ModelPreferenceStats) -> int:
    return stats.prefer_count


def _weight_for_share_mode(stats: ModelPreferenceStats, share_mode: str) -> int:
    if share_mode == "prefer_only":
        return _prefer_weight(stats)
    return _choice_weight(stats)


def preference_hint_for_model(
    model_name: str,
    *,
    stats: dict[str, ModelPreferenceStats] | None = None,
    share_mode: str | None = None,
) -> str | None:
    mode = resolve_model_preference_hint_mode(
        share_mode if share_mode is not None else DEFAULT_MODEL_PREFERENCE_HINT_MODE
    )
    if mode == "off":
        return None
    table = stats if stats is not None else rollup_preference_stats()
    row = table.get(model_name)
    if row is None or _weight_for_share_mode(row, mode) == 0:
        return None
    total_choices = sum(_weight_for_share_mode(s, mode) for s in table.values()) or 1
    pct = int(round(100.0 * _weight_for_share_mode(row, mode) / total_choices))
    parts = [
        f"Preferred on {row.pages_covered} pages · {pct}% of your prefers",
    ]
    if row.last_ts:
        day = row.last_ts[:10]
        parts.append(f"last preference {day}")
    return " · ".join(parts)
