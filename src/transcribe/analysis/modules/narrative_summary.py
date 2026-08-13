"""narrative_summary — hard parent summary; LLM narrative (no offline success fallback)."""

from __future__ import annotations

from hashlib import sha256
from typing import Any

from transcribe.analysis.document import AnalysisDocument
from transcribe.analysis.llm_runtime import TextLLMContext
from transcribe.analysis.modules._llm_common import (
    generation_settings,
    GROUND_HIGHLIGHTS_SUMMARY_V1,
    PROMPT_VERSION,
    parse_json_object,
    require_llm_ctx,
)
from transcribe.domain.fingerprint import canonical_json_bytes

MODULE_ID = "narrative_summary"
MODULE_VERSION = "1e.2.1"
PAYLOAD_SCHEMA = "narrative_summary_payload_v1"
TX_COMMIT = "50a0ede8e7acd03bbd9125a5a5237049f3291304"
SYSTEM = (
    "Rewrite the notebook summary as a short narrative paragraph. "
    'JSON only: {"narrative":"..."}.'
)


def narrative_summary_config() -> dict[str, Any]:
    return {
        "payload_schema": PAYLOAD_SCHEMA,
        "prompt_version": PROMPT_VERSION,
        "grounding_strategy_id": GROUND_HIGHLIGHTS_SUMMARY_V1,
    }


def provenance_files() -> list[dict[str, str]]:
    return []


def summary_prompt_fingerprint(overview: str, bullets: list[str]) -> str:
    return sha256(canonical_json_bytes({"overview": overview, "bullets": bullets[:8]})).hexdigest()


class NarrativeSummaryModule:
    module_id = MODULE_ID
    module_version = MODULE_VERSION
    ported_from_commit = TX_COMMIT
    semantic_class = "adaptation"
    semantic_delta = (
        "LLM narrative from deterministic summary; unavailable_model when Ollama missing"
    )

    def cache_config(self) -> dict[str, Any]:
        return narrative_summary_config()

    def run(
        self,
        document: AnalysisDocument,
        *,
        parents: dict | None = None,
        llm_ctx: TextLLMContext | None = None,
        question_text: str | None = None,
    ) -> dict[str, Any]:
        _ = question_text
        parents = parents or {}
        summary = parents.get("summary") or {}
        overview = summary.get("overview")
        if overview is not None and not isinstance(overview, str):
            return {"outcome": "insufficient_data", "payload": {}}
        overview = (overview or "").strip()
        raw_bullets = summary.get("bullets") or []
        if not isinstance(raw_bullets, list):
            return {"outcome": "insufficient_data", "payload": {}}
        bullets = [str(b) for b in raw_bullets if isinstance(b, str) and b.strip()]
        if not overview and not bullets:
            return {"outcome": "insufficient_data", "payload": {}}

        ctx = require_llm_ctx(llm_ctx)
        if not isinstance(ctx, TextLLMContext):
            return ctx

        prompt = (
            f"Summary overview:\n{overview}\n\nBullets:\n"
            + "\n".join(f"- {b}" for b in bullets[:8])
            + "\n\nWrite narrative JSON."
        )
        try:
            raw = ctx.client.generate(
                model=ctx.model_name,
                prompt=prompt,
                system=SYSTEM,
                options=generation_settings(),
            )
        except Exception as exc:  # noqa: BLE001
            return {
                "outcome": "failed",
                "payload": {"error": {"code": "llm_generate", "message": str(exc)}},
            }
        parsed = parse_json_object(raw)
        narrative = parsed.get("narrative") if parsed else None
        if not isinstance(narrative, str) or not narrative.strip():
            return {
                "outcome": "skipped_not_applicable",
                "payload": {"schema": PAYLOAD_SCHEMA, "abstain": True},
                "warnings": [
                    {
                        "code": "abstain_unparseable",
                        "message": "model output abstained / failed schema validation",
                    }
                ],
                "diagnostics": {"raw_bounded": (raw or "")[:2000]},
            }
        return {
            "outcome": "success",
            "payload": {
                "schema": PAYLOAD_SCHEMA,
                "narrative": narrative.strip(),
                "honesty_label": "llm_generated",
                "model": ctx.model_name,
                "n_units": len(document.units),
            },
        }
