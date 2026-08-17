#!/usr/bin/env python3
"""Enforce scripts/release/path_denylist.toml (tracked / untracked / ignored / secrets)."""

from __future__ import annotations

import fnmatch
import os
import subprocess
import sys
from pathlib import Path

try:
    import tomllib
except ModuleNotFoundError:  # Python < 3.11
    import tomli as tomllib  # type: ignore


ROOT = Path(__file__).resolve().parents[2]
DENYLIST = Path(__file__).resolve().parent / "path_denylist.toml"


def _load() -> dict:
    return tomllib.loads(DENYLIST.read_text(encoding="utf-8"))


def _git(*args: str) -> str:
    proc = subprocess.run(
        ["git", *args],
        cwd=ROOT,
        check=True,
        capture_output=True,
    )
    return proc.stdout.decode("utf-8")


def _matches(path: str, globs: list[str]) -> bool:
    posix = path.replace("\\", "/")
    return any(fnmatch.fnmatch(posix, g) for g in globs)


def _tracked_files() -> list[str]:
    raw = _git("ls-files", "-z")
    return [p for p in raw.split("\0") if p]


def _check_tracked_forbidden(globs: list[str]) -> list[str]:
    hits = []
    for path in _tracked_files():
        if _matches(path, globs):
            hits.append(path)
    return hits


def _check_untracked_forbidden(globs: list[str]) -> list[str]:
    hits: list[str] = []
    for glob in globs:
        if "*" in glob or "?" in glob or "[" in glob:
            continue
        candidate = ROOT / glob
        if not candidate.exists():
            continue
        proc = subprocess.run(
            ["git", "check-ignore", "-q", glob],
            cwd=ROOT,
        )
        if proc.returncode != 0:
            hits.append(glob)
    status = _git("status", "--porcelain=v1", "--untracked-files=all")
    for line in status.splitlines():
        if not line.startswith("??"):
            continue
        path = line[3:]
        if path and _matches(path, globs):
            hits.append(path)
    seen: set[str] = set()
    out: list[str] = []
    for h in hits:
        if h not in seen:
            seen.add(h)
            out.append(h)
    return out


def _check_ignored_forbidden(globs: list[str]) -> list[str]:
    hits: list[str] = []
    for glob in globs:
        prefix = glob.split("*", 1)[0].rstrip("/")
        base = ROOT / prefix if prefix else ROOT
        if not base.exists():
            continue
        if base.is_file():
            rel = str(base.relative_to(ROOT)).replace("\\", "/")
            if _matches(rel, globs):
                hits.append(rel)
            continue
        for path in base.rglob("*"):
            if not path.is_file():
                continue
            rel = str(path.relative_to(ROOT)).replace("\\", "/")
            if _matches(rel, globs):
                hits.append(rel)
    return hits


def _check_secrets(patterns: list[str]) -> list[str]:
    hits: list[str] = []
    for pattern in patterns:
        proc = subprocess.run(
            ["git", "grep", "-n", "-E", "-I", pattern],
            cwd=ROOT,
            capture_output=True,
        )
        text = proc.stdout.decode("utf-8").strip()
        if text:
            hits.append(f"pattern {pattern!r}:\n{text}")
    return hits


def main() -> int:
    data = _load()
    fail = 0

    tracked_globs = list((data.get("tracked_forbidden") or {}).get("globs") or [])
    tracked_hits = _check_tracked_forbidden(tracked_globs)
    if tracked_hits:
        fail = 1
        print("ERROR: forbidden tracked paths:")
        for p in tracked_hits:
            print(f"  {p}")

    untracked_globs = list((data.get("untracked_forbidden") or {}).get("globs") or [])
    untracked_hits = _check_untracked_forbidden(untracked_globs)
    if untracked_hits:
        fail = 1
        print("ERROR: forbidden untracked / on-disk paths:")
        for p in untracked_hits:
            print(f"  {p}")

    ignored_globs = list((data.get("ignored_forbidden") or {}).get("globs") or [])
    ignored_hits = _check_ignored_forbidden(ignored_globs)
    if ignored_hits:
        if os.environ.get("TRANSCRIBE_STRICT_IGNORED_FORBIDDEN", "0") == "1":
            fail = 1
            print("ERROR: ignored forbidden paths present:")
            for p in ignored_hits:
                print(f"  {p}")
        else:
            print(
                "WARNING: ignored forbidden paths present "
                f"({len(ignored_hits)}); set TRANSCRIBE_STRICT_IGNORED_FORBIDDEN=1 to fail"
            )

    secret_patterns = list((data.get("secret_patterns") or {}).get("patterns") or [])
    secret_hits = _check_secrets(secret_patterns)
    if secret_hits:
        fail = 1
        print("ERROR: secret pattern hits in tracked files:")
        for block in secret_hits:
            print(block)

    if fail:
        return 1
    print("OK: denylist checks passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
