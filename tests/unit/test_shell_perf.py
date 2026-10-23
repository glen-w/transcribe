"""Shell tax contracts — logo cache + once-per-session CSS inject."""

from __future__ import annotations

from pathlib import Path


def test_inject_global_styles_once_per_session(monkeypatch) -> None:
    import transcribe.ui.shell as shell

    markdown_calls: list[int] = []

    class _St:
        session_state: dict = {}

        @staticmethod
        def markdown(*_a, **_k):
            markdown_calls.append(1)

    _St.session_state = {}
    monkeypatch.setattr(shell, "st", _St)

    shell.inject_global_styles()
    shell.inject_global_styles()
    assert len(markdown_calls) == 1

    shell.inject_global_styles(force=True)
    assert len(markdown_calls) == 2


def test_logo_data_uri_is_cached(tmp_path: Path) -> None:
    import transcribe.ui.shell as shell

    logo = tmp_path / "logo.png"
    logo.write_bytes(b"\x89PNG\r\n\x1a\n" + b"x" * 64)
    shell._logo_data_uri.cache_clear()

    mtime = logo.stat().st_mtime_ns
    uri1 = shell._logo_data_uri(str(logo), mtime)
    info = shell._logo_data_uri.cache_info()
    uri2 = shell._logo_data_uri(str(logo), mtime)
    info2 = shell._logo_data_uri.cache_info()

    assert uri1 == uri2
    assert uri1.startswith("data:image/png;base64,")
    assert info.hits == 0 and info.misses == 1
    assert info2.hits == 1 and info2.misses == 1


def test_wide_layout_emits_marker_not_stylesheet(monkeypatch) -> None:
    from transcribe.ui import layout as layout_mod

    calls: list[str] = []

    class _St:
        @staticmethod
        def markdown(text: str, **_k):
            calls.append(text)

    monkeypatch.setattr(layout_mod, "st", _St)
    monkeypatch.setattr(layout_mod, "use_wide_layout", lambda _mode: True)
    layout_mod.apply_page_width("Review")
    assert calls
    assert "tx-wide-layout" in calls[0]
    assert "<style>" not in calls[0]
