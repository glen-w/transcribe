from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from transcribe.services.archive import NotebookSummary
from transcribe.ui import home as home_mod


class _FakeColumn:
    def __init__(self) -> None:
        self.metrics: list[tuple[str, object]] = []

    def __enter__(self) -> "_FakeColumn":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        return None

    def metric(self, label: str, value: object) -> None:
        self.metrics.append((label, value))


class _FakeStreamlit:
    def __init__(self) -> None:
        self.captions: list[str] = []
        self.markdowns: list[str] = []
        self.images: list[tuple[str, int | None]] = []
        self.columns_specs: list[object] = []

    def caption(self, text: str) -> None:
        self.captions.append(text)

    def markdown(self, text: str) -> None:
        self.markdowns.append(text)

    def image(self, image: str, width: int | None = None) -> None:
        self.images.append((image, width))

    def columns(self, spec, **_kwargs):
        self.columns_specs.append(spec)
        if isinstance(spec, int):
            return tuple(_FakeColumn() for _ in range(spec))
        return tuple(_FakeColumn() for _ in spec)


class _FakeArchive:
    def __init__(self, notebooks: list[NotebookSummary]) -> None:
        self._notebooks = notebooks

    def list_notebooks(self, *, order: str) -> list[NotebookSummary]:
        assert order == "newest"
        return self._notebooks


def test_render_home_shows_recent_cover_thumbnail(monkeypatch) -> None:
    fake_st = _FakeStreamlit()
    thumb = Path("/tmp/recent-cover.jpg")
    notebook = NotebookSummary(
        project_id="proj-1",
        title="Recent Notebook",
        root=Path("/tmp/proj-1"),
        page_count=12,
        tags=[],
        cover_page_id=None,
        date_start=None,
        date_end=None,
        pages_per_day=None,
    )
    runtime = SimpleNamespace(projects_dir=Path("/tmp/projects"))

    monkeypatch.setattr(home_mod, "st", fake_st)
    monkeypatch.setattr(home_mod, "ollama_health_line", lambda: "Ollama reachable")
    monkeypatch.setattr(home_mod, "_recent_cover_thumb", lambda _root: thumb)
    monkeypatch.setattr(home_mod, "load_live_notebook_context", lambda **_k: object())
    monkeypatch.setattr(home_mod, "render_configured_actions", lambda *_a, **_k: None)

    home_mod.render_home(runtime, _FakeArchive([notebook]))

    assert fake_st.images == [(str(thumb), home_mod._RECENT_COVER_WIDTH_PX)]
    assert [spec for spec in fake_st.columns_specs if spec == [1, 8]]

