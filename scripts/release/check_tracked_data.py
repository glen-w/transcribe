#!/usr/bin/env python3
"""Assert git-tracked data-like files match scripts/release/tracked_data_allowlist.toml.

Covers:
  * repo-root ``data/**`` (should stay empty / gitignored for user workspaces)
  * tracked binaries (png/jpg/jpeg/pdf/zip and similar)
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

try:
    import tomllib
except ModuleNotFoundError:  # Python < 3.11
    import tomli as tomllib  # type: ignore


ROOT = Path(__file__).resolve().parents[2]
ALLOWLIST = Path(__file__).resolve().parent / "tracked_data_allowlist.toml"

BINARY_SUFFIXES = (
    ".png",
    ".jpg",
    ".jpeg",
    ".gif",
    ".webp",
    ".pdf",
    ".zip",
    ".sqlite",
    ".db",
    ".wav",
    ".mp3",
    ".gguf",
    ".onnx",
    ".safetensors",
)


def _load_allowlist() -> set[str]:
    data = tomllib.loads(ALLOWLIST.read_text(encoding="utf-8"))
    paths = data.get("paths") or []
    out: set[str] = set()
    for entry in paths:
        path = str(entry.get("path") or "").strip()
        if not path:
            raise SystemExit(f"allowlist entry missing path: {entry!r}")
        if not entry.get("owner") or not entry.get("purpose"):
            raise SystemExit(f"allowlist entry missing owner/purpose: {path}")
        out.add(path)
    return out


def _git_ls(*pathspecs: str) -> set[str]:
    proc = subprocess.run(
        ["git", "ls-files", "-z", "--", *pathspecs],
        cwd=ROOT,
        check=True,
        capture_output=True,
    )
    raw = proc.stdout.decode("utf-8")
    if not raw:
        return set()
    return {p for p in raw.split("\0") if p}


def _tracked_data_like() -> set[str]:
    tracked = _git_ls("data")
    all_files = _git_ls(".")
    for path in all_files:
        lower = path.lower()
        if any(lower.endswith(suf) for suf in BINARY_SUFFIXES):
            tracked.add(path)
    return tracked


def main() -> int:
    allowed = _load_allowlist()
    tracked = _tracked_data_like()
    extra = sorted(tracked - allowed)
    missing = sorted(allowed - tracked)
    if extra or missing:
        if extra:
            print("ERROR: tracked data/binary paths not on allowlist:")
            for p in extra:
                print(f"  {p}")
        if missing:
            print("ERROR: allowlisted paths not tracked:")
            for p in missing:
                print(f"  {p}")
        print("Update scripts/release/tracked_data_allowlist.toml with owner + purpose.")
        return 1
    print(f"OK: tracked data/binary allowlist ({len(allowed)} path(s))")
    return 0


if __name__ == "__main__":
    sys.exit(main())
