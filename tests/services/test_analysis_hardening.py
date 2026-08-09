"""Wave 1 analysis hardening — parent freshness, evidence, boundaries, invalidation."""

from __future__ import annotations

import ast
from pathlib import Path

import pytest
from PIL import Image

from transcribe.analysis.document import (
    AnalysisDocument,
    AnalysisDocumentError,
    AnalysisUnit,
    validate_analysis_document,
)
from transcribe.analysis.eligibility import (
    eligibility_fingerprint,
    evaluate_notebook_eligibility_v1,
)
from transcribe.analysis.envelope import CAPABILITIES, derive_capability, filter_live_evidence
from transcribe.analysis.modules.stats import StatsModule
from transcribe.analysis.runner import (
    ELIGIBILITY_REQUIRED,
    AnalysisRunner,
    load_published_read_model,
)
from transcribe.analysis.storage import AnalysisStorage
from transcribe.domain.models import Project
from transcribe.ingest import IngestService
from transcribe.persistence.atomic import read_json, write_json_atomic
from transcribe.persistence.locks import mutation_lock
from transcribe.persistence.schema import require_format
from transcribe.services.project import ProjectService, open_project_paths
from tests.conftest import FakeClock, SequentialIds


def _png_bytes() -> bytes:
    from io import BytesIO

    img = Image.new("RGB", (32, 32), (10, 20, 30))
    buf = BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def _project_with_pages(tmp_path: Path, texts: list[str]):
    paths = open_project_paths(tmp_path / "proj")
    clock, ids = FakeClock(), SequentialIds("hard")
    projects = ProjectService(paths, clock=clock, ids=ids)
    projects.create("notebook")
    ingest = IngestService(paths, clock=clock, ids=ids)
    for i, _ in enumerate(texts):
        ingest.import_bytes(f"p{i}.png", _png_bytes())
    project = projects.load()
    for page, text in zip(project.pages, texts, strict=True):
        projects.save_user_edit(page.page_id, text)
    return projects, AnalysisRunner(projects, clock=clock, ids=ids)


TEXTS = [
    "Alice met Bob in Paris about gardens and soil moisture.",
    "Carol discussed water retention and compost with delight.",
    "Dana felt sad about weeds but hopeful for spring blooms.",
]


def test_stale_hard_parents_unavailable_dependency(tmp_path: Path):
    projects, runner = _project_with_pages(tmp_path, TEXTS)
    assert runner.run_module("ner")["outcome"] == "success"
    assert runner.run_module("sentiment")["outcome"] == "success"
    assert runner.run_module("entity_sentiment")["outcome"] == "success"

    page0 = projects.load().pages[0].page_id
    projects.save_user_edit(page0, "Completely rewritten page about astronomy and moons.")

    env = runner.run_module("entity_sentiment")
    assert env["outcome"] == "unavailable_dependency"
    assert env["capability"] == "unavailable_dependency"
    err = (env.get("payload") or {}).get("error") or {}
    assert "ner" in (err.get("stale_parents") or []) or "sentiment" in (
        err.get("stale_parents") or []
    )


def test_stale_highlights_blocks_summary(tmp_path: Path):
    projects, runner = _project_with_pages(tmp_path, TEXTS)
    assert runner.run_module("highlights")["outcome"] == "success"
    assert runner.run_module("summary")["outcome"] == "success"

    page0 = projects.load().pages[0].page_id
    projects.save_user_edit(page0, "New notebook text that invalidates prior highlights.")

    env = runner.run_module("summary")
    assert env["outcome"] == "unavailable_dependency"
    stale = ((env.get("payload") or {}).get("error") or {}).get("stale_parents") or []
    assert "highlights" in stale


def test_moments_prefer_paragraph_v1(tmp_path: Path):
    projects, runner = _project_with_pages(
        tmp_path,
        ["First block about gardens.\n\nSecond block about soil moisture and water."],
    )
    env = runner.run_module("moments")
    assert env["outcome"] == "success"
    evidence = env.get("evidence") or []
    assert evidence
    assert evidence[0]["source_ref"]["kind"] == "page_span"
    assert "/span:" in evidence[0]["unit_id"]


def test_failed_outcome_never_publishes(tmp_path: Path):
    projects, runner = _project_with_pages(tmp_path, TEXTS)
    ok = runner.run_module("stats")
    assert ok["outcome"] == "success"
    assert ok.get("published") is True
    prior_attempt = ok["attempt_id"]

    storage = AnalysisStorage(projects.paths)
    refused = storage.publish_if_current(
        module_id="stats",
        envelope={
            **ok,
            "attempt_state": "failed",
            "outcome": "failed",
            "attempt_id": "fake-fail",
            "published": False,
        },
        expected_cache_identity=ok["cache_identity"],
        current_cache_identity=ok["cache_identity"],
    )
    assert refused is False
    published = storage.read_published("stats")
    assert published is not None
    assert published["attempt_id"] == prior_attempt
    assert published["outcome"] == "success"


def test_module_exception_preserves_published(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    projects, runner = _project_with_pages(tmp_path, TEXTS)
    ok = runner.run_module("stats")
    assert ok["outcome"] == "success"
    prior = ok["attempt_id"]

    def boom(*_a, **_k):
        raise RuntimeError("simulated crash")

    monkeypatch.setattr(StatsModule, "run", boom)
    # Force cache miss so run() is invoked.
    page0 = projects.load().pages[0].page_id
    projects.save_user_edit(page0, TEXTS[0] + " extra tokens for crash path.")
    failed = runner.run_module("stats")
    assert failed["outcome"] == "failed"
    assert failed.get("published") is not True
    published = AnalysisStorage(projects.paths).read_published("stats")
    assert published is not None
    assert published["attempt_id"] == prior
    assert published["outcome"] == "success"


def test_page_reorder_invalidates_cache(tmp_path: Path):
    projects, runner = _project_with_pages(tmp_path, TEXTS)
    first = runner.run_module("stats")
    assert first["outcome"] == "success"
    fp1 = first["content_fingerprint"]
    identity1 = first["cache_identity"]

    with mutation_lock(projects.paths.mutation_lock):
        payload = require_format(read_json(projects.paths.manifest), "transcribe.project")
        current = Project.from_dict(payload)
        current.pages = list(reversed(current.pages))
        write_json_atomic(projects.paths.manifest, current.as_dict())

    second = runner.run_module("stats")
    assert second["outcome"] == "success"
    assert second["content_fingerprint"] != fp1
    assert second["cache_identity"] != identity1


def test_eligibility_reasons_and_fingerprint():
    units = [
        AnalysisUnit(
            unit_id="a",
            text="ok long enough",
            order=0.0,
            source_ref={"kind": "page", "page_id": "a"},
        ),
        AnalysisUnit(
            unit_id="b",
            text="  ",
            order=1.0,
            source_ref={"kind": "page", "page_id": "b"},
        ),
        AnalysisUnit(
            unit_id="c",
            text="ab",
            order=2.0,
            source_ref={"kind": "page", "page_id": "c"},
        ),
        AnalysisUnit(
            unit_id="d",
            text="excluded page text here",
            order=3.0,
            source_ref={"kind": "page", "page_id": "d"},
        ),
    ]
    out = evaluate_notebook_eligibility_v1(units, excluded_page_ids={"d"})
    by_id = {d["unit_id"]: d for d in out["decisions"]}
    assert by_id["a"]["reason"] == "ok"
    assert by_id["b"]["reason"] == "empty_or_whitespace"
    assert by_id["c"]["reason"] == "too_short"
    assert by_id["d"]["reason"] == "excluded"
    fp = eligibility_fingerprint(out)
    assert len(fp) == 64


def test_eligibility_required_modules_skip_when_empty(tmp_path: Path):
    # All units too short → eligibility empty for required modules.
    projects, runner = _project_with_pages(tmp_path, ["a", "b", "c"])
    for mid in sorted(ELIGIBILITY_REQUIRED):
        if mid == "bertopic":
            # Still goes through eligibility before optional-extra check.
            env = runner.run_module(mid)
        elif mid == "insights":
            # Needs parents; eligibility skip happens before hard parents when empty.
            env = runner.run_module(mid)
        else:
            env = runner.run_module(mid)
        assert env["outcome"] == "skipped_not_applicable", mid
        assert env["capability"] == "skipped_not_applicable", mid
        assert env["capability"] in CAPABILITIES


def test_emotion_lexicon_on_envelope(tmp_path: Path):
    projects, runner = _project_with_pages(tmp_path, TEXTS)
    env = runner.run_module("emotion")
    assert env["outcome"] == "success"
    assert env.get("lexicon_or_model") is not None
    assert env["lexicon_or_model"].get("lexicon_id") == "emotion_lexicon_v1"


def test_filter_live_evidence_and_read_model(tmp_path: Path):
    assert filter_live_evidence(None, current_content_fingerprint="abc") == []
    assert filter_live_evidence([{"content_fingerprint": "x"}], current_content_fingerprint=None) == []
    live = filter_live_evidence(
        [
            {"content_fingerprint": "abc", "quote": "a"},
            {"content_fingerprint": "zzz", "quote": "b"},
        ],
        current_content_fingerprint="abc",
    )
    assert len(live) == 1
    assert live[0]["quote"] == "a"

    projects, runner = _project_with_pages(tmp_path, TEXTS)
    env = runner.run_module("ner")
    assert env["outcome"] == "success"
    storage = AnalysisStorage(projects.paths)
    identity = runner.planned_cache_identity("ner")
    rm = load_published_read_model(
        storage, "ner", current_cache_identity=identity
    )
    assert rm["status"] == "ok"
    stale = load_published_read_model(
        storage, "ner", current_cache_identity="deadbeef"
    )
    assert stale["status"] == "stale"
    assert stale["live_evidence"] == []


def test_page_span_length_must_match_unit_text():
    bad = AnalysisDocument(
        document_id="x",
        text="hello",
        units=[
            AnalysisUnit(
                unit_id="p/span:0-5",
                text="hello",
                order=0.0,
                source_ref={
                    "kind": "page_span",
                    "page_id": "p",
                    "char_start": 0,
                    "char_end": 9,
                },
            )
        ],
    )
    with pytest.raises(AnalysisDocumentError) as exc:
        validate_analysis_document(bad)
    assert exc.value.code == "invalid_source_ref"


def test_derive_capability_skipped_listed():
    assert derive_capability(outcome="skipped_not_applicable") == "skipped_not_applicable"
    assert derive_capability(outcome="skipped_not_applicable") in CAPABILITIES


def test_analysis_package_boundary_no_ui_leaks():
    root = Path(__file__).resolve().parents[2] / "src" / "transcribe" / "analysis"
    forbidden = {"streamlit", "transcribe.ui"}
    core_forbidden_names = {"PageIndex", "ProjectService"}
    for path in root.rglob("*.py"):
        if path.name == "adapter.py":
            # Adapter may touch PageIndex / ProjectService.
            src = path.read_text(encoding="utf-8")
            tree = ast.parse(src)
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        assert alias.name.split(".")[0] != "streamlit"
                if isinstance(node, ast.ImportFrom):
                    mod = node.module or ""
                    assert not mod.startswith("streamlit")
                    assert not mod.startswith("transcribe.ui")
            continue
        src = path.read_text(encoding="utf-8")
        tree = ast.parse(src)
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    top = alias.name.split(".")[0]
                    assert top != "streamlit", path
                    assert alias.name not in forbidden, path
            if isinstance(node, ast.ImportFrom):
                mod = node.module or ""
                assert not mod.startswith("streamlit"), path
                assert not mod.startswith("transcribe.ui"), path
                if path.parent.name == "modules" or path.name in {
                    "document.py",
                    "chunking.py",
                    "eligibility.py",
                }:
                    for alias in node.names:
                        assert alias.name not in core_forbidden_names, path
