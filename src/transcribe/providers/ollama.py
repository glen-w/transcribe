"""Ollama HTTP client for vision OCR."""

from __future__ import annotations

import base64
import ipaddress
import json
import socket
import time
import urllib.error
import urllib.request
from typing import Any
from urllib.parse import urlparse

from transcribe.errors import ProviderError
from transcribe.providers.base import DiscoveryResult, ModelInfo, ProviderResult

_DISCOVERY_TTL_S = 45.0
_MAX_RETRIES = 3


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


def _allowlisted_metadata(payload: dict[str, Any], *, retry_count: int) -> dict[str, Any]:
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
    return meta


class OllamaVisionProvider:
    provider_id = "ollama"

    def __init__(
        self,
        base_url: str = "http://localhost:11434",
        *,
        request_timeout: float = 300.0,
        discovery_ttl: float = _DISCOVERY_TTL_S,
    ) -> None:
        self.base_url = normalize_base_url(base_url)
        self.request_timeout = request_timeout
        self.discovery_ttl = discovery_ttl
        self._cache_at: float | None = None
        self._cache_models: list[ModelInfo] | None = None
        self._cache_error: str | None = None

    def healthcheck(self) -> None:
        self._http_get("/api/tags", timeout=min(10.0, self.request_timeout))

    def list_models(self, *, refresh: bool = False) -> DiscoveryResult:
        models, error = self._discover(refresh=refresh)
        return DiscoveryResult(models=models, error=error)

    def list_vision_models(self, *, refresh: bool = False) -> DiscoveryResult:
        result = self.list_models(refresh=refresh)
        vision = [
            m
            for m in result.models
            if m.capability_known and "vision" in m.capabilities
        ]
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
        body = {
            "model": model,
            "prompt": prompt,
            "stream": False,
            "images": [image_b64],
            "options": options,
        }
        digest, verified = self.resolve_model_identity(model)
        last_error: ProviderError | None = None
        for attempt in range(_MAX_RETRIES):
            try:
                payload = self._http_post(
                    "/api/generate", body, timeout=self.request_timeout
                )
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
                return ProviderResult(
                    text=text,
                    model=model,
                    model_digest=digest,
                    model_identity_verified=verified,
                    provider_metadata=_allowlisted_metadata(payload, retry_count=attempt),
                )
            except ProviderError as exc:
                last_error = exc
                if not exc.retriable or attempt + 1 >= _MAX_RETRIES:
                    raise
                time.sleep(0.5 * (2**attempt))
        assert last_error is not None
        raise last_error

    def _discover(self, *, refresh: bool) -> tuple[list[ModelInfo], str | None]:
        now = time.monotonic()
        if (
            not refresh
            and self._cache_models is not None
            and self._cache_at is not None
            and now - self._cache_at < self.discovery_ttl
        ):
            return self._cache_models, self._cache_error
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
                        size=row.get("size") if isinstance(row.get("size"), int) else None,
                        family=details.get("family") if isinstance(details, dict) else None,
                        parameter_size=(
                            details.get("parameter_size")
                            if isinstance(details, dict)
                            else None
                        ),
                        capabilities=caps,
                        capability_known=capability_known,
                    )
                )
            self._cache_models = models
            self._cache_error = None
            self._cache_at = now
            return models, None
        except ProviderError as exc:
            self._cache_models = []
            self._cache_error = str(exc)
            self._cache_at = now
            return [], str(exc)
        except Exception as exc:  # noqa: BLE001 — user-safe discovery
            self._cache_models = []
            self._cache_error = str(exc)
            self._cache_at = now
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
            raise ProviderError(message, retriable=retriable, code=code) from exc
        except urllib.error.URLError as exc:
            raise ProviderError(
                f"Cannot reach Ollama at {self.base_url}: {exc.reason}",
                retriable=True,
                code="connection",
            ) from exc
        except TimeoutError as exc:
            raise ProviderError(
                "Ollama request timed out",
                retriable=True,
                code="timeout",
            ) from exc
        try:
            return json.loads(raw.decode("utf-8"))
        except json.JSONDecodeError as exc:
            raise ProviderError(
                "Ollama returned non-JSON response",
                code="bad_response",
            ) from exc
