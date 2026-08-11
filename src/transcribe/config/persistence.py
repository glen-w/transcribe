"""Atomic locked workspace settings.json I/O with corrupt/refuse policy."""

from __future__ import annotations

import shutil
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from transcribe.config.errors import (
    SETTINGS_CORRUPT,
    SETTINGS_LOCK_TIMEOUT,
    SETTINGS_SAVE_VERIFY_FAILED,
    SETTINGS_SCHEMA_UNSUPPORTED,
    ConfigError,
)
from transcribe.config.models import (
    KNOWN_CONFIG_SUBTREES,
    ProfileActivations,
    empty_config_dict,
    strip_unknown_config_keys,
    workspace_document,
)
from transcribe.config.versions import (
    CURRENT_SETTINGS_SCHEMA_VERSION,
    SETTINGS_FORMAT,
    SUPPORTED_SETTINGS_SCHEMA_VERSIONS,
)
from transcribe.persistence.atomic import read_json, write_json_atomic
from transcribe.persistence.locks import FileLock, LockTimeoutError
from transcribe.runtime_paths import RuntimePaths, build_runtime_paths

RecoveryPolicy = Literal["raise", "defaults_readonly"]


@dataclass(frozen=True)
class LoadedWorkspace:
    config: dict[str, Any]
    activations: ProfileActivations
    path: Path
    schema_version: int
    readonly_recovery: bool = False
    recovery_code: str | None = None
    recovery_message: str | None = None


def settings_path(runtime: RuntimePaths | None = None) -> Path:
    rt = runtime or build_runtime_paths()
    return rt.data_dir / "config" / "settings.json"


def settings_lock_path(runtime: RuntimePaths | None = None) -> Path:
    rt = runtime or build_runtime_paths()
    return rt.data_dir / "config" / ".transcribe.settings.lock"


def empty_workspace_payload() -> dict[str, Any]:
    acts = ProfileActivations()
    return workspace_document(
        config=empty_config_dict(),
        activations=acts,
        schema_version=CURRENT_SETTINGS_SCHEMA_VERSION,
    )


def _validate_document(raw: Any, *, path: Path) -> tuple[dict[str, Any], ProfileActivations, int]:
    if not isinstance(raw, dict):
        raise ConfigError(SETTINGS_CORRUPT, f"{path} is not a JSON object")
    fmt = raw.get("format")
    if fmt != SETTINGS_FORMAT:
        raise ConfigError(
            SETTINGS_CORRUPT,
            f"{path} unexpected format {fmt!r}",
        )
    ver = raw.get("schema_version")
    if not isinstance(ver, int):
        raise ConfigError(SETTINGS_CORRUPT, f"{path} missing schema_version")
    if ver not in SUPPORTED_SETTINGS_SCHEMA_VERSIONS:
        if ver > CURRENT_SETTINGS_SCHEMA_VERSION:
            raise ConfigError(
                SETTINGS_SCHEMA_UNSUPPORTED,
                f"settings schema_version {ver} is newer than supported",
            )
        raise ConfigError(
            SETTINGS_SCHEMA_UNSUPPORTED,
            f"settings schema_version {ver} is not supported",
        )
    cfg = raw.get("config")
    if cfg is None:
        cfg = {}
    if not isinstance(cfg, dict):
        raise ConfigError(SETTINGS_CORRUPT, f"{path} config must be an object")
    # Forbid unknown top-level config keys on load for safety
    unknown = set(cfg) - KNOWN_CONFIG_SUBTREES
    if unknown:
        raise ConfigError(
            SETTINGS_CORRUPT,
            f"{path} unknown config keys: {sorted(unknown)}",
        )
    activations = ProfileActivations(
        workflow=str(raw.get("active_workflow_profile") or "default"),
        ocr=str(raw.get("active_ocr_profile") or "default"),
        llm=str(raw.get("active_llm_profile") or "default"),
        export=str(raw.get("active_export_profile") or "default"),
    )
    return strip_unknown_config_keys(cfg), activations, ver


def load_workspace_settings(
    *,
    runtime: RuntimePaths | None = None,
    recovery: RecoveryPolicy = "raise",
) -> LoadedWorkspace:
    path = settings_path(runtime)
    if not path.is_file():
        return LoadedWorkspace(
            config=empty_config_dict(),
            activations=ProfileActivations(),
            path=path,
            schema_version=CURRENT_SETTINGS_SCHEMA_VERSION,
        )
    try:
        raw = read_json(path)
        config, activations, ver = _validate_document(raw, path=path)
        return LoadedWorkspace(
            config=config,
            activations=activations,
            path=path,
            schema_version=ver,
        )
    except ConfigError as exc:
        if recovery != "defaults_readonly":
            raise
        return LoadedWorkspace(
            config=empty_config_dict(),
            activations=ProfileActivations(),
            path=path,
            schema_version=CURRENT_SETTINGS_SCHEMA_VERSION,
            readonly_recovery=True,
            recovery_code=exc.code,
            recovery_message=str(exc),
        )
    except Exception as exc:
        err = ConfigError(SETTINGS_CORRUPT, f"could not parse {path}: {exc}")
        if recovery != "defaults_readonly":
            raise err from exc
        return LoadedWorkspace(
            config=empty_config_dict(),
            activations=ProfileActivations(),
            path=path,
            schema_version=CURRENT_SETTINGS_SCHEMA_VERSION,
            readonly_recovery=True,
            recovery_code=SETTINGS_CORRUPT,
            recovery_message=str(err),
        )


def save_workspace_settings(
    *,
    config: dict[str, Any],
    activations: ProfileActivations,
    runtime: RuntimePaths | None = None,
    timeout: float = 30.0,
) -> LoadedWorkspace:
    """Validate full prospective document, lock, atomic write, reload+verify."""
    rt = runtime or build_runtime_paths()
    path = settings_path(rt)
    lock_path = settings_lock_path(rt)
    path.parent.mkdir(parents=True, exist_ok=True)

    cleaned = strip_unknown_config_keys(config)
    if set(config.keys()) - KNOWN_CONFIG_SUBTREES:
        unknown = sorted(set(config.keys()) - KNOWN_CONFIG_SUBTREES)
        raise ConfigError(
            SETTINGS_CORRUPT,
            f"unknown config keys refused on save: {unknown}",
        )
    # Ensure activations resolve (builtin or user profile on disk)
    from transcribe.config.profiles import load_profile_overlay

    for target, name in (
        ("workflow", activations.workflow),
        ("ocr", activations.ocr),
        ("llm", activations.llm),
        ("export", activations.export),
    ):
        load_profile_overlay(target, name, runtime=rt)

    payload = workspace_document(
        config=cleaned,
        activations=activations,
        schema_version=CURRENT_SETTINGS_SCHEMA_VERSION,
    )
    # Validate by round-tripping through the same loader rules
    _validate_document(payload, path=path)

    lock = FileLock(lock_path, timeout=timeout)
    try:
        lock.acquire()
    except LockTimeoutError as exc:
        raise ConfigError(SETTINGS_LOCK_TIMEOUT, str(exc)) from exc
    try:
        write_json_atomic(path, payload)
        raw = read_json(path)
        loaded_cfg, loaded_acts, ver = _validate_document(raw, path=path)
        if loaded_cfg != cleaned or loaded_acts != activations:
            raise ConfigError(
                SETTINGS_SAVE_VERIFY_FAILED,
                "persisted settings did not match prospective document",
            )
        return LoadedWorkspace(
            config=loaded_cfg,
            activations=loaded_acts,
            path=path,
            schema_version=ver,
        )
    finally:
        lock.release()


def archive_corrupt_settings(*, runtime: RuntimePaths | None = None) -> Path | None:
    """Move bad settings aside; return archive path if a file existed."""
    path = settings_path(runtime)
    if not path.is_file():
        return None
    stamp = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
    dest = path.with_name(f"settings.corrupt.{stamp}.json")
    shutil.move(str(path), str(dest))
    return dest


def reset_workspace_settings(*, runtime: RuntimePaths | None = None) -> LoadedWorkspace:
    """Archive current settings (if any) and write factory empty workspace."""
    rt = runtime or build_runtime_paths()
    path = settings_path(rt)
    lock = FileLock(settings_lock_path(rt), timeout=30.0)
    try:
        lock.acquire()
    except LockTimeoutError as exc:
        raise ConfigError(SETTINGS_LOCK_TIMEOUT, str(exc)) from exc
    try:
        if path.is_file():
            stamp = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
            archive = path.with_name(f"settings.reset.{stamp}.json")
            shutil.copy2(path, archive)
        acts = ProfileActivations()
        payload = empty_workspace_payload()
        write_json_atomic(path, payload)
        return LoadedWorkspace(
            config=empty_config_dict(),
            activations=acts,
            path=path,
            schema_version=CURRENT_SETTINGS_SCHEMA_VERSION,
        )
    finally:
        lock.release()
