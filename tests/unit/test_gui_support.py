"""Settings guided-edit schema stays closed and includes Import DPI."""

from __future__ import annotations

from transcribe.config.gui_support import COMMON_SETTINGS_SCHEMA, CommonSettingField


def test_common_settings_schema_includes_ingest_dpi_and_unique_keys() -> None:
    keys = [field.key for field in COMMON_SETTINGS_SCHEMA]
    assert "ui.overview_cards" in keys
    assert "ui.view_show_advanced" in keys
    assert "ingest.render_dpi" in keys
    assert "ingest.visual_declutter_enabled" in keys
    assert len(keys) == len(set(keys))
    dpi = next(f for f in COMMON_SETTINGS_SCHEMA if f.key == "ingest.render_dpi")
    assert dpi == CommonSettingField("ingest.render_dpi", "Import", "PDF render DPI")
    assert all(isinstance(f, CommonSettingField) for f in COMMON_SETTINGS_SCHEMA)
    assert all(f.key.count(".") >= 1 for f in COMMON_SETTINGS_SCHEMA)
