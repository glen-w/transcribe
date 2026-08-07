from __future__ import annotations

from datetime import datetime, timedelta, timezone

from transcribe.ports import IdGenerator


class FakeClock:
    def __init__(self, start: datetime | None = None) -> None:
        self._now = start or datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)

    def now(self) -> datetime:
        current = self._now
        self._now = self._now + timedelta(seconds=1)
        return current

    def set(self, dt: datetime) -> None:
        self._now = dt


class SequentialIds:
    def __init__(self, prefix: str = "id") -> None:
        self._n = 0
        self.prefix = prefix

    def new_id(self) -> str:
        self._n += 1
        return f"{self.prefix}{self._n:04d}"


# Protocol satisfaction (documentation for type checkers)
_: type[IdGenerator] = SequentialIds
