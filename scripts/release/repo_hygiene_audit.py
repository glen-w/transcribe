#!/usr/bin/env python3
"""Repository hygiene audit — reporting mode by default.

Checks (warn by default; exit 0 unless --strict):
  1. root_md — Root markdown allowlist (scripts/release/root_docs_allowlist.toml)
  2. owner_paths — Owner absolute paths (/Users/...) in tracked scripts/docs
  3. archive_banners — Archive banners under docs/archive/
  4. type_headers — Live docs under docs/ (excl. archive) missing Type: header
  5. dated_dev_index — Dated docs/dev/*_20*.md not mentioned in docs/DEV_INDEX.md
  6. supported_scripts — Supported public scripts mentioned in user-facing docs

Usage:
  python scripts/release/repo_hygiene_audit.py
  python scripts/release/repo_hygiene_audit.py --strict
  python scripts/release/repo_hygiene_audit.py --strict --checks root_md,archive_banners
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path

try:
    import tomllib
except ModuleNotFoundError:  # Python < 3.11
    import tomli as tomllib  # type: ignore


ROOT = Path(__file__).resolve().parents[2]
ALLOWLIST = Path(__file__).resolve().parent / "root_docs_allowlist.toml"
DEV_INDEX = ROOT / "docs" / "DEV_INDEX.md"
SUPPORTED_SCRIPT_NEEDLES = (
    "transcribe.sh",
    "python -m transcribe",
)
USER_DOC_GLOBS = (
    "README.md",
    "docs/USER_INDEX.md",
    "docs/runtime/*.md",
    "docs/public_surfaces.md",
)


def _tracked(patterns: list[str]) -> list[str]:
    proc = subprocess.run(
        ["git", "ls-files", "-z", "--", *patterns],
        cwd=ROOT,
        check=True,
        capture_output=True,
    )
    raw = proc.stdout.decode("utf-8")
    if not raw:
        return []
    return [p for p in raw.split("\0") if p]


def _load_root_allowlist() -> set[str]:
    data = tomllib.loads(ALLOWLIST.read_text(encoding="utf-8"))
    out: set[str] = set()
    for entry in data.get("paths") or []:
        path = str(entry.get("path") or "").strip()
        if not path:
            raise SystemExit(f"root docs allowlist entry missing path: {entry!r}")
        out.add(path)
    return out


def check_root_md() -> list[str]:
    allowed = _load_root_allowlist()
    tracked = {p for p in _tracked(["*.md"]) if "/" not in p}
    extra = sorted(tracked - allowed)
    missing = sorted(allowed - tracked)
    warns: list[str] = []
    for p in extra:
        warns.append(f"root markdown not on allowlist: {p}")
    for p in missing:
        warns.append(f"allowlisted root markdown missing: {p}")
    return warns


def check_owner_paths() -> list[str]:
    warns: list[str] = []
    paths = _tracked(
        [
            "scripts/**",
            "docs/**",
            "README.md",
            "CONTRIBUTING.md",
            ".cursor/commands/**",
        ]
    )
    pat = re.compile(r"/Users/[A-Za-z0-9._-]+(?:/[^\s'\"`)\]|,]*)?")
    skip_self = "scripts/release/repo_hygiene_audit.py"
    for rel in paths:
        if rel == skip_self:
            continue
        path = ROOT / rel
        if not path.is_file():
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        hits = pat.findall(text)
        if not hits:
            continue
        real = [
            h
            for h in hits
            if not h.startswith("/Users/you")
            and "USERNAME" not in h
            and not h.rstrip("/").endswith("/...")
        ]
        if not real:
            continue
        level = "archive" if rel.startswith("docs/archive/") else "live"
        warns.append(
            f"{level} absolute path(s) in {rel}: {', '.join(sorted(set(real))[:3])}"
        )
    return warns


def check_archive_banners() -> list[str]:
    warns: list[str] = []
    docs = _tracked(["docs/archive/**/*.md"])
    for rel in docs:
        if rel.endswith("README.md") or rel.endswith("ARCHIVE_INDEX.md"):
            continue
        path = ROOT / rel
        if not path.is_file():
            continue
        text = path.read_text(encoding="utf-8", errors="replace")[:800]
        if "Archived / superseded" not in text and "[ARCHIVED]" not in text:
            warns.append(f"docs archive missing banner: {rel}")
    return warns


def check_type_headers() -> list[str]:
    warns: list[str] = []
    for rel in _tracked(["docs/**/*.md"]):
        if rel.startswith("docs/archive/"):
            continue
        path = ROOT / rel
        if not path.is_file():
            continue
        text = path.read_text(encoding="utf-8", errors="replace")[:400]
        if not re.search(r"^Type:\s*\S+", text, re.M):
            warns.append(f"live doc missing Type: header: {rel}")
    return warns


def check_dated_dev_index() -> list[str]:
    warns: list[str] = []
    if not DEV_INDEX.exists():
        return ["docs/DEV_INDEX.md missing"]
    index_text = DEV_INDEX.read_text(encoding="utf-8")
    for rel in _tracked(["docs/dev/*_20*.md"]):
        name = Path(rel).name
        if name not in index_text and rel not in index_text:
            warns.append(f"dated dev doc not listed in DEV_INDEX.md: {rel}")
    return warns


def check_supported_scripts_documented() -> list[str]:
    warns: list[str] = []
    blobs: list[str] = []
    for pattern in USER_DOC_GLOBS:
        for rel in _tracked([pattern]):
            blobs.append((ROOT / rel).read_text(encoding="utf-8", errors="replace"))
    joined = "\n".join(blobs)
    for needle in SUPPORTED_SCRIPT_NEEDLES:
        if needle not in joined:
            warns.append(f"supported script/needle not found in user docs: {needle}")
    return warns


CHECKS: dict[str, Callable[[], list[str]]] = {
    "root_md": check_root_md,
    "owner_paths": check_owner_paths,
    "archive_banners": check_archive_banners,
    "type_headers": check_type_headers,
    "dated_dev_index": check_dated_dev_index,
    "supported_scripts": check_supported_scripts_documented,
}

CHECK_TITLES = {
    "root_md": "root markdown allowlist",
    "owner_paths": "owner absolute paths",
    "archive_banners": "archive banners",
    "type_headers": "Type: headers",
    "dated_dev_index": "dated plans in DEV_INDEX",
    "supported_scripts": "supported scripts in user docs",
}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Exit non-zero when any selected warning is present (default: report-only).",
    )
    parser.add_argument(
        "--checks",
        default="",
        help=(
            "Comma-separated check ids to run "
            f"(default: all). Known: {','.join(CHECKS)}"
        ),
    )
    args = parser.parse_args()

    if args.checks.strip():
        selected = [c.strip() for c in args.checks.split(",") if c.strip()]
        unknown = [c for c in selected if c not in CHECKS]
        if unknown:
            raise SystemExit(f"unknown --checks id(s): {', '.join(unknown)}")
    else:
        selected = list(CHECKS)

    sections: list[tuple[str, list[str]]] = [
        (CHECK_TITLES[cid], CHECKS[cid]()) for cid in selected
    ]

    total = 0
    for title, warns in sections:
        print(f"## {title}")
        if not warns:
            print("OK")
        else:
            for w in warns:
                print(f"WARN: {w}")
            total += len(warns)
        print()

    print(f"Summary: {total} warning(s)")
    if args.strict and total:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
