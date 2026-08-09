"""Profile name policy, paths, load/save (activation-pointer content SoT)."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from transcribe.config.defaults import (
    RESERVED_PROFILE_NAMES,
    builtin_profile_config,
    is_builtin_profile,
    validate_target_id,
)
from transcribe.config.errors import (
    PROFILE_CORRUPT,
    PROFILE_NAME_INVALID,
    PROFILE_NOT_FOUND,
    PROFILE_RESERVED_NAME,
    PROFILE_SCHEMA_UNSUPPORTED,
    ConfigError,
)
from transcribe.config.models import ProfileTargetId
from transcribe.config.versions import (
    CURRENT_PROFILE_SCHEMA_VERSION,
    PROFILE_FORMAT,
    SUPPORTED_PROFILE_SCHEMA_VERSIONS,
)
from transcribe.persistence.atomic import read_json, write_json_atomic
from transcribe.runtime_paths import RuntimePaths, build_runtime_paths

_NAME_RE = re.compile(r"^[a-z][a-z0-9_]{0,63}$")


def validate_profile_name(name: str, *, for_save_as: bool = False) -> str:
    """Normalize and validate a profile name; raise ConfigError on failure."""
    normalized = str(name or "").strip().lower()
    if not _NAME_RE.fullmatch(normalized):
        raise ConfigError(
            PROFILE_NAME_INVALID,
            "profile name must match ^[a-z][a-z0-9_]{0,63}$",
        )
    if for_save_as and normalized in RESERVED_PROFILE_NAMES:
        raise ConfigError(
            PROFILE_RESERVED_NAME,
            f"profile name {normalized!r} is reserved",
        )
    return normalized


def profiles_root(runtime: RuntimePaths | None = None) -> Path:
    rt = runtime or build_runtime_paths()
    return rt.data_dir / "config" / "profiles"


def profile_path(
    target: ProfileTargetId,
    name: str,
    *,
    runtime: RuntimePaths | None = None,
) -> Path:
    target = validate_target_id(target)
    name = validate_profile_name(name, for_save_as=False)
    return profiles_root(runtime) / target / f"{name}.json"


def load_profile_overlay(
    target: ProfileTargetId,
    name: str,
    *,
    runtime: RuntimePaths | None = None,
) -> dict[str, Any]:
    """Return config overlay for builtin or user profile."""
    target = validate_target_id(target)
    name = validate_profile_name(name, for_save_as=False)
    builtin = builtin_profile_config(target, name)
    if builtin is not None:
        return dict(builtin)
    path = profile_path(target, name, runtime=runtime)
    if not path.is_file():
        raise ConfigError(
            PROFILE_NOT_FOUND,
            f"profile not found: {target}/{name}",
        )
    try:
        raw = read_json(path)
    except Exception as exc:
        raise ConfigError(
            PROFILE_CORRUPT,
            f"could not parse profile {target}/{name}: {exc}",
        ) from exc
    if not isinstance(raw, dict):
        raise ConfigError(PROFILE_CORRUPT, f"profile {target}/{name} is not an object")
    fmt = raw.get("format")
    if fmt != PROFILE_FORMAT:
        raise ConfigError(
            PROFILE_CORRUPT,
            f"profile {target}/{name} has unexpected format {fmt!r}",
        )
    ver = raw.get("schema_version")
    if not isinstance(ver, int):
        raise ConfigError(
            PROFILE_CORRUPT,
            f"profile {target}/{name} missing schema_version",
        )
    if ver not in SUPPORTED_PROFILE_SCHEMA_VERSIONS:
        if ver > CURRENT_PROFILE_SCHEMA_VERSION:
            raise ConfigError(
                PROFILE_SCHEMA_UNSUPPORTED,
                f"profile schema_version {ver} is newer than supported",
            )
        raise ConfigError(
            PROFILE_SCHEMA_UNSUPPORTED,
            f"profile schema_version {ver} is not supported",
        )
    if raw.get("target_id") != target or raw.get("name") != name:
        raise ConfigError(
            PROFILE_CORRUPT,
            f"profile identity mismatch for {target}/{name}",
        )
    cfg = raw.get("config")
    if not isinstance(cfg, dict):
        raise ConfigError(PROFILE_CORRUPT, f"profile {target}/{name} config missing")
    return dict(cfg)


def save_user_profile(
    target: ProfileTargetId,
    name: str,
    config: dict[str, Any],
    *,
    runtime: RuntimePaths | None = None,
    overwrite: bool = False,
) -> Path:
    """Persist a user profile. Rejects reserved/builtin names."""
    target = validate_target_id(target)
    name = validate_profile_name(name, for_save_as=True)
    if is_builtin_profile(target, name):
        raise ConfigError(
            PROFILE_RESERVED_NAME,
            f"cannot overwrite builtin profile {target}/{name}",
        )
    path = profile_path(target, name, runtime=runtime)
    if path.exists() and not overwrite:
        raise ConfigError(
            PROFILE_NAME_INVALID,
            f"profile already exists: {target}/{name} (pass overwrite=True)",
        )
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "format": PROFILE_FORMAT,
        "schema_version": CURRENT_PROFILE_SCHEMA_VERSION,
        "target_id": target,
        "name": name,
        "config": config,
    }
    write_json_atomic(path, payload)
    return path


def list_user_profile_names(
    target: ProfileTargetId,
    *,
    runtime: RuntimePaths | None = None,
) -> list[str]:
    target = validate_target_id(target)
    root = profiles_root(runtime) / target
    if not root.is_dir():
        return []
    names: list[str] = []
    for path in sorted(root.glob("*.json")):
        try:
            names.append(validate_profile_name(path.stem, for_save_as=False))
        except ConfigError:
            continue
    return names
