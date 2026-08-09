"""Affect tension — hard parents emotion + sentiment."""

from __future__ import annotations

from typing import Any

from transcribe.analysis.document import AnalysisDocument

MODULE_ID = "affect_tension"
MODULE_VERSION = "1d.0"
PAYLOAD_SCHEMA = "affect_tension_payload_v1"
ALGORITHM_VERSION = "affect_tension_join_v1"
TX_COMMIT = "50a0ede8e7acd03bbd9125a5a5237049f3291304"


def affect_tension_config() -> dict[str, Any]:
    return {"payload_schema": PAYLOAD_SCHEMA, "algorithm_version": ALGORITHM_VERSION}


def provenance_files() -> list[dict[str, str]]:
    return []


class AffectTensionModule:
    module_id = MODULE_ID
    module_version = MODULE_VERSION
    ported_from_commit = TX_COMMIT
    semantic_class = "adaptation"
    semantic_delta = (
        "Join emotion intensity with sentiment polarity into tension vs order; "
        "no speakers"
    )

    def cache_config(self) -> dict[str, Any]:
        return affect_tension_config()

    def run(
        self,
        document: AnalysisDocument,
        *,
        parents: dict | None = None,
        llm_ctx: Any = None,
        question_text: str | None = None,
    ) -> dict[str, Any]:
        _ = llm_ctx, question_text
        parents = parents or {}
        emotion = parents.get("emotion") or {}
        sentiment = parents.get("sentiment") or {}
        if not document.units:
            return {"outcome": "insufficient_data", "payload": {}}

        by_emo = {
            row.get("unit_id"): row
            for row in (emotion.get("units") or [])
            if isinstance(row, dict)
        }
        by_sent = {
            row.get("unit_id"): row
            for row in (sentiment.get("units") or [])
            if isinstance(row, dict)
        }
        series: list[dict[str, Any]] = []
        for unit in sorted(document.units, key=lambda u: u.order):
            emo = by_emo.get(unit.unit_id) or {}
            sent = by_sent.get(unit.unit_id) or {}
            intensity = float(emo.get("intensity") or 0.0)
            compound = float(sent.get("compound") or 0.0)
            # High intensity with conflicting/near-zero polarity → tension.
            polarity_conflict = abs(compound)
            tension = round(intensity * (1.0 - min(1.0, polarity_conflict)), 6)
            # Also flag opposite signals: negative sentiment + joy-heavy etc.
            top = emo.get("top_label")
            sent_label = sent.get("label")
            conflicting = bool(
                (top == "joy" and sent_label == "negative")
                or (top in {"sadness", "anger", "fear"} and sent_label == "positive")
            )
            if conflicting:
                tension = round(min(1.0, tension + 0.35), 6)
            series.append(
                {
                    "unit_id": unit.unit_id,
                    "order": unit.order,
                    "date": unit.date,
                    "tension": tension,
                    "emotion_intensity": intensity,
                    "sentiment_compound": compound,
                    "conflicting": conflicting,
                }
            )
        mean_t = sum(r["tension"] for r in series) / len(series) if series else 0.0
        return {
            "outcome": "success",
            "payload": {
                "schema": PAYLOAD_SCHEMA,
                "algorithm_version": ALGORITHM_VERSION,
                "units": series,
                "global_stats": {
                    "count": len(series),
                    "tension_mean": round(mean_t, 6),
                    "n_conflicting": sum(1 for r in series if r["conflicting"]),
                },
            },
        }
