"""Workspace persistence for custom prompts and built-in overrides."""

from __future__ import annotations

import re
from pathlib import Path

from transcribe.config.persistence import settings_lock_path
from transcribe.persistence.atomic import read_json, write_json_atomic
from transcribe.persistence.locks import FileLock
from transcribe.persistence.schema import require_format
from transcribe.prompt_engine.definition import (
    PromptDefinition,
    PromptFamily,
    validate_prompt_definition,
)
from transcribe.runtime_paths import RuntimePaths, build_runtime_paths

_SLUG_RE = re.compile(r"[^a-z0-9_-]+")


def prompts_root(runtime: RuntimePaths | None = None) -> Path:
    rt = runtime or build_runtime_paths()
    return rt.data_dir / "config" / "prompts"


def custom_prompts_dir(runtime: RuntimePaths | None = None) -> Path:
    return prompts_root(runtime) / "custom"


def overrides_dir(runtime: RuntimePaths | None = None) -> Path:
    return prompts_root(runtime) / "overrides"


def _safe_slug(prompt_id: str) -> str:
    return _SLUG_RE.sub("-", prompt_id.strip().lower()).strip("-") or "prompt"


def load_custom_prompts(runtime: RuntimePaths | None = None) -> list[PromptDefinition]:
    root = custom_prompts_dir(runtime)
    if not root.exists():
        return []
    out: list[PromptDefinition] = []
    for path in sorted(root.glob("*.json")):
        try:
            data = require_format(read_json(path), "transcribe.prompt-definition")
            data = {**data, "is_builtin": False}
            out.append(PromptDefinition.from_dict(data))
        except Exception:  # noqa: BLE001
            continue
    return out


def load_overrides(runtime: RuntimePaths | None = None) -> dict[str, PromptDefinition]:
    root = overrides_dir(runtime)
    if not root.exists():
        return {}
    out: dict[str, PromptDefinition] = {}
    for path in sorted(root.glob("*.json")):
        try:
            data = require_format(read_json(path), "transcribe.prompt-definition")
            defn = PromptDefinition.from_dict({**data, "is_override": True, "is_builtin": False})
            out[defn.prompt_id] = defn
        except Exception:  # noqa: BLE001
            continue
    return out


def save_custom_prompt(
    defn: PromptDefinition,
    *,
    runtime: RuntimePaths | None = None,
) -> Path:
    errors = validate_prompt_definition(defn)
    if errors:
        raise ValueError("; ".join(errors))
    rt = runtime or build_runtime_paths()
    root = custom_prompts_dir(rt)
    root.mkdir(parents=True, exist_ok=True)
    slug = _safe_slug(defn.prompt_id)
    path = root / f"{slug}.json"
    payload = defn.as_dict()
    payload["is_builtin"] = False
    payload["prompt_family"] = PromptFamily.CUSTOM.value
    with FileLock(settings_lock_path(rt), timeout=30.0):
        write_json_atomic(path, payload)
    return path


def save_override(
    defn: PromptDefinition,
    *,
    runtime: RuntimePaths | None = None,
) -> Path:
    errors = validate_prompt_definition(defn)
    if errors:
        raise ValueError("; ".join(errors))
    rt = runtime or build_runtime_paths()
    root = overrides_dir(rt)
    root.mkdir(parents=True, exist_ok=True)
    path = root / f"{_safe_slug(defn.prompt_id)}.json"
    payload = defn.as_dict()
    payload["is_override"] = True
    payload["is_builtin"] = False
    with FileLock(settings_lock_path(rt), timeout=30.0):
        write_json_atomic(path, payload)
    return path


def delete_custom_prompt(prompt_id: str, *, runtime: RuntimePaths | None = None) -> bool:
    rt = runtime or build_runtime_paths()
    path = custom_prompts_dir(rt) / f"{_safe_slug(prompt_id)}.json"
    if not path.exists():
        return False
    with FileLock(settings_lock_path(rt), timeout=30.0):
        path.unlink(missing_ok=True)
    return True


def delete_override(prompt_id: str, *, runtime: RuntimePaths | None = None) -> bool:
    rt = runtime or build_runtime_paths()
    path = overrides_dir(rt) / f"{_safe_slug(prompt_id)}.json"
    if not path.exists():
        return False
    with FileLock(settings_lock_path(rt), timeout=30.0):
        path.unlink(missing_ok=True)
    return True


def load_project_prompt_override(
    project_prompts_dir: Path,
    prompt_id: str,
) -> PromptDefinition | None:
    if not project_prompts_dir.exists():
        return None
    for path in project_prompts_dir.glob("*.json"):
        try:
            data = require_format(read_json(path), "transcribe.prompt-definition")
            if data.get("prompt_id") == prompt_id:
                return PromptDefinition.from_dict(data)
        except Exception:  # noqa: BLE001
            continue
    return None
