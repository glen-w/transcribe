"""OCR lifecycle: prefer/promote, compare validators, preference stats, finetune export."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from transcribe.domain.models import (
    AttemptProvenance,
    ComparisonRecord,
    OCRAttempt,
    PageResult,
    prune_attempts,
)
from transcribe.errors import ProjectError
from transcribe.ingest import IngestService
from transcribe.services.finetune_export import (
    FinetuneExportOptions,
    FinetuneExportService,
)
from transcribe.services.ocr_compare import (
    _parse_rank_json,
    validate_composite_against_union,
)
from transcribe.services.ocr_preference_stats import (
    append_preference_event,
    preference_hint_for_model,
    rollup_preference_stats,
)
from transcribe.services.project import ProjectService, open_project_paths
from tests.conftest import FakeClock, SequentialIds
from tests.ingest.test_ingest import _png_bytes


def _attempt(
    aid: str,
    *,
    text: str = "hello",
    model: str = "model-a",
    kind: str = "vision",
    status: str = "succeeded",
    started: str = "2020-01-01T00:00:00+00:00",
    pass_id: str | None = None,
    sources: list[str] | None = None,
) -> OCRAttempt:
    return OCRAttempt(
        attempt_id=aid,
        status=status,
        input_fingerprint=f"fp-{aid}",
        fingerprint_payload={},
        raw_text=text,
        provenance=AttemptProvenance(
            model_name=model,
            model_digest="d" * 64,
            model_identity_verified=True,
            prompt_id="faithful_markdown",
            prompt_version="1",
            prompt_sha256="a" * 64,
            prompt_text="p",
            input_sha256="b" * 64,
            preprocess_profile="none",
            preprocess_version=1,
            generation_options={},
            application_version="0",
            ollama_host="http://localhost:11434",
            request_id=aid,
            render_id="r1",
        ),
        provider_metadata={},
        started_at=started,
        completed_at=started,
        attempt_kind=kind,
        pass_id=pass_id,
        source_attempt_ids=list(sources or []),
    )


def _project_with_page(tmp_path: Path) -> tuple[ProjectService, str]:
    paths = open_project_paths(tmp_path / "projects" / "nb")
    clock, ids = FakeClock(), SequentialIds()
    projects = ProjectService(paths, clock=clock, ids=ids)
    projects.create("Test")
    ingest = IngestService(paths, clock=clock, ids=ids)
    src = tmp_path / "page.png"
    src.write_bytes(_png_bytes())
    project = ingest.import_path(src)
    return projects, project.pages[0].page_id


def test_prefer_is_promote_sets_active(tmp_path: Path) -> None:
    projects, page_id = _project_with_page(tmp_path)
    a1 = _attempt("a1", text="one", model="m1")
    a2 = _attempt("a2", text="two", model="m2", started="2020-01-02T00:00:00+00:00")
    projects.record_generation(page_id, a1, activate=True)
    projects.record_generation(page_id, a2, activate=False)
    result = projects.set_preferred_attempt(page_id, "a1", mode="prefer_is_promote")
    assert result.preferred_attempt_id == "a1"
    assert result.active_attempt_id == "a1"
    assert result.effective_text() == "one"


def test_prefer_only_does_not_activate(tmp_path: Path) -> None:
    projects, page_id = _project_with_page(tmp_path)
    a1 = _attempt("a1", text="one")
    a2 = _attempt("a2", text="two", started="2020-01-02T00:00:00+00:00")
    projects.record_generation(page_id, a1, activate=True)
    projects.record_generation(page_id, a2, activate=True)
    result = projects.set_preferred_attempt(page_id, "a1", mode="prefer_only")
    assert result.preferred_attempt_id == "a1"
    assert result.active_attempt_id == "a2"
    assert result.effective_text() == "two"


def test_prefer_edit_gate_requires_choice(tmp_path: Path) -> None:
    projects, page_id = _project_with_page(tmp_path)
    a1 = _attempt("a1", text="one")
    a2 = _attempt("a2", text="two", started="2020-01-02T00:00:00+00:00")
    projects.record_generation(page_id, a1, activate=True)
    projects.save_user_edit(page_id, "human edit")
    projects.record_generation(page_id, a2, activate=True)
    with pytest.raises(ProjectError, match="edit_gate_choice"):
        projects.set_preferred_attempt(page_id, "a1", mode="prefer_promote_with_edit_gate")
    result = projects.set_preferred_attempt(
        page_id,
        "a1",
        mode="prefer_promote_with_edit_gate",
        edit_gate_choice="adopt_new",
    )
    assert result.active_attempt_id == "a1"
    assert result.edited_text is None
    assert result.effective_text() == "one"


def test_activate_false_preserves_active(tmp_path: Path) -> None:
    projects, page_id = _project_with_page(tmp_path)
    a1 = _attempt("a1", text="one")
    a2 = _attempt("a2", text="two", started="2020-01-02T00:00:00+00:00")
    projects.record_generation(page_id, a1, activate=True)
    projects.record_generation(page_id, a2, activate=False)
    result = projects.load_page_result(page_id)
    assert result is not None
    assert result.active_attempt_id == "a1"
    assert len(result.attempts) == 2


def test_set_active_does_not_clear_edit(tmp_path: Path) -> None:
    projects, page_id = _project_with_page(tmp_path)
    a1 = _attempt("a1", text="one")
    a2 = _attempt("a2", text="two", started="2020-01-02T00:00:00+00:00")
    projects.record_generation(page_id, a1, activate=True)
    projects.save_user_edit(page_id, "kept")
    projects.record_generation(page_id, a2, activate=True)
    result = projects.set_active_attempt(page_id, "a1")
    assert result.edited_text == "kept"
    assert result.effective_text() == "kept"


def test_rank_parser_rejects_malformed() -> None:
    allowed = {"a", "b"}
    assert _parse_rank_json('{"order":["a","b"]}', allowed) == ["a", "b"]
    assert _parse_rank_json('{"order":["a"]}', allowed) is None
    assert _parse_rank_json("not json", allowed) is None


def test_composite_validator_rejects_ungrounded() -> None:
    note = validate_composite_against_union(
        candidate="completely unrelated invention xyzzy",
        sources=["hello world notebook page"],
    )
    assert note is not None
    ok = validate_composite_against_union(
        candidate="hello notebook",
        sources=["hello world notebook page", "hello notebook notes"],
    )
    assert ok is None


def test_comparison_rejects_composite_in_rank(tmp_path: Path) -> None:
    from transcribe.domain.validation import validate_page_result
    from transcribe.errors import ValidationError

    a1 = _attempt("a1")
    c1 = _attempt("c1", kind="composite", sources=["a1"], text="merged")
    result = PageResult(
        page_id="p1",
        active_attempt_id="a1",
        attempts=[a1, c1],
        comparison=ComparisonRecord(
            pass_id="pass1",
            ranked_attempt_ids=["c1"],
            created_at="2020-01-01T00:00:00+00:00",
        ),
    )
    with pytest.raises(ValidationError, match="composite"):
        validate_page_result(result)


def test_preference_rollup(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    ledger = tmp_path / "ocr_preference_ledger.json"
    monkeypatch.setenv("TRANSCRIBE_DATA_DIR", str(tmp_path))
    append_preference_event(
        notebook_id="n1",
        page_id="p1",
        attempt_id="a1",
        model_name="model-a",
        model_digest=None,
        attempt_kind="vision",
        action="prefer",
        path=ledger,
    )
    append_preference_event(
        notebook_id="n1",
        page_id="p2",
        attempt_id="a2",
        model_name="model-a",
        model_digest=None,
        attempt_kind="composite",
        action="auto_composite",
        path=ledger,
    )
    stats = rollup_preference_stats(path=ledger)
    assert stats["model-a"].prefer_count == 2
    assert stats["model-a"].composite_prefer_count == 1
    assert stats["model-a"].pages_covered == 2
    hint = preference_hint_for_model("model-a", stats=stats)
    assert hint is not None
    assert "Preferred" in hint


def test_prune_keeps_preferred_and_active() -> None:
    attempts = [
        _attempt(f"a{i}", started=f"2020-01-{i+1:02d}T00:00:00+00:00", model=f"m{i}")
        for i in range(50)
    ]
    kept = prune_attempts(
        attempts,
        active_attempt_id="a0",
        preferred_attempt_id="a1",
        max_retained=40,
    )
    ids = {a.attempt_id for a in kept}
    assert "a0" in ids
    assert "a1" in ids
    assert len(kept) <= 40


def test_finetune_export(tmp_path: Path) -> None:
    projects, page_id = _project_with_page(tmp_path)
    a1 = _attempt("a1", text="preferred text", model="m1")
    a2 = _attempt("a2", text="other", model="m2", started="2020-01-02T00:00:00+00:00")
    projects.record_generation(page_id, a1, activate=True)
    projects.record_generation(page_id, a2, activate=False)
    projects.set_preferred_attempt(page_id, "a1", mode="prefer_only")
    out = FinetuneExportService(projects.paths, projects).export(
        tmp_path / "ft",
        options=FinetuneExportOptions(
            require_preferred=True,
            include_rejected_candidates=True,
        ),
    )
    samples = (out / "samples.jsonl").read_text(encoding="utf-8").strip().splitlines()
    assert len(samples) == 1
    row = json.loads(samples[0])
    assert row["text"] == "preferred text"
    assert row["source"]["model_name"] == "m1"
    assert len(row["rejected"]) == 1
    assert (out / "images" / f"{page_id}.png").is_file()
    manifest = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["format"] == "transcribe.finetune-export-manifest"
    assert manifest["sample_count"] == 1


def test_composite_stale_when_new_source_attempt_arrives() -> None:
    from transcribe.services.ocr_composite_state import (
        current_composite_attempt,
        is_composite_current,
        stale_composite_attempts,
    )

    a1 = _attempt("a1", text="one", model="m1")
    a2 = _attempt("a2", text="two", model="m2", started="2020-01-02T00:00:00+00:00")
    comp = _attempt(
        "c1",
        text="one two",
        model="merger",
        kind="composite",
        started="2020-01-03T00:00:00+00:00",
        pass_id="p1",
        sources=["a1", "a2"],
    )
    result = PageResult(page_id="p", active_attempt_id="c1", attempts=[a1, a2, comp])
    assert is_composite_current(comp, result)
    assert current_composite_attempt(result) is comp
    a3 = _attempt("a3", text="three", model="m1", started="2020-01-04T00:00:00+00:00")
    result.attempts.append(a3)
    assert not is_composite_current(comp, result)
    assert current_composite_attempt(result) is None
    stale = stale_composite_attempts(result)
    assert [a.attempt_id for a in stale] == ["c1"]


def test_save_mark_reviewed_and_invalidation(tmp_path: Path) -> None:
    projects, page_id = _project_with_page(tmp_path)
    a1 = _attempt("a1", text="hello world")
    projects.record_generation(page_id, a1, activate=True)
    saved = projects.save_user_edit(page_id, None, mark_reviewed=True)
    assert saved.reviewed_text_fingerprint
    assert saved.reviewed_evidence_fingerprint
    page = next(p for p in projects.load(reconcile=False).pages if p.page_id == page_id)
    assert page.review_status == "reviewed"

    projects.save_user_edit(page_id, "hello worlds", origin="human_corrected")
    page = next(p for p in projects.load(reconcile=False).pages if p.page_id == page_id)
    assert page.review_status == "needs_attention"

    projects.save_user_edit(page_id, "hello worlds", origin="human_corrected", mark_reviewed=True)
    a2 = _attempt("a2", text="hello world from b", model="m2", started="2020-01-02T00:00:00+00:00")
    projects.record_generation(page_id, a2, activate=False)
    page = next(p for p in projects.load(reconcile=False).pages if p.page_id == page_id)
    assert page.review_status == "needs_attention"

    projects.save_user_edit(page_id, "hello worlds", origin="human_corrected", mark_reviewed=True)
    projects.set_active_attempt(page_id, "a2")
    page = next(p for p in projects.load(reconcile=False).pages if p.page_id == page_id)
    assert page.review_status == "needs_attention"

    projects.save_user_edit(page_id, None, mark_reviewed=True)
    page = next(p for p in projects.load(reconcile=False).pages if p.page_id == page_id)
    assert page.review_status == "reviewed"
    projects.save_user_edit(page_id, "just save")
    page = next(p for p in projects.load(reconcile=False).pages if p.page_id == page_id)
    assert page.review_status == "needs_attention"


def test_save_alone_does_not_mark_reviewed(tmp_path: Path) -> None:
    projects, page_id = _project_with_page(tmp_path)
    a1 = _attempt("a1", text="hello")
    projects.record_generation(page_id, a1, activate=True)
    projects.save_user_edit(page_id, "hello there", origin="human_corrected")
    page = next(p for p in projects.load(reconcile=False).pages if p.page_id == page_id)
    assert (page.review_status or "unreviewed") == "unreviewed"
    result = projects.load_page_result(page_id)
    assert result is not None
    assert result.edited_text == "hello there"
    assert not result.reviewed_text_fingerprint


def test_cannot_set_reviewed_without_fingerprint_path(tmp_path: Path) -> None:
    projects, page_id = _project_with_page(tmp_path)
    with pytest.raises(ProjectError, match="mark reviewed"):
        projects.set_page_review_status(page_id, "reviewed")


def test_seed_editor_text_prefers_edited_overlay() -> None:
    from transcribe.services.ocr_composite_state import seed_editor_text

    a1 = _attempt("a1", text="vision text")
    result = PageResult(page_id="p", active_attempt_id="a1", attempts=[a1], edited_text="human")
    assert seed_editor_text(result) == "human"


def test_seed_editor_text_uses_current_composite_when_active() -> None:
    from transcribe.services.ocr_composite_state import seed_editor_text

    a1 = _attempt("a1", text="one", model="m1")
    a2 = _attempt("a2", text="two", model="m2", started="2020-01-02T00:00:00+00:00")
    comp = _attempt(
        "c1",
        text="merged draft",
        model="merger",
        kind="composite",
        started="2020-01-03T00:00:00+00:00",
        pass_id="p1",
        sources=["a1", "a2"],
    )
    result = PageResult(page_id="p", active_attempt_id="c1", attempts=[a1, a2, comp])
    assert seed_editor_text(result) == "merged draft"


def test_seed_editor_text_falls_back_from_stale_composite() -> None:
    from transcribe.services.ocr_composite_state import seed_editor_text

    a1 = _attempt("a1", text="old vision", model="m1")
    a2 = _attempt("a2", text="other vision", model="m2", started="2020-01-02T00:00:00+00:00")
    stale = _attempt(
        "c1",
        text="stale merge",
        model="merger",
        kind="composite",
        started="2020-01-03T00:00:00+00:00",
        pass_id="p1",
        sources=["a1", "a2"],
    )
    a3 = _attempt("a3", text="new vision", model="m1", started="2020-01-04T00:00:00+00:00")
    result = PageResult(page_id="p", active_attempt_id="c1", attempts=[a1, a2, stale, a3])
    assert seed_editor_text(result) == "new vision"


def test_repair_review_validity_downgrades_stale_review(tmp_path: Path) -> None:
    projects, page_id = _project_with_page(tmp_path)
    a1 = _attempt("a1", text="hello")
    projects.record_generation(page_id, a1, activate=True)
    projects.save_user_edit(page_id, None, mark_reviewed=True)
    page = next(p for p in projects.load(reconcile=False).pages if p.page_id == page_id)
    assert page.review_status == "reviewed"

    result = projects.load_page_result(page_id)
    assert result is not None
    result.reviewed_text_fingerprint = "corrupt"
    from transcribe.persistence.atomic import write_json_atomic

    write_json_atomic(projects.paths.result_path(page_id), result.as_dict())

    status = projects.repair_review_validity(page_id)
    assert status == "needs_attention"
    page = next(p for p in projects.load(reconcile=False).pages if p.page_id == page_id)
    assert page.review_status == "needs_attention"


def test_cache_alignment_signals_persists_counts(tmp_path: Path) -> None:
    projects, page_id = _project_with_page(tmp_path)
    a1 = _attempt("a1", text="hello")
    projects.record_generation(page_id, a1, activate=True)
    saved = projects.cache_alignment_signals(
        page_id, source_disagreement_count=4, agreement_ratio=0.75
    )
    assert saved.source_disagreement_count == 4
    assert saved.agreement_ratio == 0.75
    reloaded = projects.load_page_result(page_id)
    assert reloaded is not None
    assert reloaded.source_disagreement_count == 4
    assert reloaded.agreement_ratio == 0.75


def test_new_current_composite_invalidates_review(tmp_path: Path) -> None:
    projects, page_id = _project_with_page(tmp_path)
    a1 = _attempt("a1", text="one", model="m1")
    a2 = _attempt("a2", text="two", model="m2", started="2020-01-02T00:00:00+00:00")
    c1 = _attempt(
        "c1",
        text="one two",
        model="merger",
        kind="composite",
        started="2020-01-03T00:00:00+00:00",
        pass_id="p1",
        sources=["a1", "a2"],
    )
    projects.record_generation(page_id, a1, activate=False)
    projects.record_generation(page_id, a2, activate=False)
    projects.record_generation(page_id, c1, activate=True)
    projects.save_user_edit(page_id, None, mark_reviewed=True)
    c2 = _attempt(
        "c2",
        text="one two merged",
        model="merger",
        kind="composite",
        started="2020-01-05T00:00:00+00:00",
        pass_id="p1",
        sources=["a1", "a2"],
    )
    projects.record_generation(page_id, c2, activate=True)
    page = next(p for p in projects.load(reconcile=False).pages if p.page_id == page_id)
    assert page.review_status == "needs_attention"
    result = projects.load_page_result(page_id)
    assert result is not None
    from transcribe.services.ocr_composite_state import current_composite_attempt, stale_composite_attempts

    current = current_composite_attempt(result)
    assert current is not None and current.attempt_id == "c2"
    assert any(a.attempt_id == "c1" for a in stale_composite_attempts(result))


