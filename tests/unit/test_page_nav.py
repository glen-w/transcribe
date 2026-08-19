"""Pure helpers for page-viewer navigation contexts."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from transcribe.domain.models import AttemptProvenance, CleanupRecord, OCRAttempt
from transcribe.domain.dates import ApproximateDate
from transcribe.ui.action_menus.nav import notebook_view_entries
from transcribe.ui.page_viewer import (
    _cleanup_mode_help,
    _escape_markdown_plain,
    _render_transcription_plain,
    _filter_existing_entries,
    _normalize_entries,
    _ocr_compare_preview,
    _page_number_to_index,
    _reader_cover_page_id,
    _resolve_view_entries,
    _shows_compare_attempts,
    _snap_page_to_search_scope,
    _transcription_model_help,
    _transcription_model_label,
)


def _attempt(
    *,
    model_name: str | None = None,
    fingerprint_model: str | None = None,
) -> OCRAttempt:
    provenance = None
    if model_name is not None:
        provenance = AttemptProvenance(
            model_name=model_name,
            model_digest=None,
            model_identity_verified=False,
            prompt_id="p",
            prompt_version="1",
            prompt_sha256="abc",
            prompt_text="x",
            input_sha256="def",
            preprocess_profile="none",
            preprocess_version=1,
            generation_options={},
            application_version="0",
            ollama_host="http://localhost",
            request_id="r",
            render_id="render",
        )
    payload = {"model_name": fingerprint_model} if fingerprint_model else {}
    return OCRAttempt(
        attempt_id="a1",
        status="succeeded",
        input_fingerprint="fp",
        fingerprint_payload=payload,
        raw_text="hi",
        provenance=provenance,
        provider_metadata={},
        started_at="2024-01-01T00:00:00Z",
    )


def test_page_number_to_index_valid():
    assert _page_number_to_index(1, 172) == 0
    assert _page_number_to_index(2, 172) == 1
    assert _page_number_to_index(172, 172) == 171


def test_page_number_to_index_rejects_out_of_range():
    assert _page_number_to_index(0, 172) is None
    assert _page_number_to_index(173, 172) is None
    assert _page_number_to_index(1, 0) is None


def test_reader_cover_page_id_uses_explicit_cover():
    project = SimpleNamespace(
        cover_page_id="cover-2",
        pages=[SimpleNamespace(page_id="page-1"), SimpleNamespace(page_id="cover-2")],
    )
    assert _reader_cover_page_id(project) == "cover-2"


def test_reader_cover_page_id_falls_back_to_first_page():
    project = SimpleNamespace(
        cover_page_id=None,
        pages=[SimpleNamespace(page_id="page-1"), SimpleNamespace(page_id="page-2")],
    )
    assert _reader_cover_page_id(project) == "page-1"


def test_transcription_model_label_from_provenance():
    assert _transcription_model_label(_attempt(model_name="gemma3:4b")) == "gemma3:4b"


def test_transcription_model_label_falls_back_to_fingerprint():
    assert _transcription_model_label(_attempt(fingerprint_model="llava:latest")) == "llava:latest"


def test_transcription_model_label_none_without_attempt():
    assert _transcription_model_label(None) is None


def test_transcription_model_help_includes_provenance():
    help_text = _transcription_model_help(
        _attempt(model_name="glm-ocr:latest"),
        "glm-ocr:latest",
    )
    assert "glm-ocr:latest" in help_text
    assert "Vision OCR" in help_text
    assert "Prompt: p v1" in help_text
    assert "Preprocess: none" in help_text
    assert "unverified" in help_text


def test_transcription_model_help_without_provenance():
    help_text = _transcription_model_help(
        _attempt(fingerprint_model="llava:latest"),
        "llava:latest",
    )
    assert "llava:latest" in help_text
    assert "Prompt:" not in help_text


def test_cleanup_mode_help_sanitize_light():
    help_text = _cleanup_mode_help(
        CleanupRecord(
            execution_status="succeeded",
            acceptance_status="applied",
            mode="sanitize_light",
            model_name="llama3.1:8b",
        )
    )
    assert "obvious OCR artefacts" in help_text
    assert "paraphrase" in help_text
    assert "llama3.1:8b" in help_text


def test_cleanup_mode_help_unknown_mode():
    help_text = _cleanup_mode_help(
        CleanupRecord(
            execution_status="succeeded",
            acceptance_status="applied",
            mode="custom_mode",
        )
    )
    assert "custom_mode" in help_text
    assert "raw OCR" in help_text


def test_normalize_entries_from_page_ids():
    entries = _normalize_entries(
        page_ids=["a", "b"],
        project_root="/tmp/nb",
        view_entries=None,
    )
    assert entries == [
        {"page_id": "a", "project_root": "/tmp/nb"},
        {"page_id": "b", "project_root": "/tmp/nb"},
    ]


def test_normalize_entries_cross_notebook():
    entries = _normalize_entries(
        page_ids=None,
        project_root=None,
        view_entries=[
            {"page_id": "p1", "project_root": "/a"},
            {"page_id": "p2", "project_root": "/b"},
        ],
    )
    assert entries[0]["project_root"] == "/a"
    assert entries[1]["project_root"] == "/b"


def test_filter_existing_entries_drops_deleted(tmp_path: Path):
    alive = tmp_path / "brown_3"
    alive.mkdir()
    (alive / "project.json").write_text("{}", encoding="utf-8")
    dead = tmp_path / "notebook-project"
    entries = _filter_existing_entries(
        [
            {"page_id": "old", "project_root": str(dead)},
            {"page_id": "new", "project_root": str(alive)},
        ]
    )
    assert entries == [{"page_id": "new", "project_root": str(alive)}]


def test_resolve_prefers_explicit_page_ids_over_stale_session(tmp_path: Path, monkeypatch):
    alive = tmp_path / "brown_3"
    alive.mkdir()
    (alive / "project.json").write_text("{}", encoding="utf-8")
    dead = tmp_path / "notebook-project"

    class _FakeState(dict):
        pass

    fake = _FakeState(
        view_entries=[
            {"page_id": "stale", "project_root": str(dead)},
        ]
    )
    monkeypatch.setattr("transcribe.ui.page_viewer.st.session_state", fake)

    entries = _resolve_view_entries(
        page_ids=["a", "b"],
        project_root=str(alive),
        view_entries=None,
        prefer_session_entries=True,
    )
    assert entries == [
        {"page_id": "a", "project_root": str(alive)},
        {"page_id": "b", "project_root": str(alive)},
    ]


def test_resolve_drops_deleted_explicit_view_entries(tmp_path: Path):
    alive = tmp_path / "brown_3"
    alive.mkdir()
    (alive / "project.json").write_text("{}", encoding="utf-8")
    dead = tmp_path / "notebook-project"

    entries = _resolve_view_entries(
        page_ids=["fallback"],
        project_root=str(alive),
        view_entries=[
            {"page_id": "gone", "project_root": str(dead)},
        ],
        prefer_session_entries=False,
    )
    assert entries == [{"page_id": "fallback", "project_root": str(alive)}]


def test_ocr_compare_preview_escapes_heading_markdown():
    """Regression: OCR starting with # must not become a Streamlit heading."""
    preview = _ocr_compare_preview('# 220820 Scandinavia House "All of us"')
    assert preview.startswith("\\#")
    assert "220820 Scandinavia" in preview


def test_ocr_compare_preview_escapes_list_and_truncates():
    text = "- Use a consistent style throughout the document\n" + ("word " * 40)
    preview = _ocr_compare_preview(text, limit=40)
    assert preview.startswith("\\-")
    assert preview.endswith("…")
    assert len(preview) <= 40 + preview.count("\\")  # escapes add length


def test_escape_markdown_plain_renders_hash_literally():
    assert _escape_markdown_plain("# hi *there*") == "\\# hi \\*there\\*"


def test_render_transcription_plain_escapes_before_markdown(monkeypatch):
    captured: list[str] = []

    class _St:
        @staticmethod
        def markdown(text: str) -> None:
            captured.append(text)

    monkeypatch.setattr("transcribe.ui.page_viewer.st", _St)
    _render_transcription_plain("# Une beauté pénétrante")
    assert captured == ["\\# Une beauté pénétrante"]


def test_shows_compare_attempts_requires_two_succeeded():
    from types import SimpleNamespace

    a = SimpleNamespace(status="succeeded", raw_text="one", attempt_kind="vision")
    b = SimpleNamespace(status="succeeded", raw_text="two", attempt_kind="vision")
    empty = SimpleNamespace(status="succeeded", raw_text="  ", attempt_kind="vision")
    assert _shows_compare_attempts(None) is False
    assert _shows_compare_attempts(SimpleNamespace(attempts=[a])) is False
    assert _shows_compare_attempts(SimpleNamespace(attempts=[a, empty])) is False
    assert _shows_compare_attempts(SimpleNamespace(attempts=[a, b])) is True


def test_shows_compare_attempts_true_for_lone_composite():
    from types import SimpleNamespace

    comp = SimpleNamespace(status="succeeded", raw_text="merged", attempt_kind="composite")
    assert _shows_compare_attempts(SimpleNamespace(attempts=[comp])) is True


def test_notebook_view_entries_chronological_order():
    p1 = SimpleNamespace(page_id="p1", date=ApproximateDate(2024, 5, 1))
    p2 = SimpleNamespace(page_id="p2", date=ApproximateDate(2024, 1, 1))
    p3 = SimpleNamespace(page_id="p3", date=None)
    project = SimpleNamespace(pages=[p1, p2, p3])
    entries = notebook_view_entries(project, "/tmp/nb")
    assert entries == [
        {"page_id": "p2", "project_root": "/tmp/nb"},
        {"page_id": "p1", "project_root": "/tmp/nb"},
        {"page_id": "p3", "project_root": "/tmp/nb"},
    ]


def test_snap_page_to_search_scope_keeps_current_hit():
    entries = [
        {"page_id": "a", "project_root": "/nb1"},
        {"page_id": "b", "project_root": "/nb2"},
    ]
    assert _snap_page_to_search_scope("b", entries, "/nb2") == "b"


def test_snap_page_to_search_scope_same_notebook_fallback():
    entries = [
        {"page_id": "a", "project_root": "/nb1"},
        {"page_id": "b", "project_root": "/nb2"},
    ]
    assert _snap_page_to_search_scope("x", entries, "/nb2") == "b"


def test_snap_page_to_search_scope_first_overall():
    entries = [
        {"page_id": "a", "project_root": "/nb1"},
        {"page_id": "b", "project_root": "/nb2"},
    ]
    assert _snap_page_to_search_scope("x", entries, "/nb3") == "a"
