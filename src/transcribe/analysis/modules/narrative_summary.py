"""narrative_summary — hard parent summary; optional LLM polish."""

from __future__ import annotations

from typing import Any

from transcribe.analysis.document import AnalysisDocument
from transcribe.analysis.modules._llm_common import (
    GENERATION_SETTINGS,
    GROUND_HIGHLIGHTS_SUMMARY_V1,
    PROMPT_VERSION,
    llm_preflight,
    parse_json_object,
)

MODULE_ID = "narrative_summary"
MODULE_VERSION = "1e.2.0"
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


class NarrativeSummaryModule:
    module_id = MODULE_ID
    module_version = MODULE_VERSION
    ported_from_commit = TX_COMMIT
    semantic_class = "adaptation"
    semantic_delta = "Narrative rollup from deterministic summary; LLM optional with offline fallback"

    def cache_config(self) -> dict[str, Any]:
        return narrative_summary_config()

    def run(self, document: AnalysisDocument, *, parents: dict | None = None) -> dict[str, Any]:
        parents = parents or {}
        summary = parents.get("summary") or {}
        overview = str(summary.get("overview") or "").strip()
        bullets = [str(b) for b in (summary.get("bullets") or []) if str(b).strip()]
        if not overview and not bullets:
            return {"outcome": "insufficient_data", "payload": {}}

        fallback = overview or " ".join(bullets[:5])
        pre = llm_preflight()
        if not pre["ok"]:
            # Deterministic narrative path when Ollama missing.
            return {
                "outcome": "success",
                "payload": {
                    "schema": PAYLOAD_SCHEMA,
                    "narrative": fallback,
                    "honesty_label": "deterministic_from_summary",
                    "n_units": len(document.units),
                },
                "partial": True,
                "warnings": [
                    {
                        "code": "unavailable_model",
                        "message": "LLM offline; used deterministic summary narrative",
                    }
                ],
                "capability_reason": None,
            }

        client = pre["client"]
        model = pre["model"]
        prompt = (
            f"Summary overview:\n{overview}\n\nBullets:\n"
            + "\n".join(f"- {b}" for b in bullets[:8])
            + "\n\nWrite narrative JSON."
        )
        try:
            raw = client.generate(
                model=model,
                prompt=prompt,
                system=SYSTEM,
                options=GENERATION_SETTINGS,
            )
        except Exception:
            return {
                "outcome": "success",
                "payload": {
                    "schema": PAYLOAD_SCHEMA,
                    "narrative": fallback,
                    "honesty_label": "deterministic_from_summary",
                },
                "partial": True,
                "warnings": [
                    {
                        "code": "llm_fallback",
                        "message": "generate failed; deterministic narrative used",
                    }
                ],
            }
        parsed = parse_json_object(raw)
        narrative = str((parsed or {}).get("narrative") or "").strip() or fallback
        return {
            "outcome": "success",
            "payload": {
                "schema": PAYLOAD_SCHEMA,
                "narrative": narrative,
                "honesty_label": "llm_generated"
                if parsed and parsed.get("narrative")
                else "deterministic_from_summary",
                "model": model,
            },
        }
