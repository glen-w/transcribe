"""Tests for shared adjacent ⓘ tooltip HTML helpers."""

from __future__ import annotations

from types import SimpleNamespace

from transcribe.ui.components import info_tooltip


def test_build_info_tooltip_html_escapes_and_is_accessible(monkeypatch) -> None:
    monkeypatch.setattr(info_tooltip, "info_tooltips_enabled", lambda: True)
    html_out = info_tooltip.build_info_tooltip_html(
        ['Line <b>one</b>', 'Line "two"'],
        control_id="tip-a",
        aria_label='Help for <section>',
        test_id="tx-info-tooltip",
    )
    assert "<b>one</b>" not in html_out
    assert "&lt;b&gt;one&lt;/b&gt;" in html_out
    assert 'tabindex="0"' in html_out
    assert 'role="tooltip"' in html_out
    assert 'id="tip-a"' in html_out
    assert "ⓘ" in html_out
    assert "aria-describedby" in html_out
    assert "Help for &lt;section&gt;" in html_out
    assert "tx-methodology-info" in html_out


def test_build_info_tooltip_html_empty_when_no_lines(monkeypatch) -> None:
    monkeypatch.setattr(info_tooltip, "info_tooltips_enabled", lambda: True)
    assert info_tooltip.build_info_tooltip_html([], control_id="x", aria_label="a") == ""
    assert (
        info_tooltip.build_info_tooltip_html("  ", control_id="x", aria_label="a") == ""
    )


def test_build_info_tooltip_html_respects_prefs_off(monkeypatch) -> None:
    monkeypatch.setattr(info_tooltip, "info_tooltips_enabled", lambda: False)
    assert (
        info_tooltip.build_info_tooltip_html(
            "Note",
            control_id="t",
            aria_label="Note",
        )
        == ""
    )
    html_out = info_tooltip.build_info_tooltip_html(
        "Note",
        control_id="t",
        aria_label="Note",
        respect_prefs=False,
    )
    assert "ⓘ" in html_out
    assert "Note" in html_out


def test_widget_help_gates_on_prefs(monkeypatch) -> None:
    monkeypatch.setattr(info_tooltip, "info_tooltips_enabled", lambda: True)
    assert info_tooltip.widget_help("  Tip  ") == "Tip"
    assert info_tooltip.widget_help("") is None
    assert info_tooltip.widget_help(None) is None
    monkeypatch.setattr(info_tooltip, "info_tooltips_enabled", lambda: False)
    assert info_tooltip.widget_help("Tip") is None


def test_info_tooltips_enabled_reads_cached_prefs(monkeypatch) -> None:
    monkeypatch.setattr(
        "transcribe.ui.action_menus.prefs.get_cached_runtime_prefs",
        lambda: SimpleNamespace(show_info_tooltips=False),
    )
    assert info_tooltip.info_tooltips_enabled() is False
    monkeypatch.setattr(
        "transcribe.ui.action_menus.prefs.get_cached_runtime_prefs",
        lambda: SimpleNamespace(show_info_tooltips=True),
    )
    assert info_tooltip.info_tooltips_enabled() is True


def test_build_section_heading_with_info_html(monkeypatch) -> None:
    monkeypatch.setattr(info_tooltip, "info_tooltips_enabled", lambda: True)
    tip = info_tooltip.build_info_tooltip_html(
        "Note",
        control_id="t1",
        aria_label="Note",
    )
    heading = info_tooltip.build_section_heading_with_info_html("Trends", tip)
    assert 'class="tx-section-info-heading"' in heading
    assert "<h4>Trends</h4>" in heading
    assert "ⓘ" in heading


def test_merge_prefs_show_info_tooltips() -> None:
    from transcribe.ui.action_menus.prefs import merge_prefs

    assert merge_prefs({}).show_info_tooltips is True
    assert merge_prefs({"show_info_tooltips": False}).show_info_tooltips is False
    assert merge_prefs({"show_info_tooltips": "yes"}).show_info_tooltips is True
