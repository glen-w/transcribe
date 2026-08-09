"""Process cache, operation snapshots, and get_config facade."""

from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from typing import Any, Iterator

from transcribe.config.models import EffectiveConfig, ProfileActivations
from transcribe.config.persistence import load_workspace_settings
from transcribe.config.resolve import ResolvedConfig, resolve_effective_config
from transcribe.domain.models import OCRSettings
from transcribe.runtime_paths import RuntimePaths, build_runtime_paths

_operation_config: ContextVar[EffectiveConfig | None] = ContextVar(
    "transcribe_operation_config",
    default=None,
)

_CACHE: ResolvedConfig | None = None
_CACHE_PROJECT_ID: str | None = None
_CACHE_RUNTIME_KEY: str | None = None


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


def reload_config(
    *,
    runtime: RuntimePaths | None = None,
    project_settings: OCRSettings | None = None,
    project_id: str | None = None,
    environ: dict[str, str] | None = None,
    recovery: str = "raise",
) -> ConfigView:
    """Re-read workspace settings and rebuild the process cache."""
    global _CACHE, _CACHE_PROJECT_ID, _CACHE_RUNTIME_KEY
    rt = runtime or build_runtime_paths()
    loaded = load_workspace_settings(runtime=rt, recovery=recovery)  # type: ignore[arg-type]
    resolved = resolve_effective_config(
        workspace_config=loaded.config,
        activations=loaded.activations,
        project_settings=project_settings,
        runtime=rt,
        environ=environ,
        readonly_recovery=loaded.readonly_recovery,
        recovery_code=loaded.recovery_code,
        recovery_message=loaded.recovery_message,
    )
    _CACHE = resolved
    _CACHE_PROJECT_ID = project_id
    _CACHE_RUNTIME_KEY = _runtime_key(rt)
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
    """Return cached ConfigView; reload when project or data_dir changes."""
    global _CACHE, _CACHE_PROJECT_ID, _CACHE_RUNTIME_KEY
    rt = runtime or build_runtime_paths()
    key = _runtime_key(rt)
    if (
        _CACHE is None
        or _CACHE_RUNTIME_KEY != key
        or (project_id is not None and project_id != _CACHE_PROJECT_ID)
        or (project_settings is not None and project_id is None)
    ):
        # When project_settings provided without id, still reload to apply overrides
        return reload_config(
            runtime=rt,
            project_settings=project_settings,
            project_id=project_id,
            recovery="defaults_readonly",
        )
    return ConfigView(
        effective=_CACHE.effective,
        provenance=_CACHE.provenance,
        readonly_recovery=_CACHE.readonly_recovery,
        recovery_code=_CACHE.recovery_code,
        recovery_message=_CACHE.recovery_message,
    )


def clear_config_cache() -> None:
    global _CACHE, _CACHE_PROJECT_ID, _CACHE_RUNTIME_KEY
    _CACHE = None
    _CACHE_PROJECT_ID = None
    _CACHE_RUNTIME_KEY = None


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
    """Config for the current operation, or process cache if none bound.

    Modules in a batch must run under ``bind_operation_config``. Outside a run
    (UI/tests), falls back to ``get_config().effective``.
    """
    bound = _operation_config.get()
    if bound is not None:
        return bound
    return get_config().effective


def operation_config_or_none() -> EffectiveConfig | None:
    return _operation_config.get()
