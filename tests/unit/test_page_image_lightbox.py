"""Roadmap contract: page scan fullscreen uses Streamlit built-in."""

from pathlib import Path


UI_ROOT = Path("src/transcribe/ui")
ROADMAP = Path("docs/ROADMAP.md")


def test_reader_and_review_use_st_image_not_custom_lightbox():
    for name in ("review_workbench.py", "page_viewer.py"):
        text = (UI_ROOT / name).read_text(encoding="utf-8")
        assert "st.image" in text
        assert "page_image_lightbox" not in text
        assert "render_page_image" not in text


def test_roadmap_documents_fullscreen_fallback():
    text = ROADMAP.read_text(encoding="utf-8")
    assert "Page scan fullscreen" in text
    assert "streamlit/streamlit/issues/8031" in text
    assert "tx-page-lightbox" in text
    assert "txOpenPageLightbox" in text
