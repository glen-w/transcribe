"""Workspace overlay for OCR model recipes.

Source of truth: ``{TRANSCRIBE_DATA_DIR}/config/ocr-model-recipes.json``.
Missing file → builtins only. Corrupt / unsupported schema → builtins, error
surfaced to Settings; never silent overwrite.
"""

from __future__ import annotations

import copy
import logging
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

from transcribe.config.errors import (
    OCR_RECIPES_CORRUPT,
    OCR_RECIPES_INVALID,
    OCR_RECIPES_LOCK_TIMEOUT,
    OCR_RECIPES_SCHEMA_UNSUPPORTED,
    ConfigError,
)
from transcribe.config.persistence import settings_lock_path
from transcribe.persistence.atomic import read_json, write_json_atomic
from transcribe.persistence.locks import FileLock, LockTimeoutError
from transcribe.persistence.schema import SchemaError, require_format
from transcribe.runtime_paths import RuntimePaths, build_runtime_paths
from transcribe.services.ocr_model_recipes import (
    ADVICE_KINDS,
    ALLOWED_GENERATION_OPTION_KEYS,
    MATCH_MODES,
    RECIPES,
    OcrModelRecipe,
)

_log = logging.getLogger(__name__)

RECIPE_FORMAT = "transcribe.ocr-model-recipes"
RECIPE_FILENAME = "ocr-model-recipes.json"
_RECIPE_ID_RE = re.compile(r"^[a-z][a-z0-9_]{1,63}$")


@dataclass(frozen=True)
class RecipeLoadResult:
    overlay_rows: tuple[dict[str, Any], ...]
    effective: tuple[OcrModelRecipe, ...]
    path: Path
    error_code: str | None = None
    error_message: str | None = None

    @property
    def ok(self) -> bool:
        return self.error_code is None


def recipes_path(runtime: RuntimePaths | None = None) -> Path:
    rt = runtime or build_runtime_paths()
    return rt.data_dir / "config" / RECIPE_FILENAME


def known_ocr_prompt_ids(*, runtime: RuntimePaths | None = None) -> set[str]:
    from transcribe.prompts import REGISTRY as OCR_REGISTRY

    ids = set(OCR_REGISTRY)
    try:
        from transcribe.prompt_engine.definition import PromptFamily
        from transcribe.prompt_engine.hub import list_catalogue

        for entry in list_catalogue(runtime=runtime, family=PromptFamily.OCR):
            ids.add(entry.definition.prompt_id)
    except Exception:  # noqa: BLE001 — catalogue is advisory at save time
        _log.debug("OCR prompt catalogue unavailable; using builtin registry", exc_info=True)
    return ids


def sanitize_generation_options(raw: Any) -> dict[str, Any]:
    if raw is None:
        return {}
    if not isinstance(raw, Mapping):
        raise ConfigError(
            OCR_RECIPES_INVALID, "generation_options must be an object"
        )
    out: dict[str, Any] = {}
    for key, value in raw.items():
        name = str(key)
        if name not in ALLOWED_GENERATION_OPTION_KEYS:
            raise ConfigError(
                OCR_RECIPES_INVALID,
                f"unsupported generation option {name!r}",
            )
        if name == "repeat_penalty":
            try:
                penalty = float(value)
            except (TypeError, ValueError) as exc:
                raise ConfigError(
                    OCR_RECIPES_INVALID, "repeat_penalty must be a number"
                ) from exc
            if penalty != penalty or penalty < 0.0 or penalty > 2.0:  # noqa: PLR0124 — NaN check
                raise ConfigError(OCR_RECIPES_INVALID, "repeat_penalty out of range")
            out[name] = penalty
        elif name == "stop":
            if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
                raise ConfigError(
                    OCR_RECIPES_INVALID, "stop must be a list of strings"
                )
            out[name] = [str(item) for item in value]
        elif name == "temperature":
            try:
                temp = float(value)
            except (TypeError, ValueError) as exc:
                raise ConfigError(
                    OCR_RECIPES_INVALID, "temperature must be a number"
                ) from exc
            if temp != temp or temp < 0.0 or temp > 2.0:  # noqa: PLR0124 — NaN check
                raise ConfigError(OCR_RECIPES_INVALID, "temperature out of range")
            out[name] = temp
        elif name == "num_predict":
            try:
                npred = int(value)
            except (TypeError, ValueError) as exc:
                raise ConfigError(
                    OCR_RECIPES_INVALID, "num_predict must be an integer"
                ) from exc
            if isinstance(value, bool) or npred < 64 or npred > 8192:
                raise ConfigError(OCR_RECIPES_INVALID, "num_predict out of range")
            out[name] = npred
    return out


def _string_tuple(raw: Any, *, field_name: str) -> tuple[str, ...]:
    if raw is None:
        return ()
    if isinstance(raw, str):
        token = raw.strip()
        return (token,) if token else ()
    if not isinstance(raw, (list, tuple)):
        raise ConfigError(OCR_RECIPES_INVALID, f"{field_name} must be a list of strings")
    out: list[str] = []
    for item in raw:
        token = str(item).strip()
        if token:
            out.append(token)
    return tuple(out)


def _warnings_tuple(raw: Any) -> tuple[str, ...]:
    if raw is None:
        return ()
    if isinstance(raw, str):
        text = raw.strip()
        return (text,) if text else ()
    if not isinstance(raw, (list, tuple)):
        raise ConfigError(OCR_RECIPES_INVALID, "warnings must be a list of strings")
    return tuple(str(item) for item in raw if str(item).strip())


def validate_overlay_row(
    row: Mapping[str, Any],
    *,
    runtime: RuntimePaths | None = None,
    require_complete: bool = False,
) -> None:
    rid = str(row.get("recipe_id") or "").strip()
    if not rid or not _RECIPE_ID_RE.match(rid):
        raise ConfigError(
            OCR_RECIPES_INVALID,
            "recipe_id must be a lowercase slug (letter, then letters/digits/_)",
        )
    builtin_ids = {recipe.recipe_id for recipe in RECIPES}
    is_custom = rid not in builtin_ids
    if require_complete or is_custom:
        tokens = row.get("match_tokens", None if is_custom else ())
        if is_custom and not _string_tuple(tokens, field_name="match_tokens"):
            raise ConfigError(
                OCR_RECIPES_INVALID, f"{rid}: match_tokens must be a non-empty list"
            )
        title = str(row.get("title") or "").strip()
        if is_custom and not title:
            raise ConfigError(OCR_RECIPES_INVALID, f"{rid}: title is required")
        prompt_id = str(row.get("prompt_id") or "").strip()
        freeze = row.get("freeze_prompt")
        freeze_prompt = True if freeze is None else bool(freeze)
        if is_custom and freeze_prompt and not prompt_id:
            raise ConfigError(
                OCR_RECIPES_INVALID, f"{rid}: prompt_id is required when freeze_prompt is true"
            )
    if "match_mode" in row and row["match_mode"] not in MATCH_MODES:
        raise ConfigError(OCR_RECIPES_INVALID, f"{rid}: match_mode must be any or all")
    if "advice_kind" in row and row["advice_kind"] not in ADVICE_KINDS:
        raise ConfigError(OCR_RECIPES_INVALID, f"{rid}: unknown advice_kind")
    if "generation_options" in row:
        sanitize_generation_options(row.get("generation_options"))
    prompt_id = str(row.get("prompt_id") or "").strip()
    if prompt_id:
        known = known_ocr_prompt_ids(runtime=runtime)
        if prompt_id not in known:
            raise ConfigError(
                OCR_RECIPES_INVALID, f"{rid}: unknown OCR prompt_id {prompt_id!r}"
            )


def _apply_overlay_row(
    base: OcrModelRecipe | None,
    row: Mapping[str, Any],
    *,
    source: str,
) -> OcrModelRecipe:
    if base is None:
        freeze = row.get("freeze_prompt")
        prompt_id = str(row.get("prompt_id") or "").strip() or "faithful_markdown"
        return OcrModelRecipe(
            recipe_id=str(row.get("recipe_id") or "").strip(),
            title=str(row.get("title") or row.get("recipe_id") or "").strip(),
            match_tokens=_string_tuple(row.get("match_tokens"), field_name="match_tokens"),
            match_mode=str(row.get("match_mode") or "any"),
            exclude_tokens=_string_tuple(
                row.get("exclude_tokens"), field_name="exclude_tokens"
            ),
            prompt_id=prompt_id,
            freeze_prompt=True if freeze is None else bool(freeze),
            generation_options=sanitize_generation_options(row.get("generation_options")),
            warnings=_warnings_tuple(row.get("warnings")),
            advice_kind=str(row.get("advice_kind") or "ocr_oriented"),
            enabled=True if "enabled" not in row else bool(row.get("enabled")),
            source=source,
        )
    updates: dict[str, Any] = {"source": source}
    if "title" in row and str(row.get("title") or "").strip():
        updates["title"] = str(row["title"]).strip()
    if "match_tokens" in row:
        updates["match_tokens"] = _string_tuple(
            row.get("match_tokens"), field_name="match_tokens"
        )
    if "match_mode" in row:
        updates["match_mode"] = str(row.get("match_mode") or "any")
    if "exclude_tokens" in row:
        updates["exclude_tokens"] = _string_tuple(
            row.get("exclude_tokens"), field_name="exclude_tokens"
        )
    if "prompt_id" in row and str(row.get("prompt_id") or "").strip():
        updates["prompt_id"] = str(row["prompt_id"]).strip()
    if "freeze_prompt" in row:
        updates["freeze_prompt"] = bool(row.get("freeze_prompt"))
    if "generation_options" in row:
        merged = dict(base.generation_options)
        incoming = sanitize_generation_options(
            {k: v for k, v in dict(row.get("generation_options") or {}).items() if v is not None}
        )
        merged.update(incoming)
        raw_opts = row.get("generation_options") or {}
        for key, value in dict(raw_opts).items():
            if value is None:
                merged.pop(str(key), None)
        updates["generation_options"] = merged
    if "warnings" in row:
        updates["warnings"] = _warnings_tuple(row.get("warnings"))
    if "advice_kind" in row:
        updates["advice_kind"] = str(row.get("advice_kind") or base.advice_kind)
    if "enabled" in row:
        updates["enabled"] = bool(row.get("enabled"))
    return replace(base, **updates)


def merge_recipes(overlay_rows: Sequence[Mapping[str, Any]]) -> tuple[OcrModelRecipe, ...]:
    """User rows prepend (higher priority). Same recipe_id overlays the builtin."""
    builtins = {recipe.recipe_id: recipe for recipe in RECIPES}
    seen: set[str] = set()
    merged: list[OcrModelRecipe] = []
    for raw in overlay_rows:
        if not isinstance(raw, Mapping):
            continue
        rid = str(raw.get("recipe_id") or "").strip()
        if not rid or rid in seen:
            continue
        try:
            validate_overlay_row(raw, require_complete=False)
        except ConfigError:
            _log.warning("skipping invalid OCR recipe overlay row %s", rid, exc_info=True)
            continue
        base = builtins.get(rid)
        source = "override" if base is not None else "custom"
        try:
            recipe = _apply_overlay_row(base, raw, source=source)
        except ConfigError:
            _log.warning("skipping unreadable OCR recipe overlay row %s", rid, exc_info=True)
            continue
        merged.append(recipe)
        seen.add(rid)
    for recipe in RECIPES:
        if recipe.recipe_id not in seen:
            merged.append(recipe)
    return tuple(merged)


def load_recipes(runtime: RuntimePaths | None = None) -> RecipeLoadResult:
    rt = runtime or build_runtime_paths()
    path = recipes_path(rt)
    if not path.exists():
        return RecipeLoadResult(
            overlay_rows=(),
            effective=RECIPES,
            path=path,
        )
    try:
        payload = read_json(path)
    except (OSError, ValueError, TypeError) as exc:
        return RecipeLoadResult(
            overlay_rows=(),
            effective=RECIPES,
            path=path,
            error_code=OCR_RECIPES_CORRUPT,
            error_message=f"{path} is unreadable: {exc}",
        )
    if not isinstance(payload, dict):
        return RecipeLoadResult(
            overlay_rows=(),
            effective=RECIPES,
            path=path,
            error_code=OCR_RECIPES_CORRUPT,
            error_message=f"{path} is not a JSON object",
        )
    fmt = payload.get("format")
    version = payload.get("schema_version")
    if fmt != RECIPE_FORMAT:
        return RecipeLoadResult(
            overlay_rows=(),
            effective=RECIPES,
            path=path,
            error_code=OCR_RECIPES_CORRUPT,
            error_message=f"{path} unexpected format {fmt!r}",
        )
    if not isinstance(version, int):
        return RecipeLoadResult(
            overlay_rows=(),
            effective=RECIPES,
            path=path,
            error_code=OCR_RECIPES_CORRUPT,
            error_message=f"{path} missing schema_version",
        )
    if version != 1:
        code = (
            OCR_RECIPES_SCHEMA_UNSUPPORTED
            if version > 1
            else OCR_RECIPES_CORRUPT
        )
        return RecipeLoadResult(
            overlay_rows=(),
            effective=RECIPES,
            path=path,
            error_code=code,
            error_message=(
                f"{path} unsupported schema_version {version}; this build supports 1"
            ),
        )
    try:
        require_format(payload, RECIPE_FORMAT)
    except SchemaError as exc:
        return RecipeLoadResult(
            overlay_rows=(),
            effective=RECIPES,
            path=path,
            error_code=OCR_RECIPES_CORRUPT,
            error_message=str(exc),
        )
    raw_rows = payload.get("recipes")
    if raw_rows is None:
        rows: list[dict[str, Any]] = []
    elif not isinstance(raw_rows, list):
        return RecipeLoadResult(
            overlay_rows=(),
            effective=RECIPES,
            path=path,
            error_code=OCR_RECIPES_CORRUPT,
            error_message=f"{path} recipes must be a list",
        )
    else:
        rows = [dict(item) for item in raw_rows if isinstance(item, Mapping)]
    return RecipeLoadResult(
        overlay_rows=tuple(copy.deepcopy(row) for row in rows),
        effective=merge_recipes(rows),
        path=path,
    )


def load_effective_recipes(
    runtime: RuntimePaths | None = None,
) -> tuple[OcrModelRecipe, ...]:
    return load_recipes(runtime).effective


def save_overlay_rows(
    rows: Sequence[Mapping[str, Any]],
    *,
    runtime: RuntimePaths | None = None,
) -> Path:
    rt = runtime or build_runtime_paths()
    path = recipes_path(rt)
    cleaned: list[dict[str, Any]] = []
    seen: set[str] = set()
    for raw in rows:
        if not isinstance(raw, Mapping):
            raise ConfigError(OCR_RECIPES_INVALID, "each recipe overlay must be an object")
        validate_overlay_row(raw, runtime=rt, require_complete=False)
        rid = str(raw.get("recipe_id") or "").strip()
        if rid in seen:
            raise ConfigError(OCR_RECIPES_INVALID, f"duplicate recipe_id {rid}")
        seen.add(rid)
        cleaned.append(copy.deepcopy(dict(raw)))
        cleaned[-1]["recipe_id"] = rid
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "format": RECIPE_FORMAT,
        "schema_version": 1,
        "recipes": cleaned,
    }
    try:
        with FileLock(settings_lock_path(rt), timeout=30.0):
            write_json_atomic(path, payload)
    except LockTimeoutError as exc:
        raise ConfigError(
            OCR_RECIPES_LOCK_TIMEOUT, f"timed out locking {settings_lock_path(rt)}"
        ) from exc
    return path


def upsert_overlay_row(
    row: Mapping[str, Any],
    *,
    runtime: RuntimePaths | None = None,
) -> Path:
    loaded = load_recipes(runtime)
    if loaded.error_code:
        raise ConfigError(loaded.error_code, loaded.error_message or "recipe overlay unreadable")
    validate_overlay_row(row, runtime=runtime, require_complete=False)
    rid = str(row.get("recipe_id") or "").strip()
    rows = [dict(item) for item in loaded.overlay_rows if str(item.get("recipe_id")) != rid]
    rows.insert(0, dict(row))
    rows[0]["recipe_id"] = rid
    return save_overlay_rows(rows, runtime=runtime)


def set_recipe_enabled(
    recipe_id: str,
    enabled: bool,
    *,
    runtime: RuntimePaths | None = None,
) -> Path:
    loaded = load_recipes(runtime)
    if loaded.error_code:
        raise ConfigError(loaded.error_code, loaded.error_message or "recipe overlay unreadable")
    rid = str(recipe_id).strip()
    rows = [dict(item) for item in loaded.overlay_rows]
    for row in rows:
        if str(row.get("recipe_id")) == rid:
            row["enabled"] = bool(enabled)
            return save_overlay_rows(rows, runtime=runtime)
    rows.append({"recipe_id": rid, "enabled": bool(enabled)})
    return save_overlay_rows(rows, runtime=runtime)


def remove_overlay_row(recipe_id: str, *, runtime: RuntimePaths | None = None) -> Path:
    loaded = load_recipes(runtime)
    if loaded.error_code:
        raise ConfigError(loaded.error_code, loaded.error_message or "recipe overlay unreadable")
    rid = str(recipe_id).strip()
    rows = [dict(item) for item in loaded.overlay_rows if str(item.get("recipe_id")) != rid]
    return save_overlay_rows(rows, runtime=runtime)


def reset_overlay(*, runtime: RuntimePaths | None = None) -> Path:
    """Write an empty overlay (builtins only). Explicit user action."""
    return save_overlay_rows([], runtime=runtime)
