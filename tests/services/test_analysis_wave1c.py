"""Topics & similarity tests (offline)."""

from __future__ import annotations

from pathlib import Path

from PIL import Image


from transcribe.analysis.modules.bertopic import BertopicModule
from transcribe.analysis.modules.semantic_similarity import SemanticSimilarityModule
from transcribe.analysis.modules.topic_shift import TopicShiftModule
from transcribe.analysis.parents import resolve_optional_parents
from transcribe.analysis.runner import AnalysisRunner
from transcribe.analysis.storage import AnalysisStorage
from transcribe.ingest import IngestService
from transcribe.services.project import ProjectService, open_project_paths
from tests.conftest import FakeClock, SequentialIds
from transcribe.analysis.modules import (
    get_registered_modules,
    THROUGH_OVERVIEW,
    THROUGH_LANGUAGE,
    THROUGH_THEMES,
    THROUGH_CORE,
)


def _png_bytes() -> bytes:
    from io import BytesIO

    img = Image.new("RGB", (32, 32), (10, 20, 30))
    buf = BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def _project_with_pages(tmp_path: Path, texts: list[str]):
    paths = open_project_paths(tmp_path / "proj")
    clock, ids = FakeClock(), SequentialIds("w1c")
    projects = ProjectService(paths, clock=clock, ids=ids)
    projects.create("notebook")
    ingest = IngestService(paths, clock=clock, ids=ids)
    for i, _ in enumerate(texts):
        ingest.import_bytes(f"p{i}.png", _png_bytes())
    project = projects.load()
    for page, text in zip(project.pages, texts, strict=True):
        projects.save_user_edit(page.page_id, text)
    return projects, AnalysisRunner(projects, clock=clock, ids=ids)


SHIFT_TEXTS = [
    "Gardens and flowers need water every morning for seedlings and soil.",
    "Gardens and flowers need water every morning for seedlings and soil.",
    "Terrible storms ruined the harvest yesterday and farmers postponed planting.",
]

NEAR_DUP = [
    "The quick brown fox jumps over the lazy dog near the river bank.",
    "A completely unrelated recipe for tomato soup with basil and garlic cloves.",
    "The quick brown fox jumps over the lazy dog near the river bank again.",
]


def test_registry_includes_1c_and_parents():
    w13 = get_registered_modules(through=THROUGH_OVERVIEW)
    w14 = get_registered_modules(through=THROUGH_LANGUAGE)
    w1c = get_registered_modules(through=THROUGH_THEMES)
    w1e = get_registered_modules(through=THROUGH_CORE)
    assert {"keyphrases", "entity_sentiment"}.issubset(set(w14))
    assert {
        "topic_modeling",
        "semantic_similarity",
        "topic_shift",
        "bertopic",
    }.issubset(set(w1c))
    assert set(w13).issubset(set(w1c))
    assert set(w1c).issubset(set(w1e))


def test_semantic_similarity_needs_two_units(tmp_path: Path):
    projects, runner = _project_with_pages(tmp_path, [SHIFT_TEXTS[0]])
    env = runner.run_module("semantic_similarity")
    assert env["outcome"] == "insufficient_data"
    assert env["capability"] == "insufficient_data"


def test_topic_shift_needs_two_units(tmp_path: Path):
    projects, runner = _project_with_pages(tmp_path, [SHIFT_TEXTS[0]])
    env = runner.run_module("topic_shift")
    assert env["outcome"] == "insufficient_data"


def test_semantic_similarity_matrix_and_motifs(tmp_path: Path):
    projects, runner = _project_with_pages(tmp_path, NEAR_DUP)
    env = runner.run_module("semantic_similarity")
    assert env["outcome"] == "success"
    payload = env["payload"]
    assert payload["schema"] == "semantic_similarity_payload_v1"
    assert payload["n_units"] == 3
    assert len(payload["matrix"]) == 3
    assert payload["matrix"][0][0] == 1.0
    # Pages 0 and 2 are near-duplicates → high similarity motif.
    assert any(
        {m["unit_id_a"], m["unit_id_b"]}
        and m["similarity"] >= payload["motif_threshold"]
        for m in payload["motifs"]
    )
    # Diagonal-adjacent near-dup pair should outrank unrelated.
    sim_02 = payload["matrix"][0][2]
    sim_01 = payload["matrix"][0][1]
    assert sim_02 > sim_01


def test_topic_shift_detects_order_boundary(tmp_path: Path):
    projects, runner = _project_with_pages(tmp_path, SHIFT_TEXTS)
    env = runner.run_module("topic_shift")
    assert env["outcome"] == "success"
    payload = env["payload"]
    assert payload["schema"] == "topic_shift_payload_v1"
    assert payload["n_units"] == 3
    assert len(payload["consecutive"]) == 2
    # First pair near-identical → no shift; second pair changes theme → shift.
    assert payload["consecutive"][0]["is_shift"] is False
    assert payload["consecutive"][1]["is_shift"] is True
    assert payload["n_shifts"] >= 1


def test_bertopic_unavailable_extra(tmp_path: Path):
    projects, runner = _project_with_pages(tmp_path, SHIFT_TEXTS)
    env = runner.run_module("bertopic")
    assert env["outcome"] == "skipped_not_applicable"
    assert env["capability"] == "unavailable_extra"
    assert env.get("payload") == {} or not env.get("payload", {}).get("topics")


def test_bertopic_baseline_ignores_keyphrases(tmp_path: Path):
    projects, runner = _project_with_pages(tmp_path, SHIFT_TEXTS)
    runner.run_module("keyphrases")
    storage = AnalysisStorage(projects.paths)
    parents = resolve_optional_parents(
        "bertopic", enrichment_mode="baseline", storage=storage
    )
    assert parents == []
    env = runner.run_module("bertopic")
    assert env["parents"] == []


def test_wave1c_batch_and_reopen(tmp_path: Path):
    projects, runner = _project_with_pages(tmp_path, SHIFT_TEXTS)
    batch = runner.run_batch(
        [
            "keyphrases",
            "topic_modeling",
            "semantic_similarity",
            "topic_shift",
            "bertopic",
        ]
    )
    assert batch["semantic_similarity"]["outcome"] == "success"
    assert batch["topic_shift"]["outcome"] == "success"
    assert batch["topic_modeling"]["outcome"] == "success"
    assert batch["bertopic"]["capability"] == "unavailable_extra"

    # Reopen: published artifacts still readable; cache hit on rerun.
    projects2 = ProjectService(projects.paths, clock=FakeClock(), ids=SequentialIds("w1c2"))
    runner2 = AnalysisRunner(projects2, clock=FakeClock(), ids=SequentialIds("w1c2b"))
    again = runner2.run_module("semantic_similarity")
    assert again["outcome"] == "success"
    assert again["cache_identity"] == batch["semantic_similarity"]["cache_identity"]


def test_cores_accept_analysis_document_only():
    from transcribe.analysis.document import AnalysisDocument, AnalysisUnit

    units = [
        AnalysisUnit(
            unit_id="u0",
            order=0,
            text="Alpha beta gamma garden flowers soil water.",
            date=None,
            source_ref={"kind": "page", "page_id": "p0"},
        ),
        AnalysisUnit(
            unit_id="u1",
            order=1,
            text="Storms harvest farmers planting decisions postpone.",
            date=None,
            source_ref={"kind": "page", "page_id": "p1"},
        ),
    ]
    doc = AnalysisDocument(
        document_id="doc",
        text="\n\n".join(u.text for u in units),
        units=units,
        granularity_version="page_v1",
        split_profile="page",
    )
    sim = SemanticSimilarityModule().run(doc)
    assert sim["outcome"] == "success"
    shift = TopicShiftModule().run(doc)
    assert shift["outcome"] == "success"
    ber = BertopicModule().run(doc)
    assert ber["capability_reason"] == "unavailable_extra"


def test_wave13_non_regression_with_1c(tmp_path: Path):
    projects, runner = _project_with_pages(tmp_path, SHIFT_TEXTS)
    for mid in get_registered_modules(through=THROUGH_OVERVIEW):
        env = runner.run_module(mid)
        assert env["outcome"] in {
            "success",
            "insufficient_data",
            "skipped_not_applicable",
        }, mid
        assert "error" not in (env.get("payload") or {}) or env["outcome"] != "failed"
