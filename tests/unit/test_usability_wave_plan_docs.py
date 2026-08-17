"""Offline smoke: usability-wave plan docs landed and indexed."""

from __future__ import annotations

from pathlib import Path

DOCS = Path(__file__).resolve().parents[2] / "docs"
ROOT = DOCS.parent
ARCHIVE_PLANS = DOCS / "archive" / "plans"


def test_usability_wave_plan_exists_with_tracks():
    plan = DOCS / "usability_wave_plan.md"
    assert plan.is_file(), "docs/usability_wave_plan.md missing"
    text = plan.read_text(encoding="utf-8")
    assert "Type: PRODUCT" in text
    assert "[~] active" in text
    for track in ("U0", "U1", "U2", "U3", "U4"):
        assert track in text, f"plan missing track {track}"
    assert "not the centerpiece" in text
    assert "Wave 2" in text  # naming collision note
    assert "corpus-integrity" in text


def test_indexes_and_roadmap_link_usability_wave():
    for rel in (
        "ROADMAP.md",
        "PRODUCT.md",
        "archive/plans/product_hardening_plan.md",
        "DEV_INDEX.md",
        "USER_INDEX.md",
        "index.md",
    ):
        text = (DOCS / rel).read_text(encoding="utf-8")
        assert "usability_wave_plan.md" in text, f"{rel} missing usability_wave_plan link"


def test_readme_direction_links_usability_wave():
    text = (ROOT / "README.md").read_text(encoding="utf-8")
    assert "usability_wave_plan.md" in text
    assert "usability wave" in text.lower()


def test_history_docs_point_at_usability_wave_now():
    for path in (
        ARCHIVE_PLANS / "analysis_wave1_plan.md",
        ARCHIVE_PLANS / "analysis_wave1_hardening_plan.md",
        DOCS / "dev" / "analysis_module_porting.md",
    ):
        text = path.read_text(encoding="utf-8")
        assert "Now — Product hardening" not in text, f"{path} has stale Now heading"
        assert (
            "usability_wave_plan.md" in text or "Usability wave" in text
        ), f"{path} should point at usability wave"


def test_hardening_checklist_splits_phase6_items():
    text = (ARCHIVE_PLANS / "product_hardening_plan.md").read_text(encoding="utf-8")
    assert "| #7 |" in text
    assert "| #8 |" in text
    assert "| #9 |" in text
    assert "product views" in text.lower() or "Product views" in text
    assert "status strip" in text.lower() or "Status strip" in text
    assert "OCR Advanced" in text
    # Phase 6 landed with hardening exit gate on main
    for line in text.splitlines():
        if line.startswith("| #7 |") or line.startswith("| #8 |") or line.startswith("| #9 |"):
            assert "| done |" in line, line


def test_roadmap_now_is_usability_wave():
    text = (DOCS / "ROADMAP.md").read_text(encoding="utf-8")
    assert "## Now — Usability wave" in text
    assert "**U0**" in text and "**U1**" in text
    assert "U2 First-run" in text or "**U2" in text
    assert "U4" in text
    assert "U0–U1 — Product hardening" in text
    assert "[x] done" in text  # hardening embedded done


def test_roadmap_after_1_0_autobiography_is_gated():
    text = (DOCS / "ROADMAP.md").read_text(encoding="utf-8")
    assert "## After 1.0 — Notebook-anchored autobiography workbench" in text
    assert "gated on 1.0" in text
    for release in ("1.1", "1.2", "1.3", "1.4", "1.5", "1.6", "1.7", "1.8", "1.9", "2.0"):
        assert release in text, f"ROADMAP missing post-1.0 release {release}"
    assert "SourceDocument" in text
    assert "sibling context corpus" in text
    assert "ReconstructionBundle" in text
    assert "Mood → Moments" in text
    product = (DOCS / "PRODUCT.md").read_text(encoding="utf-8")
    assert "After 1.0" in product
    assert "usability_wave_plan.md" in product


def test_roadmap_path_to_0_9_foundation():
    text = (DOCS / "ROADMAP.md").read_text(encoding="utf-8")
    assert "## Path to 0.9.0 / 0.9-1 / 1.0" in text
    assert "0.9.0" in text
    assert "0.9-1" in text
    assert "Foundation readiness" in text or "Foundation readiness checklist" in text or "Track C" in text
    assert "Notebook core freeze" in text
    assert "U2.2 Sample notebook" in text or "U2.2" in text
    assert "U2.4" in text
    assert "user_testing_0_9.md" in text
    protocol = DOCS / "dev" / "user_testing_0_9.md"
    assert protocol.is_file()
    proto = protocol.read_text(encoding="utf-8")
    assert "Type: GUIDE" in proto
    assert "0.9-1" in proto
    assert "autobiography" in proto.lower()
    assert "Explicitly out of script" in proto or "out of script" in proto.lower()
    infra = (DOCS / "infrastructure_wave_0_9_plan.md").read_text(encoding="utf-8")
    assert "0.9-1" in infra
    assert "not an I7" in infra or "not I7" in infra


def test_detection_contract_documents_midrun_reconcile_rule():
    text = (DOCS / "contracts" / "detection-run-storage.md").read_text(encoding="utf-8")
    assert "reconcile=False" in text


def test_archived_plans_have_banners_and_live_indexes_do_not_list_as_active():
    for name in (
        "analysis_wave1_plan.md",
        "analysis_wave1_hardening_plan.md",
        "detection_wave2_plan.md",
        "bulk_run_analysis_plan.md",
        "product_hardening_plan.md",
    ):
        text = (ARCHIVE_PLANS / name).read_text(encoding="utf-8")
        assert "Archived / superseded" in text, f"{name} missing archive banner"
    user = (DOCS / "USER_INDEX.md").read_text(encoding="utf-8")
    assert "Not in this index" in user
    assert "ARCHIVE_INDEX" in user
