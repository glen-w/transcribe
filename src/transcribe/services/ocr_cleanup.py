"""Post-OCR text cleanup (optional second-pass text model)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from transcribe.analysis.llm_runtime import OllamaTextClient, TextLLMClient
from transcribe.domain.fingerprint import sha256_text
from transcribe.domain.models import CLEANUP_MODES, CleanupRecord, OCRSettings
from transcribe.errors import ProviderError, TranscribeError
from transcribe.services.cleanup_policy import (
    CLEANUP_VALIDATOR_POLICY_ID,
    CLEANUP_VALIDATOR_POLICY_VERSION,
    compute_num_predict,
    narrow_unwrap_fence,
    validate_cleanup_candidate,
)
from transcribe.services.cleanup_prompts import render_cleanup_prompt


@dataclass(frozen=True)
class CleanupPlanConfig:
    enabled: bool
    mode: str
    model_name: str
    model_digest: str
    prompt_id: str
    prompt_version: str
    # Template body without page text — for plan freeze / fingerprint.
    prompt_template_sha256: str
    validator_policy_id: str = CLEANUP_VALIDATOR_POLICY_ID
    validator_policy_version: str = CLEANUP_VALIDATOR_POLICY_VERSION

    def fingerprint_dict(self) -> dict[str, Any] | None:
        if not self.enabled:
            return None
        return {
            "enabled": True,
            "mode": self.mode,
            "model_name": self.model_name,
            "model_digest": self.model_digest,
            "model_identity_verified": True,
            "prompt_id": self.prompt_id,
            "prompt_version": self.prompt_version,
            "prompt_sha256": self.prompt_template_sha256,
            "cleanup_validator_policy_id": self.validator_policy_id,
            "cleanup_validator_policy_version": self.validator_policy_version,
        }


def _disabled_record() -> CleanupRecord:
    return CleanupRecord(
        execution_status="disabled",
        acceptance_status="not_applicable",
        cleanup_validator_policy_id=CLEANUP_VALIDATOR_POLICY_ID,
        cleanup_validator_policy_version=CLEANUP_VALIDATOR_POLICY_VERSION,
    )


def resolve_cleanup_plan_config(
    settings: OCRSettings,
    *,
    client: TextLLMClient | None = None,
) -> CleanupPlanConfig:
    """Fail-fast plan resolution. Raises when cleanup enabled but misconfigured."""
    if not settings.cleanup_enabled:
        return CleanupPlanConfig(
            enabled=False,
            mode="strip_leak",
            model_name="",
            model_digest="",
            prompt_id="",
            prompt_version="",
            prompt_template_sha256="",
        )

    mode = (settings.cleanup_mode or "").strip()
    if mode not in CLEANUP_MODES:
        raise TranscribeError(
            f"Invalid cleanup mode {mode!r}; "
            f"expected one of {sorted(CLEANUP_MODES)}"
        )

    model = (settings.cleanup_model_name or "").strip() or (
        settings.text_model_name or ""
    ).strip()
    if not model:
        raise TranscribeError(
            "Cleanup is enabled but no cleanup model or text analysis model is set"
        )

    cli = client or OllamaTextClient(base_url=settings.base_url)
    if not cli.healthcheck():
        raise ProviderError(
            "Cannot reach Ollama for cleanup model resolution",
            code="connection",
            retriable=True,
        )
    if cli.is_unsuitable_model(model):
        raise TranscribeError(
            f"Cleanup model {model!r} is unsuitable (vision/embedding)"
        )
    resolved = cli.resolve_configured_model(model)
    if not resolved:
        raise ProviderError(
            f"Cleanup model {model!r} is not available on Ollama",
            code="model_missing",
        )
    digest = cli.model_digest(resolved)
    if not digest:
        raise TranscribeError(
            f"Cleanup model {resolved!r} has no verified digest; "
            "cleanup requires verified model identity"
        )

    prompt_id, prompt_version, prompt_text = render_cleanup_prompt(
        mode=mode, ocr_text="{ocr_text}"
    )
    return CleanupPlanConfig(
        enabled=True,
        mode=mode,
        model_name=resolved,
        model_digest=digest,
        prompt_id=prompt_id,
        prompt_version=prompt_version,
        prompt_template_sha256=sha256_text(prompt_text),
    )


def _record(
    plan: CleanupPlanConfig,
    *,
    execution_status: str,
    acceptance_status: str,
    note: str | None = None,
    pre_cleanup_text: str | None = None,
    original_length: int | None = None,
    candidate_length: int | None = None,
    length_ratio: float | None = None,
    prompt_id: str | None = None,
    prompt_version: str | None = None,
    prompt_sha256: str | None = None,
) -> CleanupRecord:
    return CleanupRecord(
        execution_status=execution_status,
        acceptance_status=acceptance_status,
        mode=plan.mode if plan.enabled else None,
        model_name=plan.model_name or None,
        model_digest=plan.model_digest or None,
        prompt_id=prompt_id if prompt_id is not None else (plan.prompt_id or None),
        prompt_version=(
            prompt_version
            if prompt_version is not None
            else (plan.prompt_version or None)
        ),
        prompt_sha256=(
            prompt_sha256
            if prompt_sha256 is not None
            else (plan.prompt_template_sha256 or None)
        ),
        note=note,
        pre_cleanup_text=pre_cleanup_text,
        original_length=original_length,
        candidate_length=candidate_length,
        length_ratio=length_ratio,
        cleanup_validator_policy_id=plan.validator_policy_id,
        cleanup_validator_policy_version=plan.validator_policy_version,
    )


def run_ocr_cleanup(
    *,
    vision_text: str,
    plan: CleanupPlanConfig,
    base_url: str,
    client: TextLLMClient | None = None,
) -> tuple[str, CleanupRecord]:
    """Return (final_raw_text, cleanup_record). Never raises for soft failures."""
    if not plan.enabled:
        return vision_text, _disabled_record()

    if not (vision_text or "").strip():
        return vision_text, _record(
            plan,
            execution_status="skipped_empty_source",
            acceptance_status="not_applicable",
            note="empty_source",
            original_length=len(vision_text or ""),
            candidate_length=0,
        )

    cli = client or OllamaTextClient(base_url=base_url)

    try:
        if cli.is_unsuitable_model(plan.model_name):
            return vision_text, _record(
                plan,
                execution_status="provider_failed",
                acceptance_status="not_applicable",
                note="unsuitable_model",
                original_length=len(vision_text),
                candidate_length=0,
            )
        resolved = cli.resolve_configured_model(plan.model_name)
        if not resolved or resolved != plan.model_name:
            return vision_text, _record(
                plan,
                execution_status="provider_failed",
                acceptance_status="not_applicable",
                note="unavailable_model",
                original_length=len(vision_text),
                candidate_length=0,
            )
        digest = cli.model_digest(plan.model_name)
        if not digest:
            return vision_text, _record(
                plan,
                execution_status="provider_failed",
                acceptance_status="not_applicable",
                note="model_identity_mismatch",
                original_length=len(vision_text),
                candidate_length=0,
            )
        if digest != plan.model_digest:
            return vision_text, _record(
                plan,
                execution_status="provider_failed",
                acceptance_status="not_applicable",
                note="digest_changed",
                original_length=len(vision_text),
                candidate_length=0,
            )
    except ProviderError as exc:
        note = "timeout" if exc.code == "timeout" else "provider_error"
        return vision_text, _record(
            plan,
            execution_status="provider_failed",
            acceptance_status="not_applicable",
            note=note,
            original_length=len(vision_text),
            candidate_length=0,
        )

    prompt_id, prompt_version, prompt_text = render_cleanup_prompt(
        mode=plan.mode, ocr_text=vision_text
    )
    prompt_sha = sha256_text(prompt_text)
    num_predict = compute_num_predict(len(vision_text))
    options = {"temperature": 0.0, "num_predict": num_predict}

    try:
        generate_meta = getattr(cli, "generate_with_meta", None)
        if callable(generate_meta):
            raw, meta = generate_meta(
                model=plan.model_name,
                prompt=prompt_text,
                options=options,
            )
        else:
            raw = cli.generate(
                model=plan.model_name,
                prompt=prompt_text,
                options=options,
            )
            meta = {}
    except ProviderError as exc:
        note = "timeout" if exc.code == "timeout" else "provider_error"
        if exc.code == "model_missing":
            note = "unavailable_model"
        return vision_text, _record(
            plan,
            execution_status="provider_failed",
            acceptance_status="not_applicable",
            note=note,
            original_length=len(vision_text),
            candidate_length=0,
            prompt_id=prompt_id,
            prompt_version=prompt_version,
            prompt_sha256=prompt_sha,
        )
    except Exception:  # noqa: BLE001 — soft-fail cleanup only
        return vision_text, _record(
            plan,
            execution_status="provider_failed",
            acceptance_status="not_applicable",
            note="provider_error",
            original_length=len(vision_text),
            candidate_length=0,
            prompt_id=prompt_id,
            prompt_version=prompt_version,
            prompt_sha256=prompt_sha,
        )

    candidate = narrow_unwrap_fence(raw if isinstance(raw, str) else "")
    truncated = False
    eval_count = meta.get("eval_count") if isinstance(meta, dict) else None
    if isinstance(eval_count, (int, float)) and int(eval_count) >= num_predict:
        truncated = True

    verdict = validate_cleanup_candidate(
        source=vision_text,
        candidate=candidate,
        mode=plan.mode,
        truncated=truncated,
    )

    common = dict(
        prompt_id=prompt_id,
        prompt_version=prompt_version,
        prompt_sha256=prompt_sha,
        original_length=verdict.original_length,
        candidate_length=verdict.candidate_length,
        length_ratio=verdict.length_ratio,
    )

    if verdict.note == "identical_nfkc":
        return vision_text, _record(
            plan,
            execution_status="provider_ok",
            acceptance_status="unchanged",
            note="identical_nfkc",
            **common,
        )

    if verdict.note is not None:
        return vision_text, _record(
            plan,
            execution_status="provider_ok",
            acceptance_status="validator_rejected",
            note=verdict.note,
            **common,
        )

    return candidate, _record(
        plan,
        execution_status="provider_ok",
        acceptance_status="applied",
        pre_cleanup_text=vision_text,
        **common,
    )
