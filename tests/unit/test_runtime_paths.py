from __future__ import annotations

import os

from transcribe.runtime_paths import build_runtime_paths, default_ollama_base_url


def test_runtime_paths_respect_env(tmp_path, monkeypatch):
    projects = tmp_path / "projects"
    inbox = tmp_path / "inbox"
    exports = tmp_path / "exports"
    data = tmp_path / "data"
    monkeypatch.setenv("TRANSCRIBE_DATA_DIR", str(data))
    monkeypatch.setenv("TRANSCRIBE_PROJECTS_DIR", str(projects))
    monkeypatch.setenv("TRANSCRIBE_INBOX_DIR", str(inbox))
    monkeypatch.setenv("TRANSCRIBE_EXPORT_DIR", str(exports))

    paths = build_runtime_paths()
    assert paths.projects_dir == projects
    assert paths.inbox_dir == inbox
    assert paths.export_dir == exports
    assert paths.data_dir == data
    assert paths.default_project_dir() == projects / "notebook-project"


def test_runtime_paths_default_under_data(tmp_path, monkeypatch):
    data = tmp_path / "data"
    monkeypatch.setenv("TRANSCRIBE_DATA_DIR", str(data))
    monkeypatch.delenv("TRANSCRIBE_PROJECTS_DIR", raising=False)
    monkeypatch.delenv("TRANSCRIBE_INBOX_DIR", raising=False)
    monkeypatch.delenv("TRANSCRIBE_EXPORT_DIR", raising=False)

    paths = build_runtime_paths()
    assert paths.projects_dir == data / "projects"
    assert paths.inbox_dir == data / "inbox"
    assert paths.export_dir == data / "exports"


def test_default_ollama_url_from_env(monkeypatch):
    monkeypatch.setenv("TRANSCRIBE_OLLAMA_BASE_URL", "http://host.docker.internal:11434")
    assert default_ollama_base_url() == "http://host.docker.internal:11434"
    monkeypatch.delenv("TRANSCRIBE_OLLAMA_BASE_URL", raising=False)
    assert default_ollama_base_url() == "http://localhost:11434"


def test_bootstrap_does_not_override_existing(tmp_path, monkeypatch):
    from transcribe import _bootstrap

    env_file = tmp_path / ".env"
    env_file.write_text("TRANSCRIBE_EXPORT_DIR=/from-dotenv\n", encoding="utf-8")
    monkeypatch.setenv("TRANSCRIBE_EXPORT_DIR", "/from-shell")
    # Reset guard so load runs again for this test file.
    _bootstrap._bootstrapped = False
    _bootstrap.bootstrap(env_file)
    assert os.environ["TRANSCRIBE_EXPORT_DIR"] == "/from-shell"
