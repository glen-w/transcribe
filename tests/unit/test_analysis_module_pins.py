"""Registered analysis MODULE_IDs must stay on the port-pin list."""

from __future__ import annotations

import re
from pathlib import Path

from transcribe.analysis.modules import get_registered_modules

ROOT = Path(__file__).resolve().parents[2]
DOCS = ROOT / "docs"
PINS = DOCS / "dev" / "analysis_port_pins.md"
AUDIT = DOCS / "dev" / "analysis_quality_audit.md"
GOVERNANCE = DOCS / "dev" / "release_governance.md"
MODULES_DIR = ROOT / "src" / "transcribe" / "analysis" / "modules"

PIN_ROW_RE = re.compile(r"^\| `([a-z][a-z0-9_]*)` \|", re.M)
MODULE_ID_RE = re.compile(r'^MODULE_ID\s*=\s*"([a-z][a-z0-9_]*)"', re.M)
SEMANTIC_CLASSES = frozenset({"parity", "adaptation", "fork"})
FROZEN_CORE_COUNT = 26


def _pinned_ids() -> set[str]:
    return set(PIN_ROW_RE.findall(PINS.read_text(encoding="utf-8")))


def _source_module_ids() -> set[str]:
    found: set[str] = set()
    for path in MODULES_DIR.glob("*.py"):
        if path.name.startswith("_"):
            continue
        found.update(MODULE_ID_RE.findall(path.read_text(encoding="utf-8")))
    return found


def _pin_semantic_class() -> dict[str, str]:
    rows: dict[str, str] = {}
    for line in PINS.read_text(encoding="utf-8").splitlines():
        if not line.startswith("| `"):
            continue
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) < 5:
            continue
        mid = cells[0].strip("`")
        klass = cells[4]
        if klass in SEMANTIC_CLASSES:
            rows[mid] = klass
    return rows


def test_registered_module_ids_are_on_the_pin_list():
    registered = set(get_registered_modules().keys())
    missing = registered - _pinned_ids()
    assert not missing, f"registered MODULE_IDs missing from pin list: {sorted(missing)}"
    assert len(registered) == FROZEN_CORE_COUNT


def test_source_module_id_constants_match_registered_set():
    registered = set(get_registered_modules().keys())
    source = _source_module_ids()
    assert source == registered, (
        f"MODULE_ID constants vs registry: extra={sorted(source - registered)} "
        f"missing={sorted(registered - source)}"
    )


def test_pin_semantic_class_matches_module():
    pins = _pin_semantic_class()
    for mid, mod in get_registered_modules().items():
        assert mid in pins, f"{mid} has no pin semantic_class"
        assert getattr(mod, "semantic_class") == pins[mid], (
            f"{mid}: code {mod.semantic_class!r} != pin {pins[mid]!r}"
        )


def test_analysis_quality_audit_lists_every_registered_id():
    text = AUDIT.read_text(encoding="utf-8")
    for mid in get_registered_modules():
        assert f"`{mid}`" in text, f"analysis_quality_audit.md missing `{mid}`"
    for needle in (
        "seed-bucket",
        "TF-IDF",
        "baseline",
        "bertopic",
        "unavailable_extra",
    ):
        assert needle in text, f"audit missing honesty needle {needle!r}"


def test_v1_gate_docs_exist_and_join_1_0_checklist():
    for rel in (
        "dev/release_severity_triage.md",
        "dev/release_ops.md",
        "dev/manual_acceptance_1_0.md",
        "dev/analysis_quality_audit.md",
    ):
        assert (DOCS / rel).is_file(), f"missing docs/{rel}"
    gov = GOVERNANCE.read_text(encoding="utf-8")
    assert "release_severity_triage.md" in gov
    assert "release_ops.md" in gov
    assert "manual_acceptance_1_0.md" in gov
    assert "analysis_quality_audit.md" in gov
    assert "0.9.0 still keys off U2" in gov
    assert "1.0" in gov
