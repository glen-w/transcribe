"""Diagnostics reuses the last report until Run diagnostics is pressed again."""

from __future__ import annotations

from types import SimpleNamespace


def test_ensure_diagnostics_reports_skips_when_cached(monkeypatch) -> None:
    from transcribe.ui import diagnostics as diag

    calls = {"n": 0}

    class _Boom:
        def __init__(self, *_a, **_k) -> None:
            calls["n"] += 1

        def run(self, **_k):
            raise AssertionError("doctor should not run when a report is cached")

    class _St:
        session_state: dict = {}

    _St.session_state = {diag._WORKSPACE_REPORT_KEY: SimpleNamespace(ok=True, findings=[])}
    monkeypatch.setattr(diag, "st", _St)
    monkeypatch.setattr(diag, "CorpusDoctorService", _Boom)
    monkeypatch.setattr(diag, "DoctorService", _Boom)

    diag.ensure_diagnostics_reports(SimpleNamespace(), root="/nb", used_deep=False)
    assert calls["n"] == 0


def test_ensure_diagnostics_reports_runs_when_empty(monkeypatch) -> None:
    from transcribe.ui import diagnostics as diag

    calls = {"n": 0}

    class _Doctor:
        def __init__(self, *_a, **_k) -> None:
            calls["n"] += 1

        def run(self, **_k):
            return SimpleNamespace(ok=True, findings=[])

    class _St:
        session_state: dict = {}

    _St.session_state = {}
    monkeypatch.setattr(diag, "st", _St)
    monkeypatch.setattr(diag, "CorpusDoctorService", _Doctor)
    monkeypatch.setattr(diag, "CorpusPaths", SimpleNamespace(from_runtime=lambda _r: object()))

    diag.ensure_diagnostics_reports(SimpleNamespace(), root=None, used_deep=False)
    assert calls["n"] == 1
    assert diag._WORKSPACE_REPORT_KEY in _St.session_state
