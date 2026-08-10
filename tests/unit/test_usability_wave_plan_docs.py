"""Offline smoke: usability-wave plan docs landed and indexed."""

from __future__ import annotations

from pathlib import Path


DOCS = Path(__file__).resolve().parents[2] / "docs"


def test_usability_wave_plan_exists_with_tracks():
    plan = DOCS / "usability_wave_plan.md"
    assert plan.is_file(), "docs/usability_wave_plan.md missing"
    text = plan.read_text(encoding="utf-8")
    assert "Type: PRODUCT" in text
    for track in ("U0", "U1", "U2", "U3", "U4"):
        assert track in text, f"plan missing track {track}"
    assert "not the centerpiece" in text
    assert "Wave 2" in text  # naming collision note
    assert "corpus-integrity" in text


def test_indexes_and_roadmap_link_usability_wave():
    for rel in (
        "ROADMAP.md",
        "PRODUCT.md",
        "product_hardening_plan.md",
        "DEV_INDEX.md",
        "USER_INDEX.md",
        "index.md",
    ):
        text = (DOCS / rel).read_text(encoding="utf-8")
        assert "usability_wave_plan.md" in text, f"{rel} missing usability_wave_plan link"


def test_hardening_checklist_splits_phase6_items():
    text = (DOCS / "product_hardening_plan.md").read_text(encoding="utf-8")
    assert "| #7 |" in text
    assert "| #8 |" in text
    assert "| #9 |" in text
    assert "product views" in text.lower() or "Product views" in text
    assert "status strip" in text.lower() or "Status strip" in text
    assert "OCR Advanced" in text


def test_roadmap_now_is_usability_wave():
    text = (DOCS / "ROADMAP.md").read_text(encoding="utf-8")
    assert "## Now — Usability wave" in text
    assert "**U0**" in text and "**U1**" in text
    assert "U2 First-run" in text or "**U2" in text
    assert "U4" in text
