"""Central typed env overlays for promoted config keys."""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Callable
from urllib.parse import urlparse

from transcribe.config.errors import ENV_INVALID, ConfigError


def _parse_ollama_url(raw: str) -> str:
    value = raw.strip()
    if not value:
        raise ConfigError(ENV_INVALID, "TRANSCRIBE_OLLAMA_BASE_URL is empty")
    parsed = urlparse(value)
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        raise ConfigError(
            ENV_INVALID,
            "TRANSCRIBE_OLLAMA_BASE_URL must be an http(s) root URL",
        )
    if parsed.path not in ("", "/"):
        raise ConfigError(
            ENV_INVALID,
            "TRANSCRIBE_OLLAMA_BASE_URL must be the server root without a path",
        )
    return value.rstrip("/")


@dataclass(frozen=True)
class EnvKeySpec:
    var: str
    config_path: tuple[str, ...]
    parse: Callable[[str], Any]


ENV_ALLOWLIST: tuple[EnvKeySpec, ...] = (
    EnvKeySpec(
        var="TRANSCRIBE_OLLAMA_BASE_URL",
        config_path=("ocr", "base_url"),
        parse=_parse_ollama_url,
    ),
)


def read_env_overlays(
    *,
    environ: Mapping[str, str] | None = None,
) -> tuple[dict[str, Any], dict[str, str]]:
    """Return (nested overlay dict, provenance map path→env:VAR).

    Only sets keys when the env var is present and non-empty after strip.
    """
    env = environ if environ is not None else os.environ
    overlay: dict[str, Any] = {}
    provenance: dict[str, str] = {}
    for spec in ENV_ALLOWLIST:
        raw = env.get(spec.var)
        if raw is None or not str(raw).strip():
            continue
        value = spec.parse(str(raw))
        cursor: dict[str, Any] = overlay
        for part in spec.config_path[:-1]:
            nxt = cursor.setdefault(part, {})
            assert isinstance(nxt, dict)
            cursor = nxt
        cursor[spec.config_path[-1]] = value
        provenance[".".join(spec.config_path)] = f"env:{spec.var}"
    return overlay, provenance
