"""Settings hub paints only the selected panel."""

from __future__ import annotations

from pathlib import Path


def test_settings_dispatch_invokes_only_selected_panel(monkeypatch) -> None:
    from transcribe.ui import settings_interface as iface

    calls: list[str] = []

    monkeypatch.setattr(
        iface,
        "_settings_panel_renderers",
        lambda: {
            "Configuration": lambda: calls.append("Configuration"),
            "Analysis": lambda: calls.append("Analysis"),
            "Models": lambda: calls.append("Models"),
        },
    )
    iface.render_settings_panel("Configuration")
    assert calls == ["Configuration"]
    iface.render_settings_panel("Models")
    assert calls == ["Configuration", "Models"]


def test_settings_source_avoids_st_tabs() -> None:
    iface = Path("src/transcribe/ui/settings_interface.py").read_text(encoding="utf-8")
    analysis = Path("src/transcribe/ui/settings_analysis.py").read_text(encoding="utf-8")
    export = Path("src/transcribe/ui/export_panel.py").read_text(encoding="utf-8")
    detect = Path("src/transcribe/ui/run_detection.py").read_text(encoding="utf-8")
    assert "st.tabs(" not in iface
    assert "st.tabs(" not in analysis
    assert "st.tabs(" not in export
    assert "st.tabs(" not in detect
    assert "st.segmented_control" in iface
    assert "st.segmented_control" in analysis
    assert "st.segmented_control" in export
    assert "st.segmented_control" in detect
    assert '"Detection fine-tune"' in export
    assert "export_hub_selected_tab" in export
