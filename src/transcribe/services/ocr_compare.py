"""Multi-candidate OCR rank and composite merge (text model)."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any

from transcribe.analysis.llm_runtime import OllamaTextClient, TextLLMClient
from transcribe.domain.fingerprint import sha256_text
from transcribe.domain.models import (
    ComparisonEntry,
    ComparisonRecord,
    OCRAttempt,
)
from transcribe.prompts import PromptTemplate
from transcribe.services.cleanup_policy import (
    MODE_BUDGETS,
    narrow_unwrap_fence,
    tokenize,
)

RANK_PROMPT = PromptTemplate(
    prompt_id="ocr_rank",
    version="1",
    body=(
        "You rank competing OCR transcriptions of the same handwritten notebook page.\n"
        "Candidates are labeled by attempt_id. Prefer completeness, faithfulness, "
        "and fewer OCR gibberish artefacts. Do not invent content.\n"
        "Return ONLY a JSON object: "
        '{{"order":["attempt_id",...],"rationales":{{"attempt_id":"short reason"}}}} '
        "listing every attempt_id exactly once, best first.\n\n"
        "Candidates:\n{candidates}"
    ),
)

COMPOSITE_PROMPT = PromptTemplate(
    prompt_id="ocr_composite",
    version="1",
    body=(
        "You merge competing OCR transcriptions of the same handwritten notebook page.\n"
        "Produce one composite transcription that takes the most correct spans from each "
        "candidate. Do not invent topics absent from all candidates. "
        "Return only the merged page text with no commentary and no markdown fences.\n\n"
        "Candidates:\n{candidates}"
    ),
)

COMPARE_REGISTRY: dict[str, PromptTemplate] = {
    "rank": RANK_PROMPT,
    "composite": COMPOSITE_PROMPT,
}


@dataclass(frozen=True)
class RankResult:
    comparison: ComparisonRecord | None
    note: str | None = None


@dataclass(frozen=True)
class CompositeResult:
    text: str | None
    note: str | None = None
    prompt_id: str = ""
    prompt_version: str = ""
    prompt_sha256: str = ""
    prompt_text: str = ""
    model_digest: str | None = None


def _format_candidates(attempts: list[OCRAttempt]) -> str:
    blocks: list[str] = []
    for attempt in attempts:
        model = ""
        if attempt.provenance is not None:
            model = attempt.provenance.model_name
        text = attempt.raw_text or ""
        blocks.append(f"--- attempt_id={attempt.attempt_id} model={model} ---\n{text}\n")
    return "\n".join(blocks)


def render_rank_prompt(attempts: list[OCRAttempt]) -> tuple[str, str, str]:
    body = RANK_PROMPT.body.format(candidates=_format_candidates(attempts))
    return RANK_PROMPT.prompt_id, RANK_PROMPT.version, body


def render_composite_prompt(attempts: list[OCRAttempt]) -> tuple[str, str, str]:
    body = COMPOSITE_PROMPT.body.format(candidates=_format_candidates(attempts))
    return COMPOSITE_PROMPT.prompt_id, COMPOSITE_PROMPT.version, body


def _parse_rank_json(raw: str, allowed: set[str]) -> list[str] | None:
    text = narrow_unwrap_fence(raw).strip()
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        # Try to find a JSON object substring
        match = re.search(r"\{.*\}", text, flags=re.DOTALL)
        if not match:
            return None
        try:
            payload = json.loads(match.group(0))
        except json.JSONDecodeError:
            return None
    if not isinstance(payload, dict):
        return None
    order = payload.get("order")
    if not isinstance(order, list):
        return None
    ids = [str(x) for x in order]
    if len(ids) != len(allowed) or set(ids) != allowed:
        return None
    return ids


def validate_composite_against_union(
    *,
    candidate: str,
    sources: list[str],
) -> str | None:
    """Return a machine note on reject, else None. Groundedness vs union of sources."""
    cleaned = narrow_unwrap_fence(candidate).strip()
    if not cleaned:
        return "empty_output"
    union_tokens: set[str] = set()
    for src in sources:
        union_tokens |= tokenize(src)
    cand_tokens = tokenize(cleaned)
    if not cand_tokens:
        return "empty_output"
    # Precision: candidate tokens should mostly appear in some source
    grounded = len(cand_tokens & union_tokens) / max(1, len(cand_tokens))
    budget = MODE_BUDGETS["rewrite"]
    if grounded < budget.min_groundedness:
        return "min_retained_failed"
    # Length vs longest source
    longest = max((len(s) for s in sources), default=1)
    if abs(len(cleaned) - longest) > (budget.max_abs_delta or 2000):
        return "abs_ceiling_exceeded"
    return None


def run_rank(
    *,
    attempts: list[OCRAttempt],
    pass_id: str,
    model_name: str,
    model_digest: str | None,
    created_at: str,
    base_url: str,
    client: TextLLMClient | None = None,
) -> RankResult:
    vision = [
        a
        for a in attempts
        if a.status == "succeeded"
        and (a.attempt_kind or "vision") == "vision"
        and (a.raw_text or "").strip()
    ]
    if len(vision) < 2:
        return RankResult(comparison=None, note="insufficient_candidates")
    allowed = {a.attempt_id for a in vision}
    prompt_id, prompt_version, prompt_text = render_rank_prompt(vision)
    cli = client or OllamaTextClient(base_url=base_url)
    try:
        raw = cli.generate(
            model=model_name,
            prompt=prompt_text,
            options={"temperature": 0.0, "num_predict": 1024},
        )
    except Exception:  # noqa: BLE001
        return RankResult(comparison=None, note="provider_failed")
    order = _parse_rank_json(raw if isinstance(raw, str) else str(raw), allowed)
    if order is None:
        # Some clients return structured objects
        if isinstance(raw, dict):
            order = _parse_rank_json(json.dumps(raw), allowed)
    if order is None:
        return RankResult(comparison=None, note="malformed_rank")
    entries = [ComparisonEntry(attempt_id=aid) for aid in order]
    return RankResult(
        comparison=ComparisonRecord(
            pass_id=pass_id,
            ranked_attempt_ids=order,
            created_at=created_at,
            entries=entries,
            ranker_model_name=model_name,
            ranker_model_digest=model_digest,
            ranker_prompt_id=prompt_id,
            ranker_prompt_version=prompt_version,
            ranker_prompt_sha256=sha256_text(prompt_text),
        )
    )


def run_composite(
    *,
    attempts: list[OCRAttempt],
    model_name: str,
    base_url: str,
    client: TextLLMClient | None = None,
) -> CompositeResult:
    vision = [
        a
        for a in attempts
        if a.status == "succeeded"
        and (a.attempt_kind or "vision") == "vision"
        and (a.raw_text or "").strip()
    ]
    if len(vision) < 2:
        return CompositeResult(text=None, note="insufficient_candidates")
    prompt_id, prompt_version, prompt_text = render_composite_prompt(vision)
    prompt_sha = sha256_text(prompt_text)
    digest: str | None = None
    cli = client or OllamaTextClient(base_url=base_url)
    try:
        digest = cli.model_digest(model_name)
    except Exception:  # noqa: BLE001 — digest is best-effort provenance
        digest = None
    try:
        raw = cli.generate(
            model=model_name,
            prompt=prompt_text,
            options={"temperature": 0.0, "num_predict": 4096},
        )
    except Exception:  # noqa: BLE001
        return CompositeResult(
            text=None,
            note="provider_failed",
            prompt_id=prompt_id,
            prompt_version=prompt_version,
            prompt_sha256=prompt_sha,
            prompt_text=prompt_text,
            model_digest=digest,
        )
    text = narrow_unwrap_fence(raw if isinstance(raw, str) else str(raw)).strip()
    note = validate_composite_against_union(
        candidate=text,
        sources=[a.raw_text or "" for a in vision],
    )
    if note is not None:
        return CompositeResult(
            text=None,
            note=note,
            prompt_id=prompt_id,
            prompt_version=prompt_version,
            prompt_sha256=prompt_sha,
            prompt_text=prompt_text,
            model_digest=digest,
        )
    return CompositeResult(
        text=text,
        note=None,
        prompt_id=prompt_id,
        prompt_version=prompt_version,
        prompt_sha256=prompt_sha,
        prompt_text=prompt_text,
        model_digest=digest,
    )


def compare_templates_as_definitions() -> list[Any]:
    from transcribe.prompt_engine.definition import (
        FREE_TEXT_SCHEMA,
        InputMode,
        ModelCapability,
        ModelRequirements,
        PromptDefinition,
        PromptFamily,
    )

    out: list[PromptDefinition] = []
    for key, tmpl in COMPARE_REGISTRY.items():
        out.append(
            PromptDefinition(
                prompt_id=tmpl.prompt_id,
                version=tmpl.version,
                title=f"OCR {key.title()}",
                description=f"Multipass OCR {key} prompt.",
                system_prompt="",
                user_template=tmpl.body.replace("{candidates}", "{{candidates}}"),
                input_mode=InputMode.TEXT,
                response_schema_id=FREE_TEXT_SCHEMA,
                model_requirements=ModelRequirements(capability=ModelCapability.TEXT),
                prompt_family=PromptFamily.CLEANUP,
                is_builtin=True,
            )
        )
    return out
