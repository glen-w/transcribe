"""Quarantine malformed durable journals (do not silently delete)."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path


def quarantine_path(path: Path, *, reason: str = "corrupt") -> Path:
    """Rename ``path`` beside itself with a corrupt suffix; return destination.

    If rename fails, best-effort copy-then-unlink is not used — raise so callers
    surface the failure rather than discarding evidence.
    """
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(path)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    safe_reason = "".join(c if c.isalnum() or c in "-_" else "_" for c in reason)[:48]
    dest = path.with_name(f"{path.name}.{safe_reason}.{stamp}")
    path.rename(dest)
    return dest
