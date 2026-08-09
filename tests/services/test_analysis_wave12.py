"""Baseline wordclouds tests."""

from __future__ import annotations

from pathlib import Path

from PIL import Image

from transcribe.analysis.adapter import build_page_v1_document
from transcribe.analysis.cache_identity import (
    build_cache_identity_object,
    cache_identity_hex,
)
from transcribe.analysis.document import AnalysisDocument, AnalysisUnit
from transcribe.analysis.modules import THROUGH_FOUNDATIONS, get_registered_modules
from transcribe.analysis.modules.wordclouds import (
    WordcloudsModule,
    build_token_payload,
    eligible_tokens,
    stopwords_digest,
    wordclouds_config,
)
from transcribe.analysis.parents import resolve_optional_parents
from transcribe.analysis.runner import AnalysisRunner, load_published_read_model, _module_provenance
from transcribe.analysis.storage import AnalysisStorage
from transcribe.ingest import IngestService
from transcribe.persistence.atomic import write_json_atomic
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
    clock, ids = FakeClock(), SequentialIds("w")
    projects = ProjectService(paths, clock=clock, ids=ids)
    projects.create("notebook")
    ingest = IngestService(paths, clock=clock, ids=ids)
    for i, _ in enumerate(texts):
        ingest.import_bytes(f"p{i}.png", _png_bytes())
    project = projects.load()
    for page, text in zip(project.pages, texts, strict=True):
        projects.save_user_edit(page.page_id, text)
    return projects, AnalysisRunner(projects, clock=clock, ids=ids)


def _doc(text: str) -> AnalysisDocument:
    unit = AnalysisUnit(
        unit_id="p1",
        order=0,
        text=text,
        source_ref={"kind": "page", "page_id": "p1"},
        date=None,
    )
    return AnalysisDocument(
        document_id="d1",
        text=text,
        units=[unit],
        granularity_version="page_v1",
        split_profile="page",
    )


def test_registry_includes_wordclouds_and_wave11_unchanged():
    w11 = get_registered_modules(through=THROUGH_FOUNDATIONS)
    assert set(w11) == {"stats", "lexical_diversity", "understandability"}
    all_mods = get_registered_modules()
    assert "wordclouds" in all_mods
    assert set(w11).issubset(set(all_mods))


def test_wordclouds_golden_and_determinism():
    text = (
        "Alpha beta gamma alpha beta alpha. "
        "Notebook clouds prefer alpha over zebra zebra."
    )
    doc = _doc(text)
    mod = WordcloudsModule()
    a = mod.run(doc)
    b = mod.run(doc)
    assert a["outcome"] == "success"
    assert a == b
    tokens = a["payload"]["tokens"]
    assert tokens[0]["token"] == "alpha"
    assert tokens[0]["count"] == 4
    assert tokens[0]["weight"] == 1.0
    # tie-break: beta (2) before zebra (2) lexicographically
    counts = {t["token"]: t["count"] for t in tokens}
    assert counts["beta"] == 2
    assert counts["zebra"] == 2
    order = [t["token"] for t in tokens]
    assert order.index("beta") < order.index("zebra")


def test_equal_frequency_lexical_tiebreak():
    payload = build_token_payload("zebra alpha zebra alpha")
    assert payload is not None
    # both count 2 → alpha before zebra
    assert [t["token"] for t in payload["tokens"][:2]] == ["alpha", "zebra"]


def test_unicode_punctuation_numbers_and_stopwords():
    # Accents preserved after casefold; digits dropped; punctuation separators
    tokens = eligible_tokens("Café CAFÉ 123 !!! the and notebook notebook")
    assert "café" in tokens
    assert "123" not in tokens
    assert "the" not in tokens
    assert "and" not in tokens
    assert tokens.count("notebook") == 2


def test_stopword_only_insufficient_data():
    mod = WordcloudsModule()
    result = mod.run(_doc("the and of to a in"))
    assert result["outcome"] == "insufficient_data"
    assert result["payload"] == {}


def test_empty_document_insufficient_data(tmp_path: Path):
    projects, runner = _project_with_pages(tmp_path, ["   "])
    # blank page omitted → empty document preflight
    env = runner.run_module("wordclouds")
    assert env["outcome"] == "insufficient_data"


def test_optional_parent_ignore_matrix(tmp_path: Path):
    projects, runner = _project_with_pages(
        tmp_path,
        ["Unique notebook topic about gardens gardens flowers."],
    )
    storage = AnalysisStorage(projects.paths)
    # Absent
    assert resolve_optional_parents(
        "wordclouds", enrichment_mode="baseline", storage=storage
    ) == []

    def _write_keyphrases(outcome: str, cache_identity: str = "kp-id") -> None:
        write_json_atomic(
            storage.published_path("keyphrases"),
            {
                "format": "transcribe.analysis-result",
                "schema_version": 1,
                "project_id": projects.load().id,
                "module_id": "keyphrases",
                "module_version": "1",
                "cache_identity": cache_identity,
                "content_fingerprint": "x",
                "attempt_state": "succeeded",
                "outcome": outcome,
                "capability": "success" if outcome == "success" else outcome,
                "provenance": {
                    "ported_from": {
                        "repo": "t",
                        "commit": "n/a",
                        "module_id": "keyphrases",
                        "files": [],
                    },
                    "semantic_class": "adaptation",
                    "semantic_delta": "",
                    "module_version": "1",
                    "adapter_version": "1",
                    "app_version": "0",
                },
                "warnings": [],
                "parents": [],
                "config_fingerprint": "c",
                "payload": {"phrases": ["gardens"]},
                "published": True,
            },
        )

    baseline = runner.run_module("wordclouds")
    assert baseline["outcome"] == "success"
    assert baseline["parents"] == []
    assert baseline["payload"]["enrichment_mode"] == "baseline"
    id_absent = baseline["cache_identity"]

    for outcome in ("failed", "insufficient_data", "success"):
        _write_keyphrases(outcome)
        parents = resolve_optional_parents(
            "wordclouds", enrichment_mode="baseline", storage=storage
        )
        assert parents == []
        again = runner.run_module("wordclouds")
        assert again["parents"] == []
        assert again["cache_identity"] == id_absent
        assert again["attempt_id"] == baseline["attempt_id"]


def test_config_change_changes_cache_identity(tmp_path: Path):
    projects, runner = _project_with_pages(
        tmp_path, ["Garden flowers bloom in spring gardens."]
    )
    project = projects.load()
    doc = build_page_v1_document(project, projects)
    cfg = wordclouds_config()
    base = cache_identity_hex(
        build_cache_identity_object(
            project_id=project.id,
            module_id="wordclouds",
            module_version="1.2.0",
            document=doc,
            config=cfg,
            parents=[],
        )
    )
    tweaked = dict(cfg)
    tweaked["max_tokens"] = 50
    other = cache_identity_hex(
        build_cache_identity_object(
            project_id=project.id,
            module_id="wordclouds",
            module_version="1.2.0",
            document=doc,
            config=tweaked,
            parents=[],
        )
    )
    assert base != other


def test_edit_exclude_blank_invalidate_metadata_keeps(tmp_path: Path):
    projects, runner = _project_with_pages(
        tmp_path,
        [
            "Alpha gardens topic one with flowers.",
            "Beta gardens topic two with petals.",
            "Gamma gardens topic three with leaves.",
        ],
    )
    first = runner.run_module("wordclouds")
    assert first["outcome"] == "success"
    id1 = first["cache_identity"]

    projects.update_notebook_metadata(title="Renamed only")
    second = runner.run_module("wordclouds")
    assert second["cache_identity"] == id1
    assert second["attempt_id"] == first["attempt_id"]  # cache hit

    project = projects.load()
    projects.save_user_edit(project.pages[0].page_id, "Completely different edited text here.")
    third = runner.run_module("wordclouds")
    assert third["cache_identity"] != id1

    # Exclude a contributing page → identity must change
    from transcribe.domain.models import Project
    from transcribe.persistence.atomic import read_json, write_json_atomic as wja
    from transcribe.persistence.locks import mutation_lock
    from transcribe.persistence.schema import require_format

    id_after_edit = third["cache_identity"]
    with mutation_lock(projects.paths.mutation_lock):
        payload = require_format(read_json(projects.paths.manifest), "transcribe.project")
        current = Project.from_dict(payload)
        current.pages[1].analysis_excluded = True
        wja(projects.paths.manifest, current.as_dict())
    fourth = runner.run_module("wordclouds")
    assert fourth["cache_identity"] != id_after_edit

    # Blank a remaining page → identity must change again
    project = projects.load()
    remaining = [p for p in project.pages if not p.analysis_excluded]
    assert remaining
    projects.save_user_edit(remaining[0].page_id, "   ")
    fifth = runner.run_module("wordclouds")
    assert fifth["cache_identity"] != fourth["cache_identity"]


def test_max_tokens_truncation_preserves_pretruncation_weights():
    # 120 unique eligible letter-only tokens (digits are not TOKEN_RE matches).
    alphabet = "abcdefghijklmnopqrstuvwxyz"
    names = []
    for i in range(120):
        # base-26 style unique labels: aa, ab, ... 
        a, b = divmod(i, 26)
        names.append(f"zz{alphabet[a]}{alphabet[b]}")
    parts = []
    for i, tok in enumerate(names):
        parts.extend([tok] * (i + 1))
    text = " ".join(parts)
    payload = build_token_payload(text)
    assert payload is not None
    tokens = payload["tokens"]
    assert len(tokens) == 100
    assert tokens[0]["token"] == names[119]
    assert tokens[0]["count"] == 120
    assert tokens[0]["weight"] == 1.0
    last = tokens[-1]
    assert last["token"] == names[20]
    assert last["count"] == 21
    assert last["weight"] == round(21 / 120, 6)
    assert all(t["token"] != names[19] for t in tokens)
    assert max(t["weight"] for t in tokens) == 1.0


def test_three_page_fixture_exact_payload(tmp_path: Path):
    projects, runner = _project_with_pages(
        tmp_path,
        [
            "The quick brown fox jumps over the lazy dog again and again.",
            "Another page with enough tokens for diversity metrics to run well.",
            "A third page keeps the notebook corpus non-trivial for readability.",
        ],
    )
    env = runner.run_module("wordclouds")
    assert env["outcome"] == "success"
    payload = env["payload"]
    assert payload["schema"] == "wordclouds_payload_v1"
    assert payload["tokenization_version"] == "wordclouds_tokens_v1"
    assert payload["enrichment_mode"] == "baseline"
    assert payload["algorithm_version"] == "1"
    tokens = payload["tokens"]
    assert tokens
    assert all(set(t) >= {"token", "count", "weight"} for t in tokens)
    # Deterministic: top token should be stable content word (stopwords stripped)
    assert tokens[0]["weight"] == 1.0
    assert tokens[0]["count"] >= tokens[-1]["count"]
    # Lexical tie-break within equal counts
    for i in range(len(tokens) - 1):
        a, b = tokens[i], tokens[i + 1]
        if a["count"] == b["count"]:
            assert a["token"] <= b["token"]


def test_unknown_module_raises(tmp_path: Path):
    projects, runner = _project_with_pages(tmp_path, ["Some notebook text here."])
    try:
        runner.run_module("not_a_real_module")
        raise AssertionError("expected KeyError")
    except KeyError as exc:
        assert "not_a_real_module" in str(exc)


def test_provenance_matches_pin_n_a_adaptation():
    mod = WordcloudsModule()
    prov = _module_provenance(mod)
    assert prov["ported_from"]["commit"] == "n/a"
    assert prov["semantic_class"] == "adaptation"
    assert prov["ported_from"]["files"] == []
    assert stopwords_digest() == (
        "59b09014b432830d8fc50e4421fd984602d17fb5b0900f4ddce3e2bbe3fa04e6"
    )


def test_wave11_non_regression_with_wordclouds(tmp_path: Path):
    projects, runner = _project_with_pages(
        tmp_path,
        [
            "The quick brown fox jumps over the lazy dog again and again.",
            "Another page with enough tokens for diversity metrics to run well.",
            "A third page keeps the notebook corpus non-trivial for readability.",
        ],
    )
    # Run 1.1 modules only first
    before = {
        mid: runner.run_module(mid)
        for mid in ("stats", "lexical_diversity", "understandability")
    }
    # Introduce wordclouds
    wc = runner.run_module("wordclouds")
    assert wc["outcome"] == "success"
    after = {
        mid: runner.run_module(mid)
        for mid in ("stats", "lexical_diversity", "understandability")
    }
    for mid in before:
        assert after[mid]["cache_identity"] == before[mid]["cache_identity"]
        assert after[mid]["payload"] == before[mid]["payload"]
        assert after[mid]["attempt_id"] == before[mid]["attempt_id"]


def test_overview_reopen_and_corrupt_wordclouds(tmp_path: Path):
    projects, runner = _project_with_pages(
        tmp_path, ["Reopen gardens gardens flowers petals notebook."]
    )
    published = runner.run_module("wordclouds")
    assert published["outcome"] == "success"
    storage = AnalysisStorage(projects.paths)

    # Simulate reopen: new runner/storage, read published only
    model = load_published_read_model(
        storage, "wordclouds", current_cache_identity=published["cache_identity"]
    )
    assert model["status"] == "ok"
    tokens = (model["envelope"] or {}).get("payload", {}).get("tokens") or []
    assert tokens and tokens[0]["token"]

    # Corrupt published — must not crash read-model; must not invent success
    path = storage.published_path("wordclouds")
    path.write_text("{not-json", encoding="utf-8")
    model2 = load_published_read_model(
        storage, "wordclouds", current_cache_identity=published["cache_identity"]
    )
    assert model2["status"] == "unavailable"
