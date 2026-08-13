"""Acceptance: multipass → rank → composite → prefer → finetune export (offline)."""

from __future__ import annotations

import json
from pathlib import Path

from transcribe.analysis.llm_runtime import RecordedDoubleClient
from transcribe.ingest import IngestService
from transcribe.providers.base import ModelInfo
from transcribe.services.finetune_export import (
    FinetuneExportOptions,
    FinetuneExportService,
)
from transcribe.services.job import JobCoordinator
from transcribe.services.multipass import MultiPassCoordinator
from transcribe.services.project import ProjectService, open_project_paths
from tests.conftest import FakeClock, SequentialIds
from tests.fakes import FakeVisionOCRProvider

FIXTURE = Path(__file__).resolve().parents[2] / "fixtures" / "mini_page.png"


class RankCompositeClient(RecordedDoubleClient):
    """Returns valid rank JSON when prompt asks to rank; otherwise merges text."""

    def generate_with_meta(self, *, model, prompt, system=None, options=None):
        if "rank competing OCR" in prompt.lower() or '"order"' in prompt or "Candidates:" in prompt and "JSON" in prompt:
            # Extract attempt ids from prompt labels
            import re

            ids = re.findall(r"attempt_id=([^\s]+)", prompt)
            # de-dupe preserving order
            seen = []
            for i in ids:
                if i not in seen:
                    seen.append(i)
            if len(seen) >= 2:
                # Prefer second model first for a deterministic non-trivial order
                order = list(reversed(seen))
                payload = {"order": order, "rationales": {x: "ok" for x in order}}
                return json.dumps(payload), {}
        if "merge competing OCR" in prompt.lower() or "composite transcription" in prompt.lower():
            # Format uses "--- attempt_id=… model=… ---\n<body>\n"
            chunks = prompt.split("---")
            texts: list[str] = []
            i = 1
            while i < len(chunks):
                header = chunks[i]
                if "attempt_id=" in header and i + 1 < len(chunks):
                    body = chunks[i + 1].strip()
                    if body:
                        texts.append(body)
                    i += 2
                else:
                    i += 1
            merged = " ".join(texts) if texts else "alpha notebook weather metro notes day"
            return merged, {}
        return super().generate_with_meta(
            model=model, prompt=prompt, system=system, options=options
        )


def _setup_project(tmp_path: Path) -> tuple[ProjectService, JobCoordinator, list[str]]:
    paths = open_project_paths(tmp_path / "proj")
    clock, ids = FakeClock(), SequentialIds()
    projects = ProjectService(paths, clock=clock, ids=ids)
    projects.create("Lifecycle")
    ingest = IngestService(paths, clock=clock, ids=ids)
    png = FIXTURE.read_bytes() if FIXTURE.is_file() else None
    if png is None:
        from tests.ingest.test_ingest import _png_bytes

        png = _png_bytes()
    for i in range(2):
        ingest.import_bytes(f"p{i}.png", png)
    project = projects.load()
    settings = project.settings
    settings.model_name = "vision-a"
    settings.text_model_name = "text-rank"
    settings.cleanup_model_name = "text-rank"
    settings.prefer_mode = "prefer_is_promote"
    settings.auto_activate_composite = True
    projects.save_settings(project, settings)
    models = [
        ModelInfo(
            name="vision-a",
            digest="digest-a",
            capabilities=["vision"],
            capability_known=True,
        ),
        ModelInfo(
            name="vision-b",
            digest="digest-b",
            capabilities=["vision"],
            capability_known=True,
        ),
    ]
    provider = FakeVisionOCRProvider(
        text_by_call=[
            "alpha notebook weather metro",
            "alpha notebook weather metro",
            "beta notebook metro notes weather day",
            "beta notebook metro notes weather day",
        ],
        models=models,
        digest="digest-a",
        verified=True,
    )
    # resolve_model_identity uses per-model digest from models list
    coord = JobCoordinator(
        paths,
        projects,
        provider,
        clock=clock,
        ids=ids,
        cleanup_client=RankCompositeClient(responses={"default": "unused"}),
    )
    page_ids = [p.page_id for p in projects.load().pages]
    return projects, coord, page_ids


def test_multipass_rank_composite_prefer_finetune(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("TRANSCRIBE_DATA_DIR", str(tmp_path / "data"))
    projects, coord, page_ids = _setup_project(tmp_path)
    text_client = RankCompositeClient(responses={"default": "fallback"})
    multi = MultiPassCoordinator(
        jobs=coord,
        projects=projects,
        clock=projects.clock,
        ids=projects.ids,
        text_client=text_client,
    )
    progress = multi.run_blocking(
        model_names=["vision-a", "vision-b"],
        force=True,
        auto_activate_composite=True,
    )
    assert progress.status == "completed"
    assert progress.pages_ranked >= 1
    assert progress.pages_composite >= 1

    page_id = page_ids[0]
    result = projects.load_page_result(page_id)
    assert result is not None
    vision = [
        a
        for a in result.attempts
        if a.status == "succeeded" and (a.attempt_kind or "vision") == "vision"
    ]
    composites = [
        a
        for a in result.attempts
        if a.status == "succeeded" and (a.attempt_kind or "") == "composite"
    ]
    assert len(vision) >= 2
    assert len(composites) >= 1
    assert result.comparison is not None
    assert "composite" not in [
        (result.attempt_by_id(i).attempt_kind if result.attempt_by_id(i) else "")
        for i in result.comparison.ranked_attempt_ids
    ]
    assert result.active_attempt_id == composites[0].attempt_id

    # Prefer an older vision attempt under prefer_only
    project = projects.load()
    settings = project.settings
    settings.prefer_mode = "prefer_only"
    projects.save_settings(project, settings)
    other = vision[0].attempt_id
    prefer_result = projects.set_preferred_attempt(
        page_id, other, mode="prefer_only"
    )
    assert prefer_result.preferred_attempt_id == other
    assert prefer_result.active_attempt_id == composites[0].attempt_id

    out = FinetuneExportService(projects.paths, projects).export(
        tmp_path / "ft",
        options=FinetuneExportOptions(
            require_preferred=True,
            include_rejected_candidates=True,
        ),
    )
    rows = (out / "samples.jsonl").read_text(encoding="utf-8").strip().splitlines()
    assert rows
    sample = json.loads(rows[0])
    assert sample["source"]["attempt_id"] == other
    assert (out / "manifest.json").is_file()


def test_multipass_resume_after_partial_vision(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("TRANSCRIBE_DATA_DIR", str(tmp_path / "data"))
    projects, coord, page_ids = _setup_project(tmp_path)
    text_client = RankCompositeClient(responses={"default": "fallback"})
    multi = MultiPassCoordinator(
        jobs=coord,
        projects=projects,
        clock=projects.clock,
        ids=projects.ids,
        text_client=text_client,
    )
    # First pass: only run first model by forcing start and stopping after one model
    # Simulate by running full then checking resume API on incomplete record.
    progress = multi.run_blocking(
        model_names=["vision-a", "vision-b"],
        force=True,
    )
    assert progress.status == "completed"
    pass_id = progress.pass_id
    # Mark job as incomplete mid-vision for resume path
    from transcribe.persistence.atomic import read_json, write_json_atomic

    path = projects.paths.jobs_dir / f"multipass_{pass_id}.json"
    payload = read_json(path)
    payload["status"] = "failed"
    payload["phase"] = "vision"
    payload["model_index"] = 1
    write_json_atomic(path, payload)

    # Clear comparisons so resume re-runs rank/composite after finishing vision
    for page_id in page_ids:
        result = projects.load_page_result(page_id)
        assert result is not None
        result.comparison = None
        # drop composites for this pass so resume recreates them
        kept = [
            a
            for a in result.attempts
            if not (
                (a.attempt_kind or "") == "composite" and a.pass_id == pass_id
            )
        ]
        result.attempts = kept
        if result.active_attempt_id and not any(
            a.attempt_id == result.active_attempt_id for a in kept
        ):
            result.active_attempt_id = kept[-1].attempt_id if kept else None
        if result.preferred_attempt_id and not any(
            a.attempt_id == result.preferred_attempt_id for a in kept
        ):
            result.preferred_attempt_id = None
        from transcribe.persistence.atomic import write_json_atomic as wja

        wja(projects.paths.result_path(page_id), result.as_dict())

    resumed = multi.resume_blocking(pass_id)
    assert resumed.status == "completed"
    assert resumed.pass_id == pass_id


def test_multipass_vision_phases_skip_cleanup_by_default(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("TRANSCRIBE_DATA_DIR", str(tmp_path / "data"))
    projects, coord, page_ids = _setup_project(tmp_path)
    project = projects.load()
    settings = project.settings
    settings.cleanup_enabled = True
    settings.cleanup_mode = "strip_leak"
    settings.cleanup_model_name = "text-rank"
    projects.save_settings(project, settings)

    class CountingCleanupClient(RankCompositeClient):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            self.generate_calls = 0

        def generate_with_meta(self, *, model, prompt, system=None, options=None):
            self.generate_calls += 1
            return super().generate_with_meta(
                model=model, prompt=prompt, system=system, options=options
            )

    cleanup = CountingCleanupClient(responses={"default": "should-not-run"})
    coord.cleanup_client = cleanup
    text_client = RankCompositeClient(responses={"default": "fallback"})
    multi = MultiPassCoordinator(
        jobs=coord,
        projects=projects,
        clock=projects.clock,
        ids=projects.ids,
        text_client=text_client,
    )
    progress = multi.run_blocking(
        model_names=["vision-a", "vision-b"],
        force=True,
        cleanup_enabled=False,
    )
    assert progress.status == "completed"
    assert cleanup.generate_calls == 0
    for page_id in page_ids:
        result = projects.load_page_result(page_id)
        assert result is not None
        for attempt in result.attempts:
            if (attempt.attempt_kind or "vision") != "vision":
                continue
            if attempt.status != "succeeded":
                continue
            status = attempt.cleanup.execution_status if attempt.cleanup else "disabled"
            assert status == "disabled"


def test_multipass_cancel_skips_remaining_models(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("TRANSCRIBE_DATA_DIR", str(tmp_path / "data"))
    projects, coord, _page_ids = _setup_project(tmp_path)
    holder: dict = {}

    class CancelAfterFirst(FakeVisionOCRProvider):
        def transcribe_image(self, *, model, prompt, image_bytes, options):
            if model == "vision-b":
                raise AssertionError("second vision model should not run after cancel")
            result = super().transcribe_image(
                model=model,
                prompt=prompt,
                image_bytes=image_bytes,
                options=options,
            )
            holder["multi"].request_cancel()
            return result

    models = list(coord.provider.models)
    coord.provider = CancelAfterFirst(
        text_by_call=[
            "alpha notebook weather metro",
            "alpha notebook weather metro",
        ],
        models=models,
        digest="digest-a",
        verified=True,
    )
    text_client = RankCompositeClient(responses={"default": "fallback"})
    multi = MultiPassCoordinator(
        jobs=coord,
        projects=projects,
        clock=projects.clock,
        ids=projects.ids,
        text_client=text_client,
    )
    holder["multi"] = multi
    progress = multi.run_blocking(
        model_names=["vision-a", "vision-b"],
        force=True,
    )
    assert progress.status == "cancelled"
    assert coord.provider.calls >= 1
    vision_b = 0
    for page in projects.load().pages:
        result = projects.load_page_result(page.page_id)
        if result is None:
            continue
        vision_b += sum(
            1
            for a in result.attempts
            if a.provenance and a.provenance.model_name == "vision-b"
        )
    assert vision_b == 0
