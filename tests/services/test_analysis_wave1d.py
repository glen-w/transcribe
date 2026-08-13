"""Emotion & salience tests (offline)."""

from __future__ import annotations

from pathlib import Path

from PIL import Image


from transcribe.analysis.modules.affect_tension import AffectTensionModule
from transcribe.analysis.modules.emotion import EmotionModule, score_emotion
from transcribe.analysis.modules.fine_grained_emotion import FineGrainedEmotionModule
from transcribe.analysis.modules.moments import MomentsModule
from transcribe.analysis.runner import AnalysisRunner
from transcribe.ingest import IngestService
from transcribe.services.project import ProjectService, open_project_paths
from tests.conftest import FakeClock, SequentialIds
from transcribe.analysis.modules import (
    get_registered_modules,
    THROUGH_THEMES,
    THROUGH_MOOD,
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
    clock, ids = FakeClock(), SequentialIds("w1d")
    projects = ProjectService(paths, clock=clock, ids=ids)
    projects.create("notebook")
    ingest = IngestService(paths, clock=clock, ids=ids)
    for i, _ in enumerate(texts):
        ingest.import_bytes(f"p{i}.png", _png_bytes())
    project = projects.load()
    for page, text in zip(project.pages, texts, strict=True):
        projects.save_user_edit(page.page_id, text)
    return projects, AnalysisRunner(projects, clock=clock, ids=ids)


AFFECTIVE = [
    "I am so happy and joyful about the wonderful success today.",
    "I feel sad and miserable with grief and lonely tears.",
    "Angry rage and furious hate make this a cruel disaster.",
]


def test_registry_includes_1d():
    w1c = get_registered_modules(through=THROUGH_THEMES)
    w1d = get_registered_modules(through=THROUGH_MOOD)
    w1e = get_registered_modules(through=THROUGH_CORE)
    assert {
        "emotion",
        "contextual_emotion",
        "fine_grained_emotion",
        "affect_tension",
        "moments",
    }.issubset(set(w1d))
    assert set(w1c).issubset(set(w1d))
    assert set(w1d).issubset(set(w1e))


def test_emotion_scores_and_empty(tmp_path: Path):
    scored = score_emotion("happy joyful wonderful love")
    assert scored["top_label"] == "joy"
    assert scored["intensity"] > 0
    projects, runner = _project_with_pages(tmp_path, AFFECTIVE)
    env = runner.run_module("emotion")
    assert env["outcome"] == "success"
    assert env["payload"]["schema"] == "emotion_payload_v1"
    assert len(env["payload"]["units"]) == 3

    empty, runner_e = _project_with_pages(tmp_path / "empty", ["   "])
    # blank OCR may yield insufficient via adapter; force empty units path via core
    from transcribe.analysis.document import AnalysisDocument

    assert (
        EmotionModule().run(
            AnalysisDocument(
                document_id="x",
                text="",
                units=[],
                granularity_version="page_v1",
                split_profile="page",
            )
        )["outcome"]
        == "insufficient_data"
    )
    _ = empty, runner_e


def test_contextual_emotion_neighbor_window(tmp_path: Path):
    projects, runner = _project_with_pages(tmp_path, AFFECTIVE)
    env = runner.run_module("contextual_emotion")
    assert env["outcome"] == "success"
    payload = env["payload"]
    assert payload["neighbor_window"] == 1
    assert payload["n_units"] == 3
    assert all(u["neighbor_count"] >= 1 for u in payload["units"])


def test_fine_grained_unavailable_extra(tmp_path: Path, monkeypatch):
    import transcribe.analysis.modules.fine_grained_emotion as fg

    monkeypatch.setattr(fg, "_transformer_emotion_available", lambda: False)
    projects, runner = _project_with_pages(tmp_path, AFFECTIVE)
    env = runner.run_module("fine_grained_emotion")
    assert env["outcome"] == "skipped_not_applicable"
    assert env["capability"] == "unavailable_extra"


def test_affect_tension_hard_parents(tmp_path: Path):
    projects, runner = _project_with_pages(tmp_path, AFFECTIVE)
    missing = runner.run_module("affect_tension")
    assert missing["outcome"] == "unavailable_dependency"
    runner.run_batch(["sentiment", "emotion"])
    env = runner.run_module("affect_tension")
    assert env["outcome"] == "success"
    assert env["payload"]["schema"] == "affect_tension_payload_v1"
    assert len(env["payload"]["units"]) == 3


def test_moments_reduced_and_enriched(tmp_path: Path):
    projects, runner = _project_with_pages(tmp_path, AFFECTIVE)
    bare = runner.run_module("moments")
    assert bare["outcome"] == "success"
    assert bare.get("partial") is True
    assert any(w.get("code") == "reduced_soft_features" for w in bare.get("warnings") or [])
    assert bare["payload"]["n_moments"] >= 1
    assert bare.get("evidence")

    runner.run_batch(["sentiment", "emotion", "topic_shift"])
    rich = runner.run_module("moments")
    assert rich["outcome"] == "success"
    soft = rich["payload"]["soft_features_present"]
    assert soft["emotion"] is True
    assert soft["sentiment"] is True
    parent_ids = {p["module_id"] for p in rich.get("parents") or []}
    assert {"emotion", "sentiment"}.issubset(parent_ids)


def test_wave1d_batch_and_cache(tmp_path: Path):
    projects, runner = _project_with_pages(tmp_path, AFFECTIVE)
    batch = runner.run_batch(
        [
            "sentiment",
            "emotion",
            "contextual_emotion",
            "fine_grained_emotion",
            "affect_tension",
            "topic_shift",
            "moments",
        ]
    )
    assert batch["emotion"]["outcome"] == "success"
    assert batch["affect_tension"]["outcome"] == "success"
    assert batch["moments"]["outcome"] == "success"
    assert batch["fine_grained_emotion"]["capability"] == "unavailable_extra"

    again = runner.run_module("emotion")
    assert again["cache_identity"] == batch["emotion"]["cache_identity"]


def test_cores_no_page_imports():
    from transcribe.analysis.document import (
        AnalysisDocument,
        AnalysisUnit,
        concatenate_document_text,
    )

    units = [
        AnalysisUnit(
            unit_id="u0",
            order=0.0,
            text="Happy wonderful joy and grateful trust.",
            date=None,
            source_ref={"kind": "page", "page_id": "p0"},
        ),
        AnalysisUnit(
            unit_id="u1",
            order=1.0,
            text="Sad miserable grief and lonely tears.",
            date=None,
            source_ref={"kind": "page", "page_id": "p1"},
        ),
    ]
    doc = AnalysisDocument(
        document_id="d",
        text=concatenate_document_text(units),
        units=units,
        granularity_version="page_v1",
        split_profile="page",
    )
    assert EmotionModule().run(doc)["outcome"] == "success"
    assert MomentsModule().run(doc)["outcome"] == "success"
    emo = EmotionModule().run(doc)["payload"]
    sent = {
        "units": [
            {"unit_id": "u0", "compound": 0.8, "label": "positive"},
            {"unit_id": "u1", "compound": -0.7, "label": "negative"},
        ]
    }
    tension = AffectTensionModule().run(doc, parents={"emotion": emo, "sentiment": sent})
    assert tension["outcome"] == "success"
    assert FineGrainedEmotionModule().run(doc)["capability_reason"] == "unavailable_extra"
