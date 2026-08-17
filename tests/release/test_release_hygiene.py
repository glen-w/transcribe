"""Run I2 hygiene scripts (offline; no Docker required)."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def _run(args: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        args,
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )


def test_tracked_data_allowlist_clean():
    proc = _run([sys.executable, "scripts/release/check_tracked_data.py"])
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "OK:" in proc.stdout


def test_denylist_clean():
    proc = _run([sys.executable, "scripts/release/check_denylist.py"])
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "OK:" in proc.stdout


def test_repo_hygiene_strict_subset_clean():
    proc = _run(
        [
            sys.executable,
            "scripts/release/repo_hygiene_audit.py",
            "--strict",
            "--checks",
            "root_md,archive_banners",
        ]
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "Summary: 0 warning(s)" in proc.stdout


def test_stale_refs_clean():
    proc = _run(["bash", "scripts/release/stale_refs.sh"])
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "OK: stale-ref sweep passed" in proc.stdout


def test_secrets_check_clean():
    proc = _run(["bash", "scripts/secrets_check.sh"])
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "OK: secrets_check" in proc.stdout


def test_compose_bind_static_ok():
    proc = _run(["bash", "scripts/release/assert_compose_bind.sh"])
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "127.0.0.1" in proc.stdout
