"""Wave 1.1 analysis infrastructure and module tests."""

from __future__ import annotations

from pathlib import Path

import pytest
from PIL import Image

from transcribe.analysis.adapter import build_page_v1_document
from transcribe.analysis.cache_identity import (
    build_cache_identity_object,
    cache_identity_hex,
)
from transcribe.analysis.document import content_fingerprint
from transcribe.analysis.eligibility import evaluate_notebook_eligibility_v1
from transcribe.analysis.modules.lexical_diversity import LexicalDiversityModule
from transcribe.analysis.modules.stats import StatsModule
from transcribe.analysis.modules.understandability import UnderstandabilityModule
from transcribe.analysis.runner import AnalysisRunner, load_published_read_model
from transcribe.analysis.storage import AnalysisStorage
from transcribe.domain.models import PageResult
from transcribe.ingest import IngestService
from transcribe.persistence.atomic import read_json, write_json_atomic
from transcribe.persistence.schema import SUPPORTED, SchemaError, require_format
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
    clock, ids = FakeClock(), SequentialIds("a")
    projects = ProjectService(paths, clock=clock, ids=ids)
    projects.create("notebook")
    ingest = IngestService(paths, clock=clock, ids=ids)
    for i, _ in enumerate(texts):
        ingest.import_bytes(f"p{i}.png", _png_bytes())
    project = projects.load()
    for page, text in zip(project.pages, texts, strict=True):
        projects.save_user_edit(page.page_id, text)
    return projects, AnalysisRunner(projects, clock=clock, ids=ids)


def test_analysis_schemas_registered_and_reject_unknown():
    assert SUPPORTED["transcribe.project"] == 1
    assert SUPPORTED["transcribe.analysis-document"] == 1
    assert SUPPORTED["transcribe.analysis-result"] == 1
    with pytest.raises(SchemaError):
        require_format(
            {"format": "transcribe.analysis-result", "schema_version": 99},
            "transcribe.analysis-result",
        )


def test_schema_supported_includes_analysis_formats():
    assert SUPPORTED["transcribe.project"] == 1
    assert SUPPORTED["transcribe.page-result"] == 1
    assert SUPPORTED["transcribe.notebook"] == 1
    assert SUPPORTED["transcribe.analysis-document"] == 1
    assert SUPPORTED["transcribe.analysis-result"] == 1
    # Duplicate registration must not change existing keys
    before = dict(SUPPORTED)
    SUPPORTED["transcribe.analysis-document"] = 1
    assert SUPPORTED == before


def test_page_v1_fingerprint_stable_and_ignores_title(tmp_path: Path):
    projects, _ = _project_with_pages(
        tmp_path,
        [
            "Hello world from page one.",
            "Second page has more words here.",
            "Third page continues the notebook text.",
        ],
    )
    project = projects.load()
    doc1 = build_page_v1_document(project, projects)
    fp1 = content_fingerprint(doc1)
    projects.update_notebook_metadata(title="Renamed title")
    project2 = projects.load()
    doc2 = build_page_v1_document(project2, projects)
    assert content_fingerprint(doc2) == fp1


def test_exclusion_and_blank_change_fingerprint(tmp_path: Path):
    projects, _ = _project_with_pages(
        tmp_path,
        ["Alpha page text here.", "Beta page text here.", "   "],
    )
    project = projects.load()
    doc = build_page_v1_document(project, projects)
    assert len(doc.units) == 2  # blank omitted
    fp = content_fingerprint(doc)

    from transcribe.domain.models import Project
    from transcribe.persistence.locks import mutation_lock
    from transcribe.persistence.atomic import read_json, write_json_atomic
    from transcribe.persistence.schema import require_format

    with mutation_lock(projects.paths.mutation_lock):
        payload = require_format(read_json(projects.paths.manifest), "transcribe.project")
        current = Project.from_dict(payload)
        current.pages[0].analysis_excluded = True
        write_json_atomic(projects.paths.manifest, current.as_dict())

    project2 = projects.load()
    doc2 = build_page_v1_document(project2, projects)
    assert len(doc2.units) == 1
    assert content_fingerprint(doc2) != fp


def test_run_three_modules_and_cache_hit(tmp_path: Path):
    projects, runner = _project_with_pages(
        tmp_path,
        [
            "The quick brown fox jumps over the lazy dog again and again.",
            "Another page with enough tokens for diversity metrics to run well.",
            "A third page keeps the notebook corpus non-trivial for readability.",
        ],
    )
    first = runner.run_batch()
    assert set(first) == {"stats", "lexical_diversity", "understandability"}
    for mid, env in first.items():
        assert env["attempt_state"] == "succeeded"
        assert env["outcome"] == "success"
        assert env.get("published") is True
    second = runner.run_module("stats")
    assert second["attempt_id"] == first["stats"]["attempt_id"]


def test_batch_isolation_one_module_fails(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    projects, runner = _project_with_pages(
        tmp_path,
        [
            "Enough words on page one for metrics to succeed properly.",
            "Enough words on page two for metrics to succeed properly.",
        ],
    )

    original = StatsModule.run

    def boom(self, document):
        raise RuntimeError("stats exploded")

    monkeypatch.setattr(StatsModule, "run", boom)
    results = runner.run_batch(["stats", "lexical_diversity", "understandability"])
    assert results["stats"]["outcome"] == "failed"
    assert results["lexical_diversity"]["outcome"] == "success"
    assert results["understandability"]["outcome"] == "success"
    monkeypatch.setattr(StatsModule, "run", original)


def test_stale_publish_refuses_after_edit(tmp_path: Path):
    projects, runner = _project_with_pages(
        tmp_path,
        ["Original page text with enough content here for analysis."],
    )
    # Manual mid-run simulation: build planned identity, edit, then publish check
    project = projects.load()
    doc = build_page_v1_document(project, projects)
    modules = {"stats": StatsModule()}
    module = modules["stats"]
    planned = build_cache_identity_object(
        project_id=project.id,
        module_id=module.module_id,
        module_version=module.module_version,
        document=doc,
    )
    planned_hex = cache_identity_hex(planned)
    result = module.run(doc)
    from transcribe.analysis.envelope import build_envelope

    attempt_id = "attempt-stale"
    env = build_envelope(
        project_id=project.id,
        module_id=module.module_id,
        module_version=module.module_version,
        cache_identity=planned_hex,
        content_fingerprint=planned["content_fingerprint"],
        attempt_state="succeeded",
        outcome=result["outcome"],
        payload=result["payload"],
        provenance={"ported_from": {"repo": "t", "commit": "n/a", "module_id": "stats", "files": []},
                    "semantic_class": "adaptation", "semantic_delta": ""},
        config_fingerprint=planned["config_fingerprint"],
        attempt_id=attempt_id,
        published=False,
    )
    storage = AnalysisStorage(projects.paths)
    storage.write_attempt("stats", env)
    projects.save_user_edit(project.pages[0].page_id, "Changed text invalidates fingerprint now.")
    project2 = projects.load()
    doc2 = build_page_v1_document(project2, projects)
    now = cache_identity_hex(
        build_cache_identity_object(
            project_id=project2.id,
            module_id=module.module_id,
            module_version=module.module_version,
            document=doc2,
        )
    )
    published = storage.publish_if_current(
        module_id="stats",
        envelope=env,
        expected_cache_identity=planned_hex,
        current_cache_identity=now,
    )
    assert published is False
    assert storage.read_published("stats") is None
    attempt = storage.read_attempt("stats", attempt_id)
    assert attempt is not None
    assert attempt.get("stale_at_publish") is True


def test_reopen_reconciles_running_without_clobbering_published(tmp_path: Path):
    projects, runner = _project_with_pages(
        tmp_path,
        ["Published notebook text with sufficient content for stats module."],
    )
    published = runner.run_module("stats")
    assert published["outcome"] == "success"
    storage = AnalysisStorage(projects.paths)
    # Inject orphan running attempt
    orphan = dict(published)
    orphan["attempt_id"] = "orphan-running"
    orphan["attempt_state"] = "running"
    orphan["published"] = False
    storage.write_attempt("stats", orphan)
    # published still valid
    before = storage.read_published("stats")
    projects.load(reconcile=True)
    after_attempt = storage.read_attempt("stats", "orphan-running")
    assert after_attempt["attempt_state"] == "interrupted"
    assert storage.read_published("stats")["cache_identity"] == before["cache_identity"]


def test_crash_boundary_between_attempt_and_publish(tmp_path: Path):
    projects, runner = _project_with_pages(
        tmp_path,
        ["Crash boundary text with enough words for a successful stats run."],
    )
    first = runner.run_module("stats")
    storage = AnalysisStorage(projects.paths)
    # Simulate: new terminal attempt written, publish not yet done
    project = projects.load()
    doc = build_page_v1_document(project, projects)
    module = StatsModule()
    planned = build_cache_identity_object(
        project_id=project.id,
        module_id=module.module_id,
        module_version=module.module_version,
        document=doc,
    )
    from transcribe.analysis.envelope import build_envelope

    new_attempt = build_envelope(
        project_id=project.id,
        module_id=module.module_id,
        module_version=module.module_version,
        cache_identity=cache_identity_hex(planned),
        content_fingerprint=planned["content_fingerprint"],
        attempt_state="succeeded",
        outcome="success",
        payload={"unit_count": 1},
        provenance={"ported_from": {"repo": "t", "commit": "n/a", "module_id": "stats", "files": []},
                    "semantic_class": "adaptation", "semantic_delta": ""},
        config_fingerprint=planned["config_fingerprint"],
        attempt_id="crash-attempt",
        published=False,
    )
    storage.write_attempt("stats", new_attempt)
    # No publish yet — old published must remain valid
    current = storage.read_published("stats")
    assert current is not None
    assert current["attempt_id"] == first["attempt_id"]
    # Completing publish replaces atomically
    assert storage.publish_if_current(
        module_id="stats",
        envelope=new_attempt,
        expected_cache_identity=cache_identity_hex(planned),
        current_cache_identity=cache_identity_hex(planned),
    )
    assert storage.read_published("stats")["attempt_id"] == "crash-attempt"


def test_eligibility_lib_but_ungated_modules_still_run(tmp_path: Path):
    projects, runner = _project_with_pages(tmp_path, ["ab", "cd"])  # too short for eligibility
    project = projects.load()
    doc = build_page_v1_document(project, projects)
    elig = evaluate_notebook_eligibility_v1(doc.units)
    assert elig["eligible_unit_ids"] == []
    # Modules must not call eligibility — still run (may be insufficient_data for lex/understand)
    results = runner.run_batch()
    assert "stats" in results
    assert results["stats"]["outcome"] == "success"
    # Prove modules don't import eligibility in their module files
    import transcribe.analysis.modules.stats as st
    import transcribe.analysis.modules.lexical_diversity as ld
    import transcribe.analysis.modules.understandability as un
    import inspect

    for mod in (st, ld, un):
        src = inspect.getsource(mod)
        assert "eligibility" not in src


def test_min_input_lexical_and_understandability(tmp_path: Path):
    projects, runner = _project_with_pages(tmp_path, ["x"])  # one letter token after tokenize? "x" len 1 filtered
    # TX tokenize requires len >= 2, so "x" → 0 tokens → insufficient_data for lexical
    lex = runner.run_module("lexical_diversity")
    assert lex["outcome"] == "insufficient_data"
    und = runner.run_module("understandability")
    assert und["outcome"] == "insufficient_data"


def test_read_model_does_not_infer_success_from_attempt(tmp_path: Path):
    projects, runner = _project_with_pages(
        tmp_path,
        ["Read model text with enough words to publish a stats result successfully."],
    )
    runner.run_module("stats")
    storage = AnalysisStorage(projects.paths)
    # Corrupt published
    path = storage.published_path("stats")
    path.write_text("{not-json", encoding="utf-8")
    model = load_published_read_model(storage, "stats", current_cache_identity=None)
    assert model["status"] == "unavailable"


def test_canonical_payload_golden_stats(tmp_path: Path):
    projects, runner = _project_with_pages(
        tmp_path,
        ["Hello world page.", "Second page text."],
    )
    env = runner.run_module("stats")
    payload = env["payload"]
    assert payload["unit_count"] == 2
    assert "attempt_id" not in payload
    assert payload["units"][0]["char_count"] == len("Hello world page.")
