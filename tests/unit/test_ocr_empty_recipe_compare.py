"""Empty OCR is failed; DeepSeek recipe; on-disk rank/merge."""

from __future__ import annotations

from pathlib import Path

from transcribe.analysis.llm_runtime import RecordedDoubleClient
from transcribe.domain.models import EMPTY_OUTPUT_CODE
from transcribe.ingest import IngestService
from transcribe.services.job import JobCoordinator
from transcribe.services.model_advice import advise_model, is_ocr_oriented_name
from transcribe.services.multipass import MultiPassCoordinator
from transcribe.services.ocr_model_recipes import recipe_for_model
from transcribe.services.project import ProjectService, open_project_paths
from transcribe.services.ocr_composite_state import merge_input_vision_attempts
from tests.conftest import FakeClock, SequentialIds
from tests.fakes import FakeVisionOCRProvider
from tests.ingest.test_ingest import _png_bytes
from tests.unit.test_ocr_lifecycle import _attempt, _project_with_page


def test_recipe_matches_deepseek_ocr() -> None:
    recipe = recipe_for_model("deepseek-ocr:latest")
    assert recipe is not None
    assert recipe.prompt_id == "free_ocr"
    assert recipe_for_model("qwen2.5vl:3b") is None
    assert recipe_for_model("deepseek-r1:8b") is None
    assert is_ocr_oriented_name("deepseek-ocr:latest")
    advice = advise_model("deepseek-ocr:latest")
    assert advice.kind == "ocr_oriented"
    assert "recipe" in advice.title.lower()


def test_empty_ocr_fails_and_keeps_prior_active(tmp_path: Path) -> None:
    projects, page_id = _project_with_page(tmp_path)
    good = _attempt("qwen1", text="notebook line", model="qwen2.5vl:3b")
    projects.record_generation(page_id, good, activate=True)
    provider = FakeVisionOCRProvider(text_by_call=["   \n"], digest="digest-aaa")
    coord = JobCoordinator(
        projects.paths, projects, provider, clock=FakeClock(), ids=SequentialIds()
    )
    project = projects.load()
    settings = project.settings
    settings.model_name = "fake-vision"
    projects.save_settings(project, settings)
    progress = coord.run_blocking(page_ids=[page_id], force=True)
    assert progress.failed == 1
    assert progress.completed == 0
    result = projects.load_page_result(page_id)
    assert result is not None
    assert result.active_attempt_id == "qwen1"
    assert result.effective_text() == "notebook line"
    empty = next(a for a in result.attempts if a.attempt_id != "qwen1" and a.status == "failed")
    assert empty.error is not None
    assert empty.error.code == EMPTY_OUTPUT_CODE


def test_repair_empty_success_restores_prior(tmp_path: Path) -> None:
    projects, page_id = _project_with_page(tmp_path)
    good = _attempt("qwen1", text="kept", model="qwen2.5vl:3b")
    empty = _attempt(
        "ds1",
        text="",
        model="deepseek-ocr:latest",
        started="2020-01-02T00:00:00+00:00",
    )
    projects.record_generation(page_id, good, activate=True)
    # Simulate historical empty success by writing status succeeded with empty text.
    result = projects.load_page_result(page_id)
    assert result is not None
    empty.status = "succeeded"
    empty.raw_text = ""
    result.attempts.append(empty)
    result.active_attempt_id = empty.attempt_id
    from transcribe.persistence.atomic import write_json_atomic

    write_json_atomic(projects.paths.result_path(page_id), result.as_dict())
    repaired = projects.repair_empty_successes(page_id)
    assert repaired is not None
    assert repaired.active_attempt_id == "qwen1"
    ds = repaired.attempt_by_id("ds1")
    assert ds is not None
    assert ds.status == "failed"
    assert ds.error is not None
    assert ds.error.code == EMPTY_OUTPUT_CODE


def test_build_plan_uses_deepseek_recipe(tmp_path: Path) -> None:
    paths = open_project_paths(tmp_path / "proj")
    clock, ids = FakeClock(), SequentialIds()
    projects = ProjectService(paths, clock=clock, ids=ids)
    projects.create("t")
    ingest = IngestService(paths, clock=clock, ids=ids)
    ingest.import_bytes("p.png", _png_bytes())
    provider = FakeVisionOCRProvider(
        models=[],
    )
    from transcribe.providers.base import ModelInfo

    provider.models = [
        ModelInfo(
            name="deepseek-ocr:latest",
            digest="digest-aaa",
            capabilities=["vision"],
            capability_known=True,
        )
    ]
    coord = JobCoordinator(paths, projects, provider, clock=clock, ids=ids)
    project = projects.load()
    settings = project.settings
    settings.model_name = "deepseek-ocr:latest"
    settings.prompt_id = "faithful_text"
    projects.save_settings(project, settings)
    project = projects.load()
    plan = coord._build_plan(
        project, job_id="j1", page_ids=None, force=True, provider=provider
    )
    assert plan.prompt_id == "free_ocr"
    assert plan.prompt_text.strip() == "Free OCR."


def test_custom_prompt_wins_over_recipe(tmp_path: Path) -> None:
    paths = open_project_paths(tmp_path / "proj")
    clock, ids = FakeClock(), SequentialIds()
    projects = ProjectService(paths, clock=clock, ids=ids)
    projects.create("t")
    ingest = IngestService(paths, clock=clock, ids=ids)
    ingest.import_bytes("p.png", _png_bytes())
    from transcribe.providers.base import ModelInfo

    provider = FakeVisionOCRProvider()
    provider.models = [
        ModelInfo(
            name="deepseek-ocr:latest",
            digest="digest-aaa",
            capabilities=["vision"],
            capability_known=True,
        )
    ]
    coord = JobCoordinator(paths, projects, provider, clock=clock, ids=ids)
    project = projects.load()
    settings = project.settings
    settings.model_name = "deepseek-ocr:latest"
    settings.custom_prompt = "Read every word on this page."
    projects.save_settings(project, settings)
    plan = coord._build_plan(
        projects.load(), job_id="j1", page_ids=None, force=True, provider=provider
    )
    assert plan.prompt_id == "custom"
    assert "Read every word" in plan.prompt_text


def test_compare_existing_ranks_cross_job_attempts(tmp_path: Path) -> None:
    projects, page_id = _project_with_page(tmp_path)
    a1 = _attempt("a1", text="first reading", model="qwen2.5vl:3b")
    a2 = _attempt(
        "a2",
        text="second reading",
        model="granite3.2-vision",
        started="2020-01-02T00:00:00+00:00",
    )
    projects.record_generation(page_id, a1, activate=True)
    projects.record_generation(page_id, a2, activate=False)
    result = projects.load_page_result(page_id)
    assert result is not None
    assert len(merge_input_vision_attempts(result)) == 2

    project = projects.load()
    settings = project.settings
    settings.text_model_name = "recorded-double:v1"
    settings.cleanup_model_name = "recorded-double:v1"
    projects.save_settings(project, settings)

    client = RecordedDoubleClient(
        responses={
            "contains:rank competing": '{"order":["a2","a1"],"rationales":{"a2":"fuller","a1":"ok"}}',
            "contains:merge competing": "first reading second reading",
        },
        digest="fixed-digest",
        model_name="recorded-double:v1",
    )
    jobs = JobCoordinator(
        projects.paths,
        projects,
        FakeVisionOCRProvider(),
        clock=FakeClock(),
        ids=SequentialIds(),
    )
    multi = MultiPassCoordinator(
        jobs=jobs,
        projects=projects,
        clock=FakeClock(),
        ids=SequentialIds(),
        text_client=client,
    )
    progress = multi.run_compare_existing_blocking(
        page_ids=[page_id], auto_activate_composite=True
    )
    assert progress.status == "completed"
    assert progress.pages_ranked == 1
    assert progress.pages_composite == 1
    after = projects.load_page_result(page_id)
    assert after is not None
    assert after.comparison is not None
    assert after.comparison.ranked_attempt_ids[0] == "a2"
    kinds = {(a.attempt_kind or "vision") for a in after.attempts}
    assert "composite" in kinds
