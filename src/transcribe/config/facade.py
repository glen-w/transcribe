"""Process cache, operation snapshots, and get_config facade."""

from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from typing import Iterator

from transcribe.config.models import EffectiveConfig, ProfileActivations
from transcribe.config.persistence import load_workspace_settings
from transcribe.config.resolve import ResolvedConfig, resolve_effective_config
from transcribe.domain.models import OCRSettings
from transcribe.runtime_paths import RuntimePaths, build_runtime_paths

_operation_config: ContextVar[EffectiveConfig | None] = ContextVar(
    "transcribe_operation_config",
    default=None,
)

# Workspace-only cache (never includes project OCR overlay).
_WS_CACHE: ResolvedConfig | None = None
_WS_CACHE_RUNTIME_KEY: str | None = None


@dataclass(frozen=True)
class ConfigView:
    """Facade returned by get_config()."""

    effective: EffectiveConfig
    provenance: dict[str, str]
    readonly_recovery: bool = False
    recovery_code: str | None = None
    recovery_message: str | None = None

    @property
    def analysis(self):  # noqa: ANN201
        return self.effective.analysis

    @property
    def llm(self):  # noqa: ANN201
        return self.effective.llm

    @property
    def ocr(self):  # noqa: ANN201
        return self.effective.ocr

    @property
    def activations(self) -> ProfileActivations:
        return self.effective.activations


def _runtime_key(runtime: RuntimePaths) -> str:
    return str(runtime.data_dir.resolve())


def _load_workspace_resolved(
    *,
    runtime: RuntimePaths,
    environ: dict[str, str] | None = None,
    recovery: str = "raise",
) -> ResolvedConfig:
    loaded = load_workspace_settings(runtime=runtime, recovery=recovery)  # type: ignore[arg-type]
    return resolve_effective_config(
        workspace_config=loaded.config,
        activations=loaded.activations,
        project_settings=None,
        runtime=runtime,
        environ=environ,
        readonly_recovery=loaded.readonly_recovery,
        recovery_code=loaded.recovery_code,
        recovery_message=loaded.recovery_message,
    )


def reload_config(
    *,
    runtime: RuntimePaths | None = None,
    project_settings: OCRSettings | None = None,
    project_id: str | None = None,
    environ: dict[str, str] | None = None,
    recovery: str = "raise",
) -> ConfigView:
    """Re-read workspace settings; optionally overlay project OCR for this view only."""
    global _WS_CACHE, _WS_CACHE_RUNTIME_KEY
    _ = project_id  # identity for callers; overlay is from project_settings
    rt = runtime or build_runtime_paths()
    ws = _load_workspace_resolved(runtime=rt, environ=environ, recovery=recovery)
    _WS_CACHE = ws
    _WS_CACHE_RUNTIME_KEY = _runtime_key(rt)

    if project_settings is not None:
        resolved = resolve_effective_config(
            workspace_config=ws.workspace_config,
            activations=ws.activations,
            project_settings=project_settings,
            runtime=rt,
            environ=environ,
            readonly_recovery=ws.readonly_recovery,
            recovery_code=ws.recovery_code,
            recovery_message=ws.recovery_message,
        )
    else:
        resolved = ws

    return ConfigView(
        effective=resolved.effective,
        provenance=resolved.provenance,
        readonly_recovery=resolved.readonly_recovery,
        recovery_code=resolved.recovery_code,
        recovery_message=resolved.recovery_message,
    )


def get_config(
    *,
    runtime: RuntimePaths | None = None,
    project_settings: OCRSettings | None = None,
    project_id: str | None = None,
) -> ConfigView:
    """Return config view. Process cache is workspace-only; project overlay is per-call."""
    global _WS_CACHE, _WS_CACHE_RUNTIME_KEY
    _ = project_id
    rt = runtime or build_runtime_paths()
    key = _runtime_key(rt)
    if _WS_CACHE is None or _WS_CACHE_RUNTIME_KEY != key:
        return reload_config(
            runtime=rt,
            project_settings=project_settings,
            project_id=project_id,
            recovery="defaults_readonly",
        )

    if project_settings is not None:
        resolved = resolve_effective_config(
            workspace_config=_WS_CACHE.workspace_config,
            activations=_WS_CACHE.activations,
            project_settings=project_settings,
            runtime=rt,
            environ=None,
            readonly_recovery=_WS_CACHE.readonly_recovery,
            recovery_code=_WS_CACHE.recovery_code,
            recovery_message=_WS_CACHE.recovery_message,
        )
        return ConfigView(
            effective=resolved.effective,
            provenance=resolved.provenance,
            readonly_recovery=resolved.readonly_recovery,
            recovery_code=resolved.recovery_code,
            recovery_message=resolved.recovery_message,
        )

    return ConfigView(
        effective=_WS_CACHE.effective,
        provenance=_WS_CACHE.provenance,
        readonly_recovery=_WS_CACHE.readonly_recovery,
        recovery_code=_WS_CACHE.recovery_code,
        recovery_message=_WS_CACHE.recovery_message,
    )


def clear_config_cache() -> None:
    global _WS_CACHE, _WS_CACHE_RUNTIME_KEY
    _WS_CACHE = None
    _WS_CACHE_RUNTIME_KEY = None


def snapshot_for_operation(
    *,
    runtime: RuntimePaths | None = None,
    project_settings: OCRSettings | None = None,
    project_id: str | None = None,
) -> EffectiveConfig:
    """Capture immutable effective config for a run/job."""
    view = reload_config(
        runtime=runtime,
        project_settings=project_settings,
        project_id=project_id,
        recovery="defaults_readonly",
    )
    return view.effective


@contextmanager
def bind_operation_config(cfg: EffectiveConfig) -> Iterator[EffectiveConfig]:
    token = _operation_config.set(cfg)
    try:
        yield cfg
    finally:
        _operation_config.reset(token)


def require_operation_config() -> EffectiveConfig:
    """Config for the current operation, or workspace cache if none bound.

    Modules in a batch must run under ``bind_operation_config``. Outside a run
    (UI/tests), falls back to workspace ``get_config().effective`` (no project
    overlay unless the caller bound a snapshot).
    """
    bound = _operation_config.get()
    if bound is not None:
        return bound
    return get_config().effective


def operation_config_or_none() -> EffectiveConfig | None:
    return _operation_config.get()
