from __future__ import annotations

from transcribe.services.export_document import document_css
from transcribe.services.export_options import (
    BODY_FONT_CATALOG,
    BODY_FONT_CHOICES,
    ExportOptions,
    ExportTypography,
    body_font_label,
    normalize_body_font,
)


def test_body_font_catalog_has_twenty_five_choices():
    assert len(BODY_FONT_CHOICES) == 25
    assert len(BODY_FONT_CATALOG) == 25


def test_normalize_body_font_keeps_legacy_and_unknown_values():
    assert normalize_body_font("sans") == "sans"
    assert normalize_body_font("Merriweather") == "merriweather"
    assert normalize_body_font("not-a-font") == "serif"


def test_export_typography_maps_named_fonts_to_pdf_base():
    typo = ExportTypography(body_font="open_sans")
    assert typo.pdf_fontname == "helv"
    assert "Open Sans" in typo.css_font_family

    mono = ExportTypography(body_font="jetbrains_mono")
    assert mono.pdf_fontname == "cour"


def test_google_font_import_in_document_css():
    css = document_css(ExportOptions(typography=ExportTypography(body_font="lora")))
    assert "fonts.googleapis.com" in css
    assert "Lora" in css
    assert "font-family: var(--body-font)" in css


def test_system_font_has_no_google_import():
    css = document_css(ExportOptions(typography=ExportTypography(body_font="georgia")))
    assert "fonts.googleapis.com" not in css
    assert "Georgia" in css


def test_body_font_labels_are_human_readable():
    assert body_font_label("serif") == "System serif"
    assert body_font_label("open_sans") == "Open Sans"
