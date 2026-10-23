"""Home Ollama one-liner is session-cached."""

from __future__ import annotations


def test_ollama_health_line_uses_session_cache(monkeypatch) -> None:
    from transcribe.ui import home as home_mod

    probes = {"n": 0}

    def _probe() -> str:
        probes["n"] += 1
        return "Ollama reachable"

    class _St:
        session_state: dict = {}

    _St.session_state = {}
    monkeypatch.setattr(home_mod, "st", _St)
    monkeypatch.setattr(home_mod, "_OLLAMA_LINE_TTL_S", 30.0)
    monkeypatch.setattr(home_mod, "_probe_ollama_health", _probe)
    monkeypatch.setattr(home_mod.time, "monotonic", lambda: 100.0)

    first = home_mod.ollama_health_line()
    second = home_mod.ollama_health_line()
    assert first == "Ollama reachable"
    assert second == first
    assert probes["n"] == 1

    home_mod.ollama_health_line(force=True)
    assert probes["n"] == 2
