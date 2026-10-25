"""Empty OCR is failed; DeepSeek recipe; on-disk rank/merge."""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.conftest import FakeClock, SequentialIds
from tests.fakes import FakeVisionOCRProvider
from tests.ingest.test_ingest import _png_bytes
from tests.unit.test_ocr_lifecycle import _attempt, _project_with_page
from transcribe.analysis.llm_runtime import RecordedDoubleClient
from transcribe.domain.models import EMPTY_OUTPUT_CODE, TOKEN_REPEAT_CODE
from transcribe.ingest import IngestService
from transcribe.runtime_paths import RuntimePaths
from transcribe.services.job import JobCoordinator
from transcribe.services.model_advice import advise_model, is_ocr_oriented_name
from transcribe.services.multipass import MultiPassCoordinator
from transcribe.services.ocr_composite_state import merge_input_vision_attempts
from transcribe.services.ocr_model_recipes import RECIPES, recipe_for_model
from transcribe.services.project import ProjectService, open_project_paths


def _runtime(tmp_path: Path) -> RuntimePaths:
    data = tmp_path / "ws-data"
    data.mkdir(exist_ok=True)
    return RuntimePaths(
        repo_root=tmp_path,
        data_dir=data,
        projects_dir=data / "projects",
        inbox_dir=data / "inbox",
        export_dir=data / "exports",
    )


def test_recipe_matches_deepseek_ocr() -> None:
    recipe = recipe_for_model("deepseek-ocr:latest", recipes=RECIPES)
    assert recipe is not None
    assert recipe.prompt_id == "free_ocr"
    assert recipe.freeze_prompt is True
    assert recipe_for_model("qwen2.5vl:3b", recipes=RECIPES) is None
    assert recipe_for_model("deepseek-r1:8b", recipes=RECIPES) is None
    assert is_ocr_oriented_name("deepseek-ocr:latest")
    advice = advise_model("deepseek-ocr:latest")
    assert advice.kind == "ocr_oriented"
    assert "recipe" in advice.title.lower()


def test_recipe_matches_glm_ocr() -> None:
    recipe = recipe_for_model("glm-ocr:latest", recipes=RECIPES)
    assert recipe is not None
    assert recipe.recipe_id == "glm_ocr"
    assert recipe.prompt_id == "faithful_markdown"
    assert recipe.freeze_prompt is False
    assert recipe.generation_options.get("repeat_penalty") == 1.2
    assert recipe.generation_options.get("stop") == ["```\n```"]
    assert recipe_for_model("qwen2.5vl:7b", recipes=RECIPES) is None
    advice = advise_model("glm-ocr")
    assert advice.kind == "ocr_oriented"
    assert "recipe" in advice.title.lower()
    assert any("repeat_penalty" in w for w in advice.warnings)


def test_recipe_matches_granite_vision() -> None:
    recipe = recipe_for_model("granite3.2-vision:latest", recipes=RECIPES)
    assert recipe is not None
    assert recipe.recipe_id == "granite_vision"
    assert recipe.freeze_prompt is False
    assert recipe.generation_options.get("repeat_penalty") == 1.2
    assert recipe.generation_options.get("stop") == ["```\n```"]
    assert recipe_for_model("granite3.2-vision", recipes=RECIPES) is not None
    assert recipe_for_model("granite3.2:8b", recipes=RECIPES) is None
    advice = advise_model("granite3.2-vision")
    assert advice.kind == "recommended_vlm"
    assert "recipe" in advice.title.lower()
    assert any("repeat_penalty" in w for w in advice.warnings)


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
    coord = JobCoordinator(
        paths, projects, provider, clock=clock, ids=ids, archive_runtime=_runtime(tmp_path)
    )
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
    assert plan.recipe_id == "deepseek_ocr"


def test_build_plan_uses_glm_ocr_repeat_penalty(tmp_path: Path) -> None:
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
            name="glm-ocr:latest",
            digest="digest-glm",
            capabilities=["vision"],
            capability_known=True,
        )
    ]
    coord = JobCoordinator(
        paths, projects, provider, clock=clock, ids=ids, archive_runtime=_runtime(tmp_path)
    )
    project = projects.load()
    settings = project.settings
    settings.model_name = "glm-ocr"
    settings.prompt_id = "faithful_markdown"
    projects.save_settings(project, settings)
    plan = coord._build_plan(
        projects.load(), job_id="j1", page_ids=None, force=True, provider=provider
    )
    assert plan.prompt_id == "faithful_markdown"
    assert plan.generation_options.get("repeat_penalty") == 1.2
    assert plan.generation_options.get("stop") == ["```\n```"]
    assert plan.generation_options.get("temperature") == 0.0
    assert plan.model_identity_verified is True
    assert plan.recipe_id == "glm_ocr"


def test_glm_recipe_job_seals_options_not_recipe_id(tmp_path: Path) -> None:
    """Recipe overlay is hashed; recipe_id stays provenance-only so skip still matches."""
    paths = open_project_paths(tmp_path / "proj")
    clock, ids = FakeClock(), SequentialIds()
    projects = ProjectService(paths, clock=clock, ids=ids)
    projects.create("t")
    ingest = IngestService(paths, clock=clock, ids=ids)
    ingest.import_bytes("p.png", _png_bytes())
    from transcribe.providers.base import ModelInfo

    provider = FakeVisionOCRProvider(
        digest="digest-glm",
        default_text="glm notebook line about weather metro",
    )
    provider.models = [
        ModelInfo(
            name="glm-ocr:latest",
            digest="digest-glm",
            capabilities=["vision"],
            capability_known=True,
        )
    ]
    coord = JobCoordinator(
        paths, projects, provider, clock=clock, ids=ids, archive_runtime=_runtime(tmp_path)
    )
    project = projects.load()
    settings = project.settings
    settings.model_name = "glm-ocr"
    settings.prompt_id = "faithful_markdown"
    projects.save_settings(project, settings)
    progress = coord.run_blocking()
    assert progress.status == "completed"
    assert progress.completed == 1
    assert provider.last_options.get("repeat_penalty") == 1.2
    assert provider.last_options.get("stop") == ["```\n```"]
    page_id = projects.load().pages[0].page_id
    attempt = projects.load_page_result(page_id).active_attempt()
    assert attempt is not None
    payload = attempt.fingerprint_payload or {}
    assert payload.get("generation_options", {}).get("repeat_penalty") == 1.2
    assert payload.get("generation_options", {}).get("stop") == ["```\n```"]
    assert "recipe_id" not in payload
    assert attempt.provenance is not None
    assert attempt.provenance.recipe_id == "glm_ocr"
    progress2 = coord.run_blocking()
    assert progress2.skipped == 1
    assert provider.calls == 1


def test_build_plan_uses_granite_repeat_penalty(tmp_path: Path) -> None:
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
            name="granite3.2-vision:latest",
            digest="digest-granite",
            capabilities=["vision"],
            capability_known=True,
        )
    ]
    coord = JobCoordinator(
        paths, projects, provider, clock=clock, ids=ids, archive_runtime=_runtime(tmp_path)
    )
    project = projects.load()
    settings = project.settings
    settings.model_name = "granite3.2-vision"
    settings.prompt_id = "faithful_markdown"
    projects.save_settings(project, settings)
    plan = coord._build_plan(
        projects.load(), job_id="j1", page_ids=None, force=True, provider=provider
    )
    assert plan.prompt_id == "faithful_markdown"
    assert plan.generation_options.get("repeat_penalty") == 1.2
    assert plan.model_identity_verified is True
    assert plan.recipe_id == "granite_vision"


def test_repair_truncated_repetition_successes(tmp_path: Path) -> None:
    projects, page_id = _project_with_page(tmp_path)
    good = _attempt("qwen1", text="kept diary line", model="qwen2.5vl:7b")
    loop = "I'm talking lily " * 40
    bad = _attempt(
        "granite1",
        text=loop,
        model="granite3.2-vision",
        started="2020-01-02T00:00:00+00:00",
    )
    bad.provider_metadata = {"truncated": True, "eval_count": 4096}
    projects.record_generation(page_id, good, activate=True)
    projects.record_generation(page_id, bad, activate=True)
    result = projects.load_page_result(page_id)
    assert result is not None
    assert result.active_attempt_id == "granite1"
    repaired = projects.repair_truncated_repetition_successes(page_id)
    assert repaired is not None
    assert repaired.active_attempt_id == "qwen1"
    demoted = repaired.attempt_by_id("granite1")
    assert demoted is not None
    assert demoted.status == "failed"
    assert demoted.error is not None
    assert demoted.error.code == TOKEN_REPEAT_CODE


def test_build_plan_qwen_has_no_repeat_penalty(tmp_path: Path) -> None:
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
            name="qwen2.5vl:7b",
            digest="digest-qwen",
            capabilities=["vision"],
            capability_known=True,
        )
    ]
    coord = JobCoordinator(
        paths, projects, provider, clock=clock, ids=ids, archive_runtime=_runtime(tmp_path)
    )
    project = projects.load()
    settings = project.settings
    settings.model_name = "qwen2.5vl:7b"
    projects.save_settings(project, settings)
    plan = coord._build_plan(
        projects.load(), job_id="j1", page_ids=None, force=True, provider=provider
    )
    assert "repeat_penalty" not in plan.generation_options
    assert plan.generation_options.get("num_predict") == 4096
    assert plan.recipe_id == ""


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
    coord = JobCoordinator(
        paths, projects, provider, clock=clock, ids=ids, archive_runtime=_runtime(tmp_path)
    )
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
    assert plan.recipe_id == "deepseek_ocr"


def test_glm_options_only_keeps_faithful_text(tmp_path: Path) -> None:
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
            name="glm-ocr:latest",
            digest="digest-glm",
            capabilities=["vision"],
            capability_known=True,
        )
    ]
    coord = JobCoordinator(
        paths, projects, provider, clock=clock, ids=ids, archive_runtime=_runtime(tmp_path)
    )
    project = projects.load()
    settings = project.settings
    settings.model_name = "glm-ocr"
    settings.prompt_id = "faithful_text"
    projects.save_settings(project, settings)
    plan = coord._build_plan(
        projects.load(), job_id="j1", page_ids=None, force=True, provider=provider
    )
    assert plan.prompt_id == "faithful_text"
    assert plan.generation_options.get("repeat_penalty") == 1.2
    assert plan.recipe_id == "glm_ocr"


def test_granite_options_only_keeps_faithful_text(tmp_path: Path) -> None:
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
            name="granite3.2-vision:latest",
            digest="digest-granite",
            capabilities=["vision"],
            capability_known=True,
        )
    ]
    coord = JobCoordinator(
        paths, projects, provider, clock=clock, ids=ids, archive_runtime=_runtime(tmp_path)
    )
    project = projects.load()
    settings = project.settings
    settings.model_name = "granite3.2-vision"
    settings.prompt_id = "faithful_text"
    projects.save_settings(project, settings)
    plan = coord._build_plan(
        projects.load(), job_id="j1", page_ids=None, force=True, provider=provider
    )
    assert plan.prompt_id == "faithful_text"
    assert plan.generation_options.get("repeat_penalty") == 1.2
    assert plan.recipe_id == "granite_vision"


def test_glm_custom_prompt_still_overlays_options(tmp_path: Path) -> None:
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
            name="glm-ocr:latest",
            digest="digest-glm",
            capabilities=["vision"],
            capability_known=True,
        )
    ]
    coord = JobCoordinator(
        paths, projects, provider, clock=clock, ids=ids, archive_runtime=_runtime(tmp_path)
    )
    project = projects.load()
    settings = project.settings
    settings.model_name = "glm-ocr"
    settings.custom_prompt = "Transcribe this page exactly."
    projects.save_settings(project, settings)
    plan = coord._build_plan(
        projects.load(), job_id="j1", page_ids=None, force=True, provider=provider
    )
    assert plan.prompt_id == "custom"
    assert "exactly" in plan.prompt_text
    assert plan.generation_options.get("repeat_penalty") == 1.2
    assert plan.recipe_id == "glm_ocr"


def test_disabled_glm_recipe_skips_overlay(tmp_path: Path) -> None:
    from transcribe.services.ocr_model_recipe_store import set_recipe_enabled

    runtime = _runtime(tmp_path)
    set_recipe_enabled("glm_ocr", False, runtime=runtime)
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
            name="glm-ocr:latest",
            digest="digest-glm",
            capabilities=["vision"],
            capability_known=True,
        )
    ]
    coord = JobCoordinator(
        paths, projects, provider, clock=clock, ids=ids, archive_runtime=runtime
    )
    project = projects.load()
    settings = project.settings
    settings.model_name = "glm-ocr"
    projects.save_settings(project, settings)
    plan = coord._build_plan(
        projects.load(), job_id="j1", page_ids=None, force=True, provider=provider
    )
    assert "repeat_penalty" not in plan.generation_options
    assert plan.recipe_id == ""


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


def test_truncated_repetition_fails_and_keeps_prior_active(tmp_path: Path) -> None:
    projects, page_id = _project_with_page(tmp_path)
    good = _attempt("qwen1", text="notebook line", model="qwen2.5vl:3b")
    projects.record_generation(page_id, good, activate=True)
    looping = ("I'm talking lily and I'm not sure. ") * 6
    provider = FakeVisionOCRProvider(
        text_by_call=[looping],
        digest="digest-aaa",
        result_metadata={"truncated": True, "eval_count": 4096},
    )
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
    failed = next(a for a in result.attempts if a.attempt_id != "qwen1" and a.status == "failed")
    assert failed.error is not None
    assert failed.error.code == TOKEN_REPEAT_CODE
    assert failed.raw_text == looping


def test_truncated_without_repetition_succeeds(tmp_path: Path) -> None:
    projects, page_id = _project_with_page(tmp_path)
    provider = FakeVisionOCRProvider(
        text_by_call=["a unique notebook line with no looping span"],
        digest="digest-aaa",
        result_metadata={"truncated": True, "eval_count": 4096},
    )
    coord = JobCoordinator(
        projects.paths, projects, provider, clock=FakeClock(), ids=SequentialIds()
    )
    project = projects.load()
    settings = project.settings
    settings.model_name = "fake-vision"
    projects.save_settings(project, settings)
    progress = coord.run_blocking(page_ids=[page_id], force=True)
    assert progress.completed == 1
    result = projects.load_page_result(page_id)
    assert result is not None
    active = result.active_attempt()
    assert active is not None
    assert active.status == "succeeded"


def test_keyboard_interrupt_persists_and_aborts(tmp_path: Path) -> None:
    projects, page_id = _project_with_page(tmp_path)
    provider = FakeVisionOCRProvider(raise_interrupt=True, digest="digest-aaa")
    coord = JobCoordinator(
        projects.paths, projects, provider, clock=FakeClock(), ids=SequentialIds()
    )
    project = projects.load()
    settings = project.settings
    settings.model_name = "fake-vision"
    projects.save_settings(project, settings)
    with pytest.raises(KeyboardInterrupt):
        coord.run_blocking(page_ids=[page_id], force=True)
    assert provider.abort_calls == ["fake-vision"]
    result = projects.load_page_result(page_id)
    assert result is not None
    interrupted = [a for a in result.attempts if a.status == "interrupted"]
    assert len(interrupted) == 1
    assert interrupted[0].error is not None
    assert interrupted[0].error.code == "interrupted"
