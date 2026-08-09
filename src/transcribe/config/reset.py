"""Reset scopes: field, subtree, profile, workspace."""

from __future__ import annotations

from typing import Any, Literal

from transcribe.config.models import ProfileActivations, deep_merge_dict
from transcribe.config.persistence import (
    LoadedWorkspace,
    load_workspace_settings,
    reset_workspace_settings,
    save_workspace_settings,
)
from transcribe.config.profiles import validate_target_id
from transcribe.runtime_paths import RuntimePaths

ResetScope = Literal["field", "subtree", "profile", "workspace"]

_SUBTREE_PREFIXES = {
    "analysis": ("analysis",),
    "analysis.ui_presets": ("analysis", "ui_presets"),
    "llm": ("llm",),
    "ocr": ("ocr",),
}


def _delete_path(cfg: dict[str, Any], parts: tuple[str, ...]) -> None:
    if not parts:
        return
    if len(parts) == 1:
        cfg.pop(parts[0], None)
        return
    child = cfg.get(parts[0])
    if isinstance(child, dict):
        _delete_path(child, parts[1:])
        if not child:
            cfg.pop(parts[0], None)


def reset_field(
    path: str,
    *,
    runtime: RuntimePaths | None = None,
) -> LoadedWorkspace:
    """Remove one dotted workspace key (e.g. llm.num_predict). Does not touch project.json."""
    loaded = load_workspace_settings(runtime=runtime)
    parts = tuple(path.split("."))
    cfg = deep_merge_dict({}, loaded.config)
    _delete_path(cfg, parts)
    return save_workspace_settings(
        config=cfg,
        activations=loaded.activations,
        runtime=runtime,
    )


def reset_subtree(
    subtree: str,
    *,
    runtime: RuntimePaths | None = None,
) -> LoadedWorkspace:
    """Clear workspace keys under a known subtree. Does not touch project.json."""
    if subtree not in _SUBTREE_PREFIXES:
        raise ValueError(f"unknown subtree reset: {subtree!r}")
    loaded = load_workspace_settings(runtime=runtime)
    cfg = deep_merge_dict({}, loaded.config)
    _delete_path(cfg, _SUBTREE_PREFIXES[subtree])
    return save_workspace_settings(
        config=cfg,
        activations=loaded.activations,
        runtime=runtime,
    )


def reset_profile_activation(
    target: str,
    *,
    runtime: RuntimePaths | None = None,
) -> LoadedWorkspace:
    """Set activation to default for one target. Does not modify profile files or project.json."""
    target_id = validate_target_id(target)
    loaded = load_workspace_settings(runtime=runtime)
    acts = ProfileActivations(
        workflow="default" if target_id == "workflow" else loaded.activations.workflow,
        ocr="default" if target_id == "ocr" else loaded.activations.ocr,
        llm="default" if target_id == "llm" else loaded.activations.llm,
    )
    return save_workspace_settings(
        config=loaded.config,
        activations=acts,
        runtime=runtime,
    )


def reset_whole_workspace(*, runtime: RuntimePaths | None = None) -> LoadedWorkspace:
    """Archive settings.json and write factory defaults. Never modifies project.json."""
    return reset_workspace_settings(runtime=runtime)
