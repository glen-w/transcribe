"""Rank and merged-draft (composite) from existing vision OCR attempts.

Used by same-session multipass after vision phases, and by compare-only runs
over on-disk attempts from different jobs.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from transcribe import __version__
from transcribe.domain.models import (
    AttemptProvenance,
    DEFAULT_PREFER_MODE,
    OCRAttempt,
    PREFER_MODES,
)
from transcribe.ports import Clock, IdGenerator, to_iso
from transcribe.services.ocr_compare import run_composite, run_rank
from transcribe.services.ocr_composite_state import merge_input_vision_attempts
from transcribe.services.ocr_preference_stats import append_preference_event
from transcribe.services.project import ProjectService


@dataclass(frozen=True)
class RankCompositeOutcome:
    ranked: bool = False
    composited: bool = False


def comparable_attempts(result) -> list[OCRAttempt]:
    """Latest succeeded-with-text vision attempt per model identity."""
    if result is None:
        return []
    return list(merge_input_vision_attempts(result))


def rank_and_composite_page(
    *,
    projects: ProjectService,
    page_id: str,
    pass_id: str,
    ranker_model_name: str,
    base_url: str,
    ids: IdGenerator,
    clock: Clock,
    auto_activate_composite: bool,
    prefer_mode: str,
    prior_active_id: str | None,
    attempts: list[OCRAttempt],
    text_client: Any | None = None,
) -> RankCompositeOutcome:
    """Persist rank + optional composite for ``attempts`` (≥2 succeeded-with-text)."""
    vision = [
        a
        for a in attempts
        if a.status == "succeeded"
        and (a.attempt_kind or "vision") == "vision"
        and (a.raw_text or "").strip()
    ]
    if len(vision) < 2:
        return RankCompositeOutcome()

    created = to_iso(clock.now())
    ranker_digest = None
    if text_client is not None:
        try:
            ranker_digest = text_client.model_digest(ranker_model_name)
        except Exception:  # noqa: BLE001 — provenance best-effort
            ranker_digest = None
    rank = run_rank(
        attempts=vision,
        pass_id=pass_id,
        model_name=ranker_model_name,
        model_digest=ranker_digest,
        created_at=created,
        base_url=base_url,
        client=text_client,
    )
    ranked = False
    if rank.comparison is not None:
        projects.save_comparison(page_id, rank.comparison)
        ranked = True

    comp = run_composite(
        attempts=vision,
        model_name=ranker_model_name,
        base_url=base_url,
        client=text_client,
    )
    composited = False
    if comp.text:
        attempt_id = ids.new_id()
        source_ids = [a.attempt_id for a in vision]
        composite_attempt = OCRAttempt(
            attempt_id=attempt_id,
            status="succeeded",
            input_fingerprint=f"composite:{pass_id}:{attempt_id}",
            fingerprint_payload={
                "kind": "composite",
                "pass_id": pass_id,
                "source_attempt_ids": source_ids,
            },
            raw_text=comp.text,
            provenance=AttemptProvenance(
                model_name=ranker_model_name,
                model_digest=comp.model_digest or ranker_digest,
                model_identity_verified=bool(comp.model_digest or ranker_digest),
                prompt_id=comp.prompt_id or "ocr_composite",
                prompt_version=comp.prompt_version or "1",
                prompt_sha256=comp.prompt_sha256 or "",
                prompt_text=comp.prompt_text or "",
                input_sha256="",
                preprocess_profile="none",
                preprocess_version=0,
                generation_options={},
                application_version=__version__,
                ollama_host=base_url,
                request_id=attempt_id,
                render_id="",
            ),
            provider_metadata={},
            started_at=created,
            completed_at=created,
            attempt_kind="composite",
            pass_id=pass_id,
            source_attempt_ids=source_ids,
        )
        project = projects.load(reconcile=False)
        page = next((p for p in project.pages if p.page_id == page_id), None)
        if page and composite_attempt.provenance:
            composite_attempt.provenance.render_id = page.active_render_id
        activate = bool(auto_activate_composite)
        resolved_mode = prefer_mode if prefer_mode in PREFER_MODES else DEFAULT_PREFER_MODE
        projects.record_generation(page_id, composite_attempt, activate=activate)
        composited = True
        if activate:
            if resolved_mode == "prefer_is_promote":
                projects.set_preferred_attempt(
                    page_id,
                    attempt_id,
                    mode="prefer_is_promote",
                    record_ledger=True,
                    action_override="auto_composite",
                )
            else:
                append_preference_event(
                    notebook_id=project.id,
                    page_id=page_id,
                    attempt_id=attempt_id,
                    model_name=ranker_model_name,
                    model_digest=comp.model_digest or ranker_digest,
                    attempt_kind="composite",
                    action="auto_composite",
                    pass_id=pass_id,
                    clock=clock,
                )
    else:
        result = projects.load_page_result(page_id)
        if result and not prior_active_id:
            best_id = None
            if rank.comparison and rank.comparison.ranked_attempt_ids:
                best_id = rank.comparison.ranked_attempt_ids[0]
            elif vision:
                best_id = sorted(vision, key=lambda a: a.started_at, reverse=True)[0].attempt_id
            if best_id:
                projects.set_active_attempt(page_id, best_id)

    return RankCompositeOutcome(ranked=ranked, composited=composited)
