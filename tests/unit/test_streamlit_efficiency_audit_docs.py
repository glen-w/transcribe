"""Offline smoke: Streamlit efficiency audit doc landed and indexed."""

from __future__ import annotations

from pathlib import Path

DOCS = Path(__file__).resolve().parents[2] / "docs"


def test_streamlit_efficiency_audit_exists_with_pr1_matrix():
    plan = DOCS / "dev" / "streamlit_efficiency_audit.md"
    assert plan.is_file(), "docs/dev/streamlit_efficiency_audit.md missing"
    text = plan.read_text(encoding="utf-8")
    assert "[~] active" in text
    assert "rerun_cache" in text
    for surface in (
        "Shell CSS",
        "Sidebar logo",
        "Review queue",
        "View health",
        "Analyse poll",
    ):
        assert surface in text, f"matrix missing {surface}"
    assert "st.cache_resource.clear()" in text
    assert "Acceptance (PR1)" in text


def test_dev_index_links_streamlit_efficiency_audit():
    text = (DOCS / "DEV_INDEX.md").read_text(encoding="utf-8")
    assert "streamlit_efficiency_audit.md" in text
