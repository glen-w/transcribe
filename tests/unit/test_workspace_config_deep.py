"""Deepened workspace-config regressions (apply/reset/concurrency/project switch)."""

from __future__ import annotations

import threading
from pathlib import Path

import pytest

from transcribe.config.apply_ocr import (
    APPLY_OCR_FIELD_ALLOWLIST,
    apply_ocr_patch,
    preview_apply_ocr,
)
from transcribe.config.errors import ConfigError
from transcribe.config.facade import clear_config_cache, get_config, reload_config
from transcribe.config.models import OcrWorkspaceConfig, ProfileActivations
from transcribe.config.persistence import (
    load_workspace_settings,
    save_workspace_settings,
    settings_path,
)
from transcribe.config.reset import reset_field, reset_subtree, reset_whole_workspace
from transcribe.domain.models import OCRSettings
from transcribe.ports import SystemClock, UuidGenerator
from transcribe.runtime_paths import RuntimePaths, default_ollama_base_url
from transcribe.services.project import ProjectService, open_project_paths


@pytest.fixture()
def runtime(tmp_path: Path) -> RuntimePaths:
    clear_config_cache()
    data = tmp_path / "data"
    data.mkdir()
    (data / "config").mkdir()
    return RuntimePaths(
        repo_root=tmp_path,
        data_dir=data,
        projects_dir=tmp_path / "projects",
        inbox_dir=tmp_path / "inbox",
        export_dir=tmp_path / "exports",
    )


def test_apply_ocr_allowlisted_patch_not_wholesale(runtime: RuntimePaths) -> None:
    project = OCRSettings(
        model_name="keep-me",
        base_url="http://project:11434",
        max_workers=1,
        cleanup_enabled=False,
    )
    ws = OcrWorkspaceConfig(
        base_url="http://workspace:11434",
        max_workers=2,
        cleanup_enabled=True,
        cleanup_mode="sanitize_light",
        preprocess_profile="gentle_contrast",
    )
    plan = preview_apply_ocr(project, ws, fields={"base_url", "max_workers", "cleanup_enabled"})
    assert "model_name" not in plan.fields
    patched = apply_ocr_patch(project, plan)
    assert patched.model_name == "keep-me"
    assert patched.base_url == "http://workspace:11434"
    assert patched.max_workers == 2
    assert patched.cleanup_enabled is True


def test_ocr_preprocess_profile_seed_does_not_fingerprint_ui(
    runtime: RuntimePaths,
) -> None:
    from transcribe.analysis.cache_identity import config_fingerprint
    from transcribe.config.knobs import analysis_fingerprint_base, module_knob_dict
    from transcribe.config.models import EffectiveConfig

    assert "preprocess_profile" in APPLY_OCR_FIELD_ALLOWLIST
    save_workspace_settings(
        config={
            "analysis": {},
            "llm": {},
            "ocr": {"preprocess_profile": "gentle_contrast"},
            "ui": {"overview_cards": ["ner"]},
        },
        activations=ProfileActivations(),
        runtime=runtime,
    )
    clear_config_cache()
    view = get_config(runtime=runtime)
    assert view.effective.ocr.preprocess_profile == "gentle_contrast"

    seeded = EffectiveConfig(
        ocr=OcrWorkspaceConfig(preprocess_profile="gentle_contrast"),
    )
    baseline = EffectiveConfig()
    assert config_fingerprint(module_knob_dict(seeded, "stats")) == config_fingerprint(
        module_knob_dict(baseline, "stats")
    )
    base = analysis_fingerprint_base(seeded)
    assert "ui" not in base
    assert "overview_cards" not in base
    assert "preprocess_profile" not in base

    project = OCRSettings(preprocess_profile="none")
    plan = preview_apply_ocr(project, view.effective.ocr)
    assert plan.changed["preprocess_profile"] == ("none", "gentle_contrast")


def test_reset_scopes_do_not_touch_project_json(runtime: RuntimePaths, tmp_path: Path) -> None:
    projects_root = tmp_path / "projects"
    projects_root.mkdir()
    root = projects_root / "nb"
    paths = open_project_paths(root)
    svc = ProjectService(paths, clock=SystemClock(), ids=UuidGenerator())
    project = svc.create(title="t")
    before = paths.manifest.read_bytes()

    save_workspace_settings(
        config={
            "analysis": {"keyphrases": {"top_n": 3}},
            "llm": {"num_predict": 99},
            "ocr": {"max_workers": 2},
        },
        activations=ProfileActivations(workflow="quick"),
        runtime=runtime,
    )
    reset_field("llm.num_predict", runtime=runtime)
    reset_subtree("analysis", runtime=runtime)
    reset_whole_workspace(runtime=runtime)
    assert paths.manifest.read_bytes() == before
    loaded = svc.load(reconcile=False)
    assert loaded.id == project.id


def test_invalid_save_writes_nothing(runtime: RuntimePaths) -> None:
    path = settings_path(runtime)
    assert not path.exists()
    with pytest.raises(ConfigError):
        save_workspace_settings(
            config={"analysis": {}, "llm": {}, "ocr": {}, "mystery": {"x": 1}},
            activations=ProfileActivations(),
            runtime=runtime,
        )
    assert not path.exists()


def test_concurrent_saves_leave_valid_document(runtime: RuntimePaths) -> None:
    errors: list[BaseException] = []

    def writer(n: int) -> None:
        try:
            save_workspace_settings(
                config={
                    "analysis": {"keyphrases": {"top_n": n}},
                    "llm": {},
                    "ocr": {},
                },
                activations=ProfileActivations(),
                runtime=runtime,
            )
        except BaseException as exc:  # noqa: BLE001
            errors.append(exc)

    threads = [threading.Thread(target=writer, args=(i,)) for i in range(4, 12)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert not errors
    loaded = load_workspace_settings(runtime=runtime)
    assert "keyphrases" in (loaded.config.get("analysis") or {})
    top_n = loaded.config["analysis"]["keyphrases"]["top_n"]
    assert isinstance(top_n, int)


def test_project_switch_reloads_project_layer(runtime: RuntimePaths) -> None:
    a = OCRSettings(base_url="http://a:11434")
    b = OCRSettings(base_url="http://b:11434")
    view_a = reload_config(runtime=runtime, project_settings=a, project_id="proj-a")
    assert view_a.effective.ocr.base_url == "http://a:11434"
    view_b = get_config(runtime=runtime, project_settings=b, project_id="proj-b")
    assert view_b.effective.ocr.base_url == "http://b:11434"


def test_project_overlay_does_not_pollute_workspace_cache(
    runtime: RuntimePaths,
) -> None:
    """Job snapshots with cleanup-enabled project must not seed later creates."""
    dirty = OCRSettings(cleanup_enabled=True, cleanup_model_name="x", text_model_name="x")
    view_dirty = reload_config(runtime=runtime, project_settings=dirty, project_id="dirty")
    assert view_dirty.effective.ocr.cleanup_enabled is True
    view_clean = get_config(runtime=runtime)
    assert view_clean.effective.ocr.cleanup_enabled is False


def test_default_ollama_uses_env_allowlist(monkeypatch: pytest.MonkeyPatch) -> None:
    clear_config_cache()
    monkeypatch.setenv("TRANSCRIBE_OLLAMA_BASE_URL", "http://127.0.0.1:11434")
    assert default_ollama_base_url() == "http://127.0.0.1:11434"
    monkeypatch.setenv("TRANSCRIBE_OLLAMA_BASE_URL", "not-a-url")
    with pytest.raises(ConfigError):
        default_ollama_base_url()
    monkeypatch.delenv("TRANSCRIBE_OLLAMA_BASE_URL", raising=False)
    clear_config_cache()
    assert default_ollama_base_url() == "http://localhost:11434"


def test_promoted_ollama_env_not_read_raw_in_config_package() -> None:
    """Contract: config package uses allowlist; runtime_paths delegates to it."""
    src = Path("src/transcribe/runtime_paths.py").read_text(encoding="utf-8")
    assert "read_env_overlays" in src
    assert 'os.getenv("TRANSCRIBE_OLLAMA_BASE_URL")' not in src
