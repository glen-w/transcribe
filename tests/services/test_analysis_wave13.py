"""Overview language foundations tests."""

from __future__ import annotations

from pathlib import Path

from PIL import Image

from transcribe.analysis.adapter import build_page_v1_document
from transcribe.analysis.cache_identity import (
    build_cache_identity_object,
    cache_identity_hex,
)
from transcribe.analysis.document import (
    AnalysisDocument,
    AnalysisUnit,
    content_fingerprint,
)
from transcribe.analysis.eligibility import evaluate_notebook_eligibility_v1
from transcribe.analysis.modules import (
    THROUGH_FOUNDATIONS,
    THROUGH_OVERVIEW,
    THROUGH_WORDCLOUDS,
    get_registered_modules,
)
from transcribe.analysis.modules.epistemic_markers import EpistemicMarkersModule
from transcribe.analysis.modules.ner import NERModule
from transcribe.analysis.modules.sentiment import SentimentModule, score_sentiment
from transcribe.analysis.runner import AnalysisRunner, _module_provenance
from transcribe.ingest import IngestService
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
    clock, ids = FakeClock(), SequentialIds("w13")
    projects = ProjectService(paths, clock=clock, ids=ids)
    projects.create("notebook")
    ingest = IngestService(paths, clock=clock, ids=ids)
    for i, _ in enumerate(texts):
        ingest.import_bytes(f"p{i}.png", _png_bytes())
    project = projects.load()
    for page, text in zip(project.pages, texts, strict=True):
        projects.save_user_edit(page.page_id, text)
    return projects, AnalysisRunner(projects, clock=clock, ids=ids)


def _doc(units: list[tuple[str, str]], *, doc_id: str = "d1") -> AnalysisDocument:
    from transcribe.analysis.document import concatenate_document_text

    analysis_units = []
    for i, (uid, text) in enumerate(units):
        analysis_units.append(
            AnalysisUnit(
                unit_id=uid,
                order=float(i),
                text=text,
                source_ref={"kind": "page", "page_id": uid},
                date=None,
            )
        )
    return AnalysisDocument(
        document_id=doc_id,
        text=concatenate_document_text(analysis_units),
        units=analysis_units,
        granularity_version="page_v1",
        split_profile="page",
    )


def test_registry_wave_slices():
    assert set(get_registered_modules(through=THROUGH_FOUNDATIONS)) == {
        "stats",
        "lexical_diversity",
        "understandability",
    }
    w12 = get_registered_modules(through=THROUGH_WORDCLOUDS)
    assert "wordclouds" in w12
    assert "ner" not in w12
    w13 = get_registered_modules(through=THROUGH_OVERVIEW)
    assert {"ner", "sentiment", "epistemic_markers"}.issubset(set(w13))
    assert set(w12).issubset(set(w13))
    assert set(get_registered_modules()) >= set(w13)
    assert set(w13).issubset(set(get_registered_modules()))


def test_sentiment_golden_and_order():
    doc = _doc(
        [
            ("p0", "This is a terrible awful day."),
            ("p1", "I am happy and grateful for wonderful success."),
        ]
    )
    result = SentimentModule().run(doc)
    assert result["outcome"] == "success"
    units = result["payload"]["units"]
    assert units[0]["order"] == 0.0
    assert units[1]["order"] == 1.0
    assert units[0]["compound"] < units[1]["compound"]
    assert units[0]["label"] == "negative"
    assert units[1]["label"] == "positive"
    again = SentimentModule().run(doc)
    assert again == result


def test_sentiment_empty_insufficient():
    empty = AnalysisDocument(
        document_id="e",
        text="",
        units=[],
        granularity_version="page_v1",
        split_profile="page",
    )
    assert SentimentModule().run(empty)["outcome"] == "insufficient_data"


def test_epistemic_markers_hits_and_evidence():
    doc = _doc([("p0", "I think maybe this is sort of fine. Definitely not.")])
    result = EpistemicMarkersModule().run(doc)
    assert result["outcome"] == "success"
    payload = result["payload"]
    assert payload["global_stats"]["total_marker_hits"] >= 3
    assert result["evidence"]
    for ev in result["evidence"]:
        assert ev["unit_id"] == "p0"
        assert ev["quote"]
        assert ev["content_fingerprint"] == content_fingerprint(doc)
        assert "source_ref" in ev


def test_ner_unavailable_without_spacy(monkeypatch):
    doc = _doc([("p0", "Alice met Bob in Paris.")])
    import transcribe.analysis.modules.ner as ner_mod

    monkeypatch.setattr(ner_mod, "_try_spacy_extract", lambda _text: None)
    result = NERModule().run(doc)
    assert result["outcome"] == "skipped_not_applicable"
    assert result["capability_reason"] == "unavailable_extra"


def test_ner_with_injected_extractor_and_empty_success():
    def fake_extract(text: str):
        if "Alice" in text:
            i = text.index("Alice")
            return [("Alice", "PERSON", i, i + 5)]
        return []

    doc = _doc([("p0", "Alice wrote notes."), ("p1", "Nothing named here.")])
    result = NERModule(extract_fn=fake_extract).run(doc)
    assert result["outcome"] == "success"
    assert result["payload"]["entity_counts"]["Alice"] == 1
    assert result["evidence"][0]["quote"] == "Alice"

    empty_ents = NERModule(extract_fn=lambda _t: []).run(doc)
    assert empty_ents["outcome"] == "success"
    assert empty_ents["payload"]["entities"] == []


def test_ungated_modules_ignore_eligibility_rejection(tmp_path: Path):
    # Short units that eligibility would mark too_short still run for 1.3 modules.
    projects, runner = _project_with_pages(tmp_path, ["Hi", "Ok"])
    project = projects.load()
    doc = build_page_v1_document(project, projects)
    elig = evaluate_notebook_eligibility_v1(doc.units)
    # Even if few/no eligible units, ungated modules must not consult eligibility.
    assert "eligible_unit_ids" in elig

    sent = runner.run_module("sentiment")
    assert sent["outcome"] in {"success", "insufficient_data"}
    assert "eligibility" not in (sent.get("payload") or {})
    epi = runner.run_module("epistemic_markers")
    assert epi["outcome"] in {"success", "insufficient_data"}


def test_runner_publishes_sentiment_and_wave12_non_regression(tmp_path: Path):
    texts = [
        "I love this wonderful notebook page.",
        "This is a terrible bad entry with worry.",
        "Neutral text about notebooks and ink.",
    ]
    projects, runner = _project_with_pages(tmp_path, texts)
    batch = runner.run_batch(["stats", "wordclouds", "sentiment", "epistemic_markers", "ner"])
    assert batch["stats"]["outcome"] == "success"
    assert batch["wordclouds"]["outcome"] == "success"
    assert batch["sentiment"]["outcome"] == "success"
    assert batch["epistemic_markers"]["outcome"] == "success"
    # ner may be unavailable_extra without spaCy
    assert batch["ner"]["outcome"] in {"success", "skipped_not_applicable"}
    if batch["ner"]["outcome"] == "skipped_not_applicable":
        assert batch["ner"]["capability"] == "unavailable_extra"

    # 1.2 wordclouds still baseline / no parents
    assert batch["wordclouds"]["parents"] == []
    assert batch["wordclouds"]["payload"]["enrichment_mode"] == "baseline"


def test_ner_evidence_stale_after_edit(tmp_path: Path):
    projects, runner = _project_with_pages(tmp_path, ["Alice visited Paris today."])

    def fake_extract(text: str):
        out = []
        for name, label in (("Alice", "PERSON"), ("Paris", "GPE")):
            if name in text:
                i = text.index(name)
                out.append((name, label, i, i + len(name)))
        return out

    import transcribe.analysis.runner as runner_mod

    original = runner_mod.get_registered_modules

    def patched(*, through=None):
        base = original(through=through)
        base["ner"] = NERModule(extract_fn=fake_extract)
        return base

    runner_mod.get_registered_modules = patched  # type: ignore[assignment]
    try:
        env = runner.run_module("ner")
        assert env["outcome"] == "success"
        assert env.get("evidence")
        old_fp = env["evidence"][0]["content_fingerprint"]
        page_id = projects.load().pages[0].page_id
        projects.save_user_edit(page_id, "Bob visited London today.")
        doc2 = build_page_v1_document(projects.load(), projects)
        new_fp = content_fingerprint(doc2)
        assert new_fp != old_fp
        assert all(e["content_fingerprint"] != new_fp for e in env["evidence"])
    finally:
        runner_mod.get_registered_modules = original  # type: ignore[assignment]


def test_provenance_pins_for_language_modules():
    for mid in ("ner", "sentiment", "epistemic_markers"):
        mod = get_registered_modules(through=THROUGH_OVERVIEW)[mid]
        prov = _module_provenance(mod)
        assert prov["ported_from"]["commit"] == "50a0ede8e7acd03bbd9125a5a5237049f3291304"
        assert prov["semantic_class"] == "adaptation"
        assert prov["ported_from"]["files"]


def test_score_sentiment_deterministic():
    a = score_sentiment("happy wonderful love")
    b = score_sentiment("happy wonderful love")
    assert a == b
    assert a["compound"] > 0


def test_runner_publishes_epistemic_evidence_on_envelope(tmp_path: Path):
    projects, runner = _project_with_pages(tmp_path, ["I think maybe this is sort of fine."])
    env = runner.run_module("epistemic_markers")
    assert env["outcome"] == "success"
    assert env.get("published") is True or env.get("attempt_state") == "succeeded"
    evidence = env.get("evidence") or []
    assert evidence
    assert all("content_fingerprint" in e and "source_ref" in e for e in evidence)
    # parents stay empty for ungated 1.3 modules
    assert env.get("parents") == []


def test_sentiment_cache_identity_includes_lexicon_digest(tmp_path: Path):
    projects, runner = _project_with_pages(tmp_path, ["happy wonderful day"])
    env = runner.run_module("sentiment")
    assert env["outcome"] == "success"
    from transcribe.analysis.modules.sentiment import (
        sentiment_config,
        sentiment_lexicon_or_model,
    )

    project = projects.load()
    doc = build_page_v1_document(project, projects)
    mod = SentimentModule()
    identity = cache_identity_hex(
        build_cache_identity_object(
            project_id=project.id,
            module_id=mod.module_id,
            module_version=mod.module_version,
            document=doc,
            config=sentiment_config(),
            parents=[],
            lexicon_or_model=sentiment_lexicon_or_model(),
        )
    )
    assert env["cache_identity"] == identity
    assert "lexicon_digest" in sentiment_config()


def test_unavailable_extra_capability_on_envelope(tmp_path: Path, monkeypatch):
    import transcribe.analysis.modules.ner as ner_mod

    monkeypatch.setattr(ner_mod, "_try_spacy_extract", lambda _text: None)
    projects, runner = _project_with_pages(tmp_path, ["Alice met Bob."])
    env = runner.run_module("ner")
    assert env["outcome"] == "skipped_not_applicable"
    assert env["capability"] == "unavailable_extra"
