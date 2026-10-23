"""Open-notebook loads reconcile interrupted runs once per root per session."""

from __future__ import annotations


def test_load_open_notebook_reconciles_once(monkeypatch) -> None:
    from transcribe.ui import app as app_mod

    class _Projects:
        def __init__(self) -> None:
            self.calls: list[bool] = []

        def load(self, *, reconcile: bool = True):
            self.calls.append(reconcile)
            return "project"

    class _St:
        session_state: dict = {}

    _St.session_state = {}
    monkeypatch.setattr(app_mod, "st", _St)
    projects = _Projects()
    first = app_mod._load_open_notebook(projects, "/nb-a")
    second = app_mod._load_open_notebook(projects, "/nb-a")
    other = app_mod._load_open_notebook(projects, "/nb-b")
    assert first == "project" and second == "project" and other == "project"
    assert projects.calls == [True, False, True]
