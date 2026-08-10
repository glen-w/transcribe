"""Prompt Hub resolver — workspace override → project → code builtin."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from transcribe.prompt_engine.adapters import (
    cleanup_templates_as_definitions,
    ocr_templates_as_definitions,
    resolve_cleanup_prompt_text,
    resolve_ocr_prompt_text,
)
from transcribe.prompt_engine.definition import PromptDefinition, PromptFamily, PromptRef
from transcribe.prompt_engine.registry import (
    VISION_PROMPT_FOR_TEXT,
    get_prompt as get_code_prompt,
    list_all_code_builtins,
)
from transcribe.prompt_engine.store import (
    load_custom_prompts,
    load_overrides,
    load_project_prompt_override,
)
from transcribe.runtime_paths import RuntimePaths, build_runtime_paths


@dataclass(frozen=True)
class PromptCatalogueEntry:
    definition: PromptDefinition
    source: str  # builtin | override | custom | project


def list_catalogue(
    *,
    runtime: RuntimePaths | None = None,
    project_prompts_dir: Path | None = None,
    family: PromptFamily | None = None,
) -> list[PromptCatalogueEntry]:
    rt = runtime or build_runtime_paths()
    overrides = load_overrides(rt)
    customs = {p.prompt_id: p for p in load_custom_prompts(rt)}
    entries: list[PromptCatalogueEntry] = []

    # OCR + cleanup adapters
    for defn in ocr_templates_as_definitions() + cleanup_templates_as_definitions():
        if defn.prompt_id in overrides:
            ov = overrides[defn.prompt_id]
            entries.append(PromptCatalogueEntry(definition=ov, source="override"))
        else:
            entries.append(PromptCatalogueEntry(definition=defn, source="builtin"))

    # Detection code builtins
    seen_ids: set[str] = set()
    for defn in list_all_code_builtins():
        if defn.prompt_id in seen_ids:
            continue
        seen_ids.add(defn.prompt_id)
        # prefer latest from get_code_prompt
        latest = get_code_prompt(defn.prompt_id) or defn
        if latest.prompt_id in overrides:
            entries.append(
                PromptCatalogueEntry(definition=overrides[latest.prompt_id], source="override")
            )
        else:
            entries.append(PromptCatalogueEntry(definition=latest, source="builtin"))

    for custom in customs.values():
        entries.append(PromptCatalogueEntry(definition=custom, source="custom"))

    if project_prompts_dir is not None and project_prompts_dir.exists():
        from transcribe.persistence.atomic import read_json
        from transcribe.persistence.schema import require_format

        for path in sorted(project_prompts_dir.glob("*.json")):
            try:
                data = require_format(read_json(path), "transcribe.prompt-definition")
                defn = PromptDefinition.from_dict(data)
                entries.append(PromptCatalogueEntry(definition=defn, source="project"))
            except Exception:  # noqa: BLE001
                continue

    if family is not None:
        entries = [e for e in entries if e.definition.prompt_family == family]
    # Dedupe by prompt_id preferring project > custom > override > builtin
    priority = {"project": 0, "custom": 1, "override": 2, "builtin": 3}
    best: dict[str, PromptCatalogueEntry] = {}
    for e in entries:
        pid = e.definition.prompt_id
        if pid not in best or priority[e.source] < priority[best[pid].source]:
            best[pid] = e
    return sorted(best.values(), key=lambda e: (e.definition.prompt_family.value, e.definition.prompt_id))


def resolve_prompt(
    prompt_id: str,
    *,
    version: str | None = None,
    runtime: RuntimePaths | None = None,
    project_prompts_dir: Path | None = None,
) -> PromptDefinition | None:
    """Prefer project override → workspace override → custom → code builtin (+ OCR/cleanup)."""
    rt = runtime or build_runtime_paths()
    if project_prompts_dir is not None:
        proj = load_project_prompt_override(project_prompts_dir, prompt_id)
        if proj is not None and (version is None or proj.version == version):
            return proj
    overrides = load_overrides(rt)
    if prompt_id in overrides:
        ov = overrides[prompt_id]
        if version is None or ov.version == version:
            return ov
    for custom in load_custom_prompts(rt):
        if custom.prompt_id == prompt_id and (version is None or custom.version == version):
            return custom
    code = get_code_prompt(prompt_id, version=version)
    if code is not None:
        return code
    for defn in ocr_templates_as_definitions() + cleanup_templates_as_definitions():
        if defn.prompt_id == prompt_id and (version is None or defn.version == version):
            return defn
    return None


def resolve_prompt_ref(
    ref: PromptRef,
    *,
    runtime: RuntimePaths | None = None,
    project_prompts_dir: Path | None = None,
) -> PromptDefinition | None:
    return resolve_prompt(
        ref.prompt_id,
        version=ref.version,
        runtime=runtime,
        project_prompts_dir=project_prompts_dir,
    )


def resolve_for_input_mode(
    text_prompt_id: str,
    *,
    want_vision: bool,
    runtime: RuntimePaths | None = None,
    project_prompts_dir: Path | None = None,
) -> PromptDefinition | None:
    """Pick vision twin when routing to vision; else text prompt (with overrides)."""
    if want_vision:
        vision_id = VISION_PROMPT_FOR_TEXT.get(text_prompt_id, text_prompt_id)
        return resolve_prompt(
            vision_id, runtime=runtime, project_prompts_dir=project_prompts_dir
        )
    return resolve_prompt(
        text_prompt_id, runtime=runtime, project_prompts_dir=project_prompts_dir
    )


def ocr_render_for_job(
    *,
    prompt_id: str,
    custom_prompt: str | None = None,
    runtime: RuntimePaths | None = None,
) -> tuple[str, str, str]:
    overrides = load_overrides(runtime)
    return resolve_ocr_prompt_text(
        prompt_id=prompt_id,
        custom_prompt=custom_prompt,
        override=overrides.get(prompt_id),
    )


def cleanup_render_for_job(
    *,
    mode: str,
    ocr_text: str,
    runtime: RuntimePaths | None = None,
) -> tuple[str, str, str]:
    from transcribe.services.cleanup_prompts import CLEANUP_REGISTRY

    tmpl = CLEANUP_REGISTRY.get(mode)
    prompt_id = tmpl.prompt_id if tmpl else ""
    overrides = load_overrides(runtime)
    return resolve_cleanup_prompt_text(
        mode=mode,
        ocr_text=ocr_text,
        override=overrides.get(prompt_id) if prompt_id else None,
    )
