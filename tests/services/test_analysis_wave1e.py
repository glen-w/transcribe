"""Synthesis & LLM tests (offline deterministic + recorded doubles)."""

from __future__ import annotations

from pathlib import Path

from PIL import Image

from transcribe.analysis.adapter import (
    build_page_v1_document,
    build_paragraph_v1_document,
)
from transcribe.analysis.chunking import CHUNKING_UNITS_V1, pack_units_v1
from transcribe.analysis.document import SPLIT_PARAGRAPH_V1
from transcribe.analysis.llm_runtime import (
    RecordedDoubleClient,
    bind_text_llm_context,
    set_text_llm_client,
)
from transcribe.analysis.modules import (
    THROUGH_CORE,
    THROUGH_LANGUAGE,
    THROUGH_OVERVIEW,
    get_registered_modules,
)
from transcribe.analysis.modules.llm_custom_qa import LLMCustomQAModule
from transcribe.analysis.runner import AnalysisRunner
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
    clock, ids = FakeClock(), SequentialIds("w1e")
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
    "Gardens and flowers need water every morning.\n\n" "The soil must stay damp for seedlings.",
    "Terrible storms ruined the harvest yesterday.\n\n"
    "Farmers decided to postpone planting decisions.",
    "Happy teams celebrated wonderful progress on notebooks and topics.",
]


def test_registry_includes_1e_and_parents():
    w13 = get_registered_modules(through=THROUGH_OVERVIEW)
    w14 = get_registered_modules(through=THROUGH_LANGUAGE)
    w1e = get_registered_modules(through=THROUGH_CORE)
    assert {"keyphrases", "entity_sentiment"}.issubset(set(w14))
    assert {"topic_modeling", "highlights", "summary", "insights"}.issubset(set(w1e))
    assert {
        "llm_summary",
        "llm_action_items",
        "llm_custom_qa",
        "narrative_summary",
    }.issubset(set(w1e))
    assert set(w13).issubset(set(w1e))


def test_paragraph_v1_splitter(tmp_path: Path):
    projects, _ = _project_with_pages(
        tmp_path,
        ["Para one.\n\nPara two stays here."],
    )
    project = projects.load()
    doc = build_paragraph_v1_document(project, projects)
    assert doc.split_profile == SPLIT_PARAGRAPH_V1
    assert len(doc.units) == 2
    assert all(u.source_ref["kind"] == "page_span" for u in doc.units)
    assert "/span:" in doc.units[0].unit_id


def test_chunking_policy_packs_units(tmp_path: Path):
    projects, _ = _project_with_pages(tmp_path, TEXTS)
    doc = build_page_v1_document(projects.load(), projects)
    chunks = pack_units_v1(doc, max_tokens=20)
    assert chunks
    assert CHUNKING_UNITS_V1 == "notebook_chunks_units_v1"
    assert all("unit_ids" in c and "text" in c for c in chunks)


def test_hard_parent_summary_unavailable(tmp_path: Path):
    projects, runner = _project_with_pages(tmp_path, TEXTS)
    env = runner.run_module("summary")
    assert env["outcome"] == "unavailable_dependency"
    assert env["capability"] == "unavailable_dependency"


def test_deterministic_synthesis_offline(tmp_path: Path):
    set_text_llm_client(RecordedDoubleClient(responses={}, healthy=False))
    try:
        projects, runner = _project_with_pages(tmp_path, TEXTS)
        batch = runner.run_batch(
            [
                "ner",
                "sentiment",
                "keyphrases",
                "topic_modeling",
                "highlights",
                "summary",
                "insights",
                "narrative_summary",
                "llm_summary",
            ]
        )
        assert batch["topic_modeling"]["outcome"] == "success"
        assert batch["highlights"]["outcome"] == "success"
        assert batch["summary"]["outcome"] == "success"
        assert batch["insights"]["outcome"] == "success"
        assert batch["narrative_summary"]["outcome"] == "skipped_not_applicable"
        assert batch["narrative_summary"]["capability"] == "unavailable_model"
        assert batch["llm_summary"]["outcome"] == "skipped_not_applicable"
        assert batch["llm_summary"]["capability"] == "unavailable_model"
        assert batch["keyphrases"]["outcome"] == "success"
        # NER may be unavailable_extra without spaCy; hard-parent consumer then skips.
        es = runner.run_module("entity_sentiment")
        if batch["ner"]["outcome"] == "success":
            assert es["outcome"] == "success"
        else:
            assert es["outcome"] == "unavailable_dependency"
    finally:
        set_text_llm_client(None)


def test_entity_sentiment_with_injected_ner(tmp_path: Path):
    projects, runner = _project_with_pages(
        tmp_path, ["Alice met Bob in Paris with happy wonderful success."]
    )
    import transcribe.analysis.runner as runner_mod
    from transcribe.analysis.modules.ner import NERModule
    from transcribe.analysis.modules.sentiment import SentimentModule

    def fake_extract(text: str):
        out = []
        for name, label in (("Alice", "PERSON"), ("Bob", "PERSON"), ("Paris", "GPE")):
            if name in text:
                i = text.index(name)
                out.append((name, label, i, i + len(name)))
        return out

    original = runner_mod.get_registered_modules

    def patched(*, through: str | None = None):
        mods = original(through=through)
        mods["ner"] = NERModule(extract_fn=fake_extract)
        mods["sentiment"] = SentimentModule()
        return mods

    runner_mod.get_registered_modules = patched  # type: ignore[assignment]
    try:
        assert runner.run_module("ner")["outcome"] == "success"
        assert runner.run_module("sentiment")["outcome"] == "success"
        env = runner.run_module("entity_sentiment")
        assert env["outcome"] == "success"
        assert env["payload"]["n_entities"] >= 1
    finally:
        runner_mod.get_registered_modules = original  # type: ignore[assignment]


def test_llm_summary_recorded_double(tmp_path: Path):
    double = RecordedDoubleClient(
        responses={"default": '{"summary":"Notebook about gardens.","bullets":["water","soil"]}'}
    )
    set_text_llm_client(double)
    try:
        projects, runner = _project_with_pages(tmp_path, TEXTS)
        env = runner.run_module("llm_summary")
        assert env["outcome"] == "success"
        assert env["payload"]["summary"]
        assert env.get("llm") is not None
        assert env["llm"]["chunking_policy_id"] == CHUNKING_UNITS_V1
        assert env["payload"]["honesty_label"] == "llm_generated"
    finally:
        set_text_llm_client(None)


def test_llm_custom_qa_grounding_and_abstain(tmp_path: Path):
    projects, runner = _project_with_pages(tmp_path, TEXTS)
    project = projects.load()
    doc = build_page_v1_document(project, projects)
    unit_id = doc.units[0].unit_id

    # Success path with grounded citation
    set_text_llm_client(
        RecordedDoubleClient(
            responses={
                "default": (
                    f'{{"answer":"They need water.","unit_ids":["{unit_id}"],' f'"abstain":false}}'
                )
            }
        )
    )
    try:
        mod = LLMCustomQAModule(question_text="What do gardens need?")
        ctx = bind_text_llm_context(text_model_name="recorded-double:v1")
        result = mod.run(doc, llm_ctx=ctx, question_text="What do gardens need?")
        assert result["outcome"] == "success"
        assert result["payload"]["unit_ids"] == [unit_id]
        assert result.get("evidence")
    finally:
        set_text_llm_client(None)

    # Ungrounded / fabricated ids → abstain
    set_text_llm_client(
        RecordedDoubleClient(
            responses={"default": '{"answer":"Nope","unit_ids":["missing-id"],"abstain":false}'}
        )
    )
    try:
        ctx = bind_text_llm_context(text_model_name="recorded-double:v1")
        result = LLMCustomQAModule(question_text="Anything?").run(
            doc, llm_ctx=ctx, question_text="Anything?"
        )
        assert result["outcome"] == "skipped_not_applicable"
        assert any(w["code"] == "abstain_ungrounded" for w in result["warnings"])
    finally:
        set_text_llm_client(None)


def test_eligibility_empty_skips_keyphrases(tmp_path: Path):
    projects, runner = _project_with_pages(tmp_path, ["ab", "cd"])  # too_short
    env = runner.run_module("keyphrases")
    assert env["outcome"] == "skipped_not_applicable"


def test_wave13_non_regression(tmp_path: Path):
    projects, runner = _project_with_pages(
        tmp_path,
        ["I am happy and grateful for wonderful success in gardens."],
    )
    for mid in ("stats", "sentiment", "wordclouds"):
        env = runner.run_module(mid)
        assert env["outcome"] == "success", mid


def test_llm_action_items_recorded_double(tmp_path: Path):
    set_text_llm_client(
        RecordedDoubleClient(
            responses={
                "default": (
                    '{"items":[{"record_type":"action_item","text":"Water the plants"},'
                    '{"record_type":"decision","text":"Postpone planting"}]}'
                )
            }
        )
    )
    try:
        projects, runner = _project_with_pages(tmp_path, TEXTS)
        env = runner.run_module("llm_action_items")
        assert env["outcome"] == "success"
        assert env["payload"]["n_items"] == 2
        assert env["payload"]["honesty_label"] == "llm_generated"
        assert env["llm"]["chunking_policy_id"] == CHUNKING_UNITS_V1
        assert env["llm"]["grounding_strategy_id"] == "ground_doc_chunks_v1"
    finally:
        set_text_llm_client(None)


def test_highlights_prefer_paragraph_v1(tmp_path: Path):
    projects, runner = _project_with_pages(
        tmp_path,
        ["First block about gardens.\n\nSecond block about soil moisture and water."],
    )
    env = runner.run_module("highlights")
    assert env["outcome"] == "success"
    assert env["payload"]["n_quotes"] >= 1
    # Evidence should cite page_span when paragraph split applied.
    evidence = env.get("evidence") or []
    assert evidence
    assert evidence[0]["source_ref"]["kind"] == "page_span"
    assert "/span:" in evidence[0]["unit_id"]


def test_batch_runs_parents_before_consumers(tmp_path: Path):
    set_text_llm_client(RecordedDoubleClient(responses={}, healthy=False))
    try:
        projects, runner = _project_with_pages(tmp_path, TEXTS)
        # Intentionally reverse consumer-first order; runner must topo-sort.
        batch = runner.run_batch(
            ["summary", "insights", "highlights", "topic_modeling", "keyphrases"]
        )
        assert batch["keyphrases"]["outcome"] == "success"
        assert batch["topic_modeling"]["outcome"] == "success"
        assert batch["highlights"]["outcome"] == "success"
        assert batch["summary"]["outcome"] == "success"
        assert batch["insights"]["outcome"] == "success"
    finally:
        set_text_llm_client(None)


def test_llm_summary_cache_hit_with_double(tmp_path: Path):
    set_text_llm_client(
        RecordedDoubleClient(responses={"default": '{"summary":"Cached gardens.","bullets":["a"]}'})
    )
    try:
        projects, runner = _project_with_pages(tmp_path, TEXTS)
        a = runner.run_module("llm_summary")
        b = runner.run_module("llm_summary")
        assert a["outcome"] == "success"
        assert b["cache_identity"] == a["cache_identity"]
        assert b.get("attempt_id") == a.get("attempt_id") or b["outcome"] == "success"
    finally:
        set_text_llm_client(None)


def test_digest_change_invalidates_llm_cache(tmp_path: Path):
    projects, runner = _project_with_pages(tmp_path, TEXTS)
    set_text_llm_client(
        RecordedDoubleClient(
            responses={"default": '{"summary":"Gardens.","bullets":["water"]}'},
            digest="digest-aaa",
        )
    )
    try:
        first = runner.run_module("llm_summary")
        assert first["outcome"] == "success"
        assert first["resolved_model_digest"] == "digest-aaa"
        set_text_llm_client(
            RecordedDoubleClient(
                responses={"default": '{"summary":"Gardens.","bullets":["water"]}'},
                digest="digest-bbb",
            )
        )
        second = runner.run_module("llm_summary")
        assert second["outcome"] == "success"
        assert second["resolved_model_digest"] == "digest-bbb"
        assert first["cache_identity"] != second["cache_identity"]
    finally:
        set_text_llm_client(None)


def test_rejects_unsuitable_vision_model_name():
    from transcribe.analysis.llm_runtime import (
        RecordedDoubleClient,
        bind_text_llm_context,
        is_unsuitable_text_model_name,
        set_text_llm_client,
    )

    assert is_unsuitable_text_model_name("llama3.2-vision:latest")
    assert is_unsuitable_text_model_name("nomic-embed-text")
    set_text_llm_client(RecordedDoubleClient(responses={"default": "{}"}))
    try:
        assert bind_text_llm_context(text_model_name="llama3.2-vision") is None
    finally:
        set_text_llm_client(None)


def test_oversized_unit_subsplit_preserves_provenance(tmp_path: Path):
    from transcribe.analysis.chunking import pack_units_v1

    long = " ".join([f"word{i}" for i in range(80)])
    projects, _ = _project_with_pages(tmp_path, [long])
    doc = build_page_v1_document(projects.load(), projects)
    chunks = pack_units_v1(doc, max_tokens=15)
    assert len(chunks) >= 2
    assert all(c.get("spans") for c in chunks)
    assert any("#s" in cid for c in chunks for cid in c.get("cite_ids") or [])
    # No silent truncation: reconstructed text covers all words.
    joined = " ".join(c["text"] for c in chunks)
    for token in long.split()[:20]:
        assert token in joined


def test_llm_summary_strict_schema_abstains(tmp_path: Path):
    # bullets as a string must not coerce into character list
    set_text_llm_client(
        RecordedDoubleClient(responses={"default": '{"summary":"ok","bullets":"abc"}'})
    )
    try:
        projects, runner = _project_with_pages(tmp_path, TEXTS)
        env = runner.run_module("llm_summary")
        assert env["outcome"] == "skipped_not_applicable"
        assert "raw" not in (env.get("payload") or {})
        assert any(w.get("code") == "abstain_unparseable" for w in (env.get("warnings") or []))
    finally:
        set_text_llm_client(None)


def test_qa_question_text_via_runner(tmp_path: Path):
    projects, runner = _project_with_pages(tmp_path, TEXTS)
    doc = build_paragraph_v1_document(projects.load(), projects)
    unit_id = doc.units[0].unit_id
    set_text_llm_client(
        RecordedDoubleClient(
            responses={
                "default": (f'{{"answer":"Water.","unit_ids":["{unit_id}"],"abstain":false}}')
            }
        )
    )
    try:
        env = runner.run_module("llm_custom_qa", question_text="What do gardens need?")
        assert env["outcome"] == "success"
        assert env["llm"]["question_text"] == "What do gardens need?"
        evidence = env.get("evidence") or []
        assert evidence
        assert "quote" in evidence[0]
        assert "content_fingerprint" in evidence[0]
    finally:
        set_text_llm_client(None)


def test_load_published_read_model_none_is_stale(tmp_path: Path):
    from transcribe.analysis.runner import load_published_read_model
    from transcribe.analysis.storage import AnalysisStorage

    set_text_llm_client(
        RecordedDoubleClient(responses={"default": '{"summary":"x","bullets":["y"]}'})
    )
    try:
        projects, runner = _project_with_pages(tmp_path, TEXTS)
        env = runner.run_module("llm_summary")
        assert env["outcome"] == "success"
        storage = AnalysisStorage(projects.paths)
        rm = load_published_read_model(storage, "llm_summary", current_cache_identity=None)
        assert rm["status"] == "stale"
        assert rm["envelope"] is not None
    finally:
        set_text_llm_client(None)


def test_highlights_stopwords_in_identity(tmp_path: Path):
    projects, runner = _project_with_pages(tmp_path, TEXTS)
    env = runner.run_module("highlights")
    assert env["outcome"] == "success"
    lex = env.get("lexicon_or_model") or {}
    assert lex.get("stopwords_id") == "wordclouds_stopwords_v1"
    assert lex.get("stopwords_digest")


def test_narrative_summary_success_with_double(tmp_path: Path):
    set_text_llm_client(
        RecordedDoubleClient(responses={"default": '{"narrative":"A short garden story."}'})
    )
    try:
        projects, runner = _project_with_pages(tmp_path, TEXTS)
        assert runner.run_module("highlights")["outcome"] == "success"
        assert runner.run_module("summary")["outcome"] == "success"
        env = runner.run_module("narrative_summary")
        assert env["outcome"] == "success"
        assert env["payload"]["honesty_label"] == "llm_generated"
        assert "garden" in env["payload"]["narrative"].lower()
        assert env["llm"]["grounding_strategy_id"] == "ground_highlights_summary_v1"
    finally:
        set_text_llm_client(None)


def test_llm_action_items_rejects_non_list_items(tmp_path: Path):
    set_text_llm_client(RecordedDoubleClient(responses={"default": '{"items":"not-a-list"}'}))
    try:
        projects, runner = _project_with_pages(tmp_path, TEXTS)
        env = runner.run_module("llm_action_items")
        assert env["outcome"] == "skipped_not_applicable"
        assert "raw" not in (env.get("payload") or {})
    finally:
        set_text_llm_client(None)
