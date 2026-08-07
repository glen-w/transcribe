"""Tiny injectable ports for deterministic tests."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Protocol


class Clock(Protocol):
    def now(self) -> datetime: ...


class IdGenerator(Protocol):
    def new_id(self) -> str: ...


class SystemClock:
    def now(self) -> datetime:
        return datetime.now(timezone.utc)


class UuidGenerator:
    def new_id(self) -> str:
        return uuid.uuid4().hex


def to_iso(dt: datetime) -> str:
    """Canonical ISO-8601 UTC with Z suffix."""
    if dt.tzinfo is None:
        raise ValueError("naive datetime rejected; use timezone-aware UTC")
    utc = dt.astimezone(timezone.utc)
    return utc.strftime("%Y-%m-%dT%H:%M:%S.") + f"{utc.microsecond:06d}"[:-3] + "Z"


def parse_iso(value: str) -> datetime:
    text = value.strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    dt = datetime.fromisoformat(text)
    if dt.tzinfo is None:
        raise ValueError(f"naive timestamp rejected: {value!r}")
    return dt.astimezone(timezone.utc)
