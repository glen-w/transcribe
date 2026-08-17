"""Offline checks that maintainer lanes (I0–I3) stay wired."""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_makefile_exposes_named_lanes():
    text = (ROOT / "Makefile").read_text(encoding="utf-8")
    for target in (
        "help",
        "lint",
        "test-smoke",
        "test-fast",
        "test-contracts",
        "test-acceptance",
        "test-coverage",
        "docker-smoke",
        "docs",
        "docs-clean",
        "release-hygiene",
    ):
        assert re.search(rf"^{re.escape(target)}:", text, re.M), f"Makefile missing {target}"


def test_tests_readme_documents_markers_and_makefile():
    text = (ROOT / "tests" / "README.md").read_text(encoding="utf-8")
    assert "make test-smoke" in text
    assert "make test-fast" in text
    assert "`integration`" in text or "integration" in text
    assert "requires_ollama" in text
    assert "offline" in text.lower()


def test_ci_workflow_runs_python_matrix_and_compose():
    text = (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    assert "cancel-in-progress: true" in text
    for version in ("3.10", "3.11", "3.12"):
        assert version in text
    assert "make test-smoke" in text
    assert "make test-fast" in text
    assert "make test-coverage" in text
    assert "assert_compose_bind.sh" in text
    assert "ruff check src/transcribe" in text
    assert "release-checks:" in text
    assert "check_tracked_data.py" in text
    assert "secrets_check.sh" in text


def test_package_version_matches_pyproject():
    init_text = (ROOT / "src" / "transcribe" / "__init__.py").read_text(encoding="utf-8")
    pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    init_ver = re.search(r'__version__\s*=\s*"([^"]+)"', init_text)
    proj_ver = re.search(r'^version\s*=\s*"([^"]+)"', pyproject, re.M)
    assert init_ver and proj_ver
    assert init_ver.group(1) == proj_ver.group(1)
    assert init_ver.group(1) == "0.8.5"


def test_i2_i3_release_kit_files_exist():
    for rel in (
        "scripts/secrets_check.sh",
        "scripts/release/check_denylist.py",
        "scripts/release/path_denylist.toml",
        "scripts/release/stale_refs.sh",
        "scripts/release/check_tracked_data.py",
        "scripts/release/tracked_data_allowlist.toml",
        "scripts/release/repo_hygiene_audit.py",
        "scripts/release/root_docs_allowlist.toml",
        "scripts/release/assert_compose_bind.sh",
        "docs/dev/release_governance.md",
        "docs/dev/dependency_audit.md",
        ".coveragerc",
        ".pre-commit-config.yaml",
    ):
        path = ROOT / rel
        assert path.is_file(), f"missing {rel}"
    cover = (ROOT / ".coveragerc").read_text(encoding="utf-8")
    assert "fail_under" in cover
    assert "transcribe/ui" in cover
    gov = (ROOT / "docs" / "dev" / "release_governance.md").read_text(encoding="utf-8")
    assert "Type: GUIDE" in gov
    assert "authoritative release gate" in gov.lower() or "authoritative" in gov.lower()
