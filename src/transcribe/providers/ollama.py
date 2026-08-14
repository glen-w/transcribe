"""Ollama HTTP client for vision OCR."""

from __future__ import annotations

import base64
import ipaddress
import json
import socket
import threading
import time
import urllib.error
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, TypeVar
from urllib.parse import urlparse

from transcribe.domain.models import DEFAULT_VISION_NUM_PREDICT
from transcribe.errors import ProviderError
from transcribe.providers.base import DiscoveryResult, ModelInfo, ProviderResult

_DISCOVERY_TTL_S = 45.0
DEFAULT_MAX_RETRIES = 3
_RETRY_BASE_DELAY_S = 0.5

T = TypeVar("T")

# Ollama/llama-server fatal load failures that will not recover mid-job.
_FATAL_MODEL_LOAD_MARKERS = (
    "unknown model architecture",
    "error loading model",
    "llama-server process has terminated",
)


def is_fatal_model_load_error(message: str) -> bool:
    """True when Ollama cannot load the selected model (architecture/loader crash)."""
    lower = (message or "").lower()
    return any(marker in lower for marker in _FATAL_MODEL_LOAD_MARKERS)


def friendly_model_load_message(raw: str) -> str:
    """Plain-language message for fatal model-load HTTP bodies."""
    lower = (raw or "").lower()
    if "unknown model architecture" in lower:
        return (
            "Ollama cannot load this vision model (architecture unsupported). "
            "Try another vision model, or upgrade/re-pull the model for this "
            "Ollama build."
        )
    if "error loading model" in lower or "llama-server process has terminated" in lower:
        return (
            "Ollama failed to load this vision model (loader crash). "
            "Try another vision model, or check Ollama logs / re-pull the model."
        )
    return (raw or "").strip() or "Ollama failed to load this vision model"


def call_with_retries(
    op: Callable[[], T],
    *,
    max_retries: int = DEFAULT_MAX_RETRIES,
    sleep: Callable[[float], None] = time.sleep,
) -> tuple[T, int]:
    """Run ``op``, retrying retriable :class:`ProviderError`s with exponential backoff.

    Defaults: 3 attempts, delays 0.5s / 1s between retries. Returns
    ``(result, attempt_index)`` where ``attempt_index`` is 0 on first-try success.
    """
    if max_retries < 1:
        raise ValueError("max_retries must be >= 1")
    last_error: ProviderError | None = None
    for attempt in range(max_retries):
        try:
            return op(), attempt
        except ProviderError as exc:
            last_error = exc
            if not exc.retriable or attempt + 1 >= max_retries:
                raise
            sleep(_RETRY_BASE_DELAY_S * (2**attempt))
    assert last_error is not None
    raise last_error


_discovery_lock = threading.Lock()
_discovery_cache: dict[str, "_DiscoveryEntry"] = {}


@dataclass
class _DiscoveryEntry:
    at: float
    models: list[ModelInfo]
    error: str | None


def discovery_cache_key(base_url: str, *, request_timeout: float = 300.0) -> str:
    """Key for shared discovery metadata (URL + transport timeout)."""
    return f"{normalize_base_url(base_url)}|timeout={float(request_timeout)}"


def invalidate_discovery_cache(base_url: str | None = None) -> None:
    """Drop cached discovery for one URL (all timeouts) or the entire cache."""
    with _discovery_lock:
        if base_url is None:
            _discovery_cache.clear()
            return
        prefix = f"{normalize_base_url(base_url)}|"
        for key in list(_discovery_cache):
            if key.startswith(prefix):
                del _discovery_cache[key]


def get_cached_discovery(
    base_url: str,
    *,
    request_timeout: float = 300.0,
    discovery_ttl: float = _DISCOVERY_TTL_S,
    refresh: bool = False,
    fetch: Any | None = None,
) -> tuple[list[ModelInfo], str | None]:
    """Thread-safe discovery metadata cache keyed by URL + transport config.

    ``fetch`` is ``Callable[[], tuple[list[ModelInfo], str | None]]`` used on miss.
    """
    key = discovery_cache_key(base_url, request_timeout=request_timeout)
    now = time.monotonic()
    with _discovery_lock:
        if not refresh:
            entry = _discovery_cache.get(key)
            if entry is not None and now - entry.at < discovery_ttl:
                return list(entry.models), entry.error
    if fetch is None:
        raise TypeError("fetch is required when discovery cache misses")
    models, error = fetch()
    with _discovery_lock:
        _discovery_cache[key] = _DiscoveryEntry(
            at=time.monotonic(), models=list(models), error=error
        )
    return list(models), error


def normalize_base_url(url: str) -> str:
    text = (url or "").strip()
    if not text:
        raise ProviderError("Ollama base URL is empty", code="invalid_url")
    parsed = urlparse(text)
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        raise ProviderError(
            "Enter the Ollama server root, e.g. http://localhost:11434.",
            code="invalid_url",
        )
    path = (parsed.path or "").rstrip("/")
    if path and path != "":
        # Reject /api/... and any non-root path.
        raise ProviderError(
            "Enter the Ollama server root, e.g. http://localhost:11434.",
            code="invalid_url",
        )
    return f"{parsed.scheme}://{parsed.netloc}".rstrip("/")


def is_loopback_host(url: str) -> bool:
    host = urlparse(url).hostname or ""
    if host in {"localhost", "127.0.0.1", "::1"}:
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        try:
            infos = socket.getaddrinfo(host, None)
        except socket.gaierror:
            return False
        for info in infos:
            try:
                if ipaddress.ip_address(info[4][0]).is_loopback:
                    return True
            except (ValueError, IndexError):
                continue
        return False


def is_local_machine_host(url: str) -> bool:
    """True when OCR traffic stays on this machine (loopback or Docker→host)."""
    if is_loopback_host(url):
        return True
    host = (urlparse(url).hostname or "").lower()
    return host in {"host.docker.internal"}


def ollama_healthcheck(base_url: str, *, timeout: float = 10.0) -> bool:
    """Return True when Ollama responds at ``base_url``."""
    try:
        OllamaVisionProvider(base_url, request_timeout=timeout).healthcheck()
        return True
    except (ProviderError, OSError, urllib.error.URLError):
        return False


def resolve_reachable_ollama_base_url(
    configured: str | None,
    *,
    fallback: str | None = None,
) -> str:
    """Pick an Ollama base URL that responds to healthcheck.

    Prefer ``configured`` when healthy, else workspace/env fallback (e.g. Docker
  → ``host.docker.internal``). Falls back to the first valid candidate when none
    respond so callers still surface connection errors.
    """
    from transcribe.runtime_paths import default_ollama_base_url

    candidates: list[str] = []
    for raw in (configured, fallback, default_ollama_base_url()):
        text = (raw or "").strip()
        if not text:
            continue
        try:
            url = normalize_base_url(text)
        except ProviderError:
            continue
        if url not in candidates:
            candidates.append(url)
    for url in candidates:
        if ollama_healthcheck(url):
            return url
    if candidates:
        return candidates[0]
    return default_ollama_base_url()


def _allowlisted_metadata(
    payload: dict[str, Any],
    *,
    retry_count: int,
    options: dict[str, Any] | None = None,
) -> dict[str, Any]:
    meta: dict[str, Any] = {"retry_count": retry_count}
    for key in (
        "total_duration",
        "load_duration",
        "prompt_eval_count",
        "eval_count",
        "prompt_eval_duration",
        "eval_duration",
    ):
        if key in payload and isinstance(payload[key], (int, float)):
            meta[key] = payload[key]
    eval_count = meta.get("eval_count")
    num_predict = (options or {}).get("num_predict")
    if (
        isinstance(eval_count, (int, float))
        and isinstance(num_predict, (int, float))
        and int(num_predict) > 0
        and int(eval_count) >= int(num_predict)
    ):
        meta["truncated"] = True
    return meta


class OllamaVisionProvider:
    provider_id = "ollama"

    def __init__(
        self,
        base_url: str = "http://localhost:11434",
        *,
        request_timeout: float = 300.0,
        discovery_ttl: float = _DISCOVERY_TTL_S,
        max_retries: int = DEFAULT_MAX_RETRIES,
    ) -> None:
        self.base_url = normalize_base_url(base_url)
        self.request_timeout = request_timeout
        self.discovery_ttl = discovery_ttl
        self.max_retries = max_retries

    def healthcheck(self) -> None:
        self._http_get("/api/tags", timeout=min(10.0, self.request_timeout))

    def list_models(self, *, refresh: bool = False) -> DiscoveryResult:
        models, error = self._discover(refresh=refresh)
        return DiscoveryResult(models=models, error=error)

    def list_vision_models(self, *, refresh: bool = False) -> DiscoveryResult:
        result = self.list_models(refresh=refresh)
        vision = [m for m in result.models if m.capability_known and "vision" in m.capabilities]
        return DiscoveryResult(models=vision, error=result.error)

    def resolve_model_identity(self, model_name: str) -> tuple[str | None, bool]:
        result = self.list_models()
        for model in result.models:
            if model.name == model_name:
                if model.digest:
                    return model.digest, True
                return None, False
        return None, False

    def transcribe_image(
        self,
        *,
        model: str,
        prompt: str,
        image_bytes: bytes,
        options: dict[str, Any],
    ) -> ProviderResult:
        image_b64 = base64.b64encode(image_bytes).decode("ascii")
        gen_options = dict(options or {})
        if "num_predict" not in gen_options:
            gen_options["num_predict"] = DEFAULT_VISION_NUM_PREDICT
        body = {
            "model": model,
            "prompt": prompt,
            "stream": False,
            "images": [image_b64],
            "options": gen_options,
        }
        digest, verified = self.resolve_model_identity(model)

        def once() -> dict[str, Any]:
            payload = self._http_post("/api/generate", body, timeout=self.request_timeout)
            if not isinstance(payload, dict):
                raise ProviderError(
                    "Ollama returned a non-object JSON response",
                    code="bad_response",
                )
            text = payload.get("response")
            if not isinstance(text, str):
                raise ProviderError(
                    "Ollama response missing text field",
                    code="bad_response",
                )
            return payload

        payload, attempt = call_with_retries(once, max_retries=self.max_retries)
        return ProviderResult(
            text=str(payload["response"]),
            model=model,
            model_digest=digest,
            model_identity_verified=verified,
            provider_metadata=_allowlisted_metadata(
                payload, retry_count=attempt, options=gen_options
            ),
        )

    def _discover(self, *, refresh: bool) -> tuple[list[ModelInfo], str | None]:
        def fetch() -> tuple[list[ModelInfo], str | None]:
            return self._discover_uncached()

        return get_cached_discovery(
            self.base_url,
            request_timeout=self.request_timeout,
            discovery_ttl=self.discovery_ttl,
            refresh=refresh,
            fetch=fetch,
        )

    def _discover_uncached(self) -> tuple[list[ModelInfo], str | None]:
        try:
            tags = self._http_get("/api/tags", timeout=min(30.0, self.request_timeout))
            models_raw = tags.get("models") if isinstance(tags, dict) else None
            if not isinstance(models_raw, list):
                raise ProviderError("Malformed /api/tags response", code="bad_response")
            models: list[ModelInfo] = []
            for row in models_raw:
                if not isinstance(row, dict) or not row.get("name"):
                    continue
                name = str(row["name"])
                digest = row.get("digest")
                digest_s = str(digest) if digest else None
                details = row.get("details") if isinstance(row.get("details"), dict) else {}
                caps: list[str] = []
                capability_known = False
                show = self._show(name)
                if show is not None:
                    raw_caps = show.get("capabilities")
                    if isinstance(raw_caps, list):
                        capability_known = True
                        caps = [str(c) for c in raw_caps]
                    show_details = show.get("details")
                    if isinstance(show_details, dict) and not details:
                        details = show_details
                models.append(
                    ModelInfo(
                        name=name,
                        digest=digest_s,
                        size=(row.get("size") if isinstance(row.get("size"), int) else None),
                        family=(details.get("family") if isinstance(details, dict) else None),
                        parameter_size=(
                            details.get("parameter_size") if isinstance(details, dict) else None
                        ),
                        capabilities=caps,
                        capability_known=capability_known,
                    )
                )
            return models, None
        except ProviderError as exc:
            return [], str(exc)
        except Exception as exc:  # noqa: BLE001 — user-safe discovery
            return [], str(exc)

    def _show(self, model: str) -> dict[str, Any] | None:
        try:
            payload = self._http_post(
                "/api/show", {"model": model}, timeout=min(30.0, self.request_timeout)
            )
            return payload if isinstance(payload, dict) else None
        except ProviderError:
            return None

    def _http_get(self, path: str, *, timeout: float) -> Any:
        return self._request("GET", path, None, timeout=timeout)

    def _http_post(self, path: str, body: dict[str, Any], *, timeout: float) -> Any:
        return self._request("POST", path, body, timeout=timeout)

    def _request(
        self, method: str, path: str, body: dict[str, Any] | None, *, timeout: float
    ) -> Any:
        url = f"{self.base_url}{path}"
        data = None if body is None else json.dumps(body).encode("utf-8")
        headers = {"Content-Type": "application/json"} if data is not None else {}
        req = urllib.request.Request(url, data=data, headers=headers, method=method)
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                raw = resp.read()
        except urllib.error.HTTPError as exc:
            err_body = ""
            try:
                err_body = exc.read().decode("utf-8", errors="replace")
            except Exception:  # noqa: BLE001
                pass
            message = err_body or str(exc)
            code = "http_error"
            retriable = exc.code >= 500
            if exc.code == 404:
                lower = message.lower()
                if "model" in lower or "not found" in lower:
                    code = "model_missing"
                    retriable = False
                else:
                    code = "http_404"
                    retriable = False
            elif 400 <= exc.code < 500:
                retriable = False
                if exc.code == 405:
                    code = "method_not_allowed"
            elif is_fatal_model_load_error(message):
                # Unrecoverable mid-job (e.g. unknown architecture 'mllama').
                # Do not retry every page — JobCoordinator circuits on this code.
                code = "model_load"
                retriable = False
                message = friendly_model_load_message(message)
            raise ProviderError(message, retriable=retriable, code=code) from exc
        except urllib.error.URLError as exc:
            reason = exc.reason
            if isinstance(reason, TimeoutError):
                raise ProviderError(
                    "Ollama request timed out",
                    retriable=False,
                    code="timeout",
                ) from exc
            raise ProviderError(
                f"Cannot reach Ollama at {self.base_url}: {exc.reason}",
                retriable=True,
                code="connection",
            ) from exc
        except TimeoutError as exc:
            raise ProviderError(
                "Ollama request timed out",
                retriable=False,
                code="timeout",
            ) from exc
        try:
            return json.loads(raw.decode("utf-8"))
        except json.JSONDecodeError as exc:
            raise ProviderError(
                "Ollama returned non-JSON response",
                code="bad_response",
            ) from exc
