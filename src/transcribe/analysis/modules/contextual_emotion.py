"""Contextual emotion — neighbor window over unit order (not a parent module)."""

from __future__ import annotations

from typing import Any

from transcribe.analysis.document import AnalysisDocument
from transcribe.analysis.modules.emotion import (
    TX_COMMIT,
    emotion_config,
    emotion_lexicon_or_model,
    score_emotion,
)

MODULE_ID = "contextual_emotion"
MODULE_VERSION = "1d.0"
PAYLOAD_SCHEMA = "contextual_emotion_payload_v1"
ALGORITHM_VERSION = "emotion_neighbor_window_v1"
WINDOW = 1


def contextual_emotion_config() -> dict[str, Any]:
    base = emotion_config()
    base.update(
        {
            "payload_schema": PAYLOAD_SCHEMA,
            "algorithm_version": ALGORITHM_VERSION,
            "neighbor_window": WINDOW,
        }
    )
    return base


def provenance_files() -> list[dict[str, str]]:
    return []


class ContextualEmotionModule:
    module_id = MODULE_ID
    module_version = MODULE_VERSION
    ported_from_commit = TX_COMMIT
    semantic_class = "adaptation"
    semantic_delta = (
        "neighbor window by unit order (±1); no speaker context; "
        "lexicon path shared with emotion"
    )

    def cache_config(self) -> dict[str, Any]:
        return contextual_emotion_config()

    def run(
        self,
        document: AnalysisDocument,
        *,
        parents: dict | None = None,
        llm_ctx: Any = None,
        question_text: str | None = None,
    ) -> dict[str, Any]:
        _ = parents, llm_ctx, question_text
        if not document.units or not document.text.strip():
            return {
                "outcome": "insufficient_data",
                "payload": {},
                "warnings": [
                    {
                        "code": "empty_document",
                        "message": "No units / empty document text",
                    }
                ],
            }

        units = sorted(document.units, key=lambda u: u.order)
        raw = [score_emotion(u.text) for u in units]
        labels = list(raw[0]["scores"].keys()) if raw else []
        units_out: list[dict[str, Any]] = []
        for i, unit in enumerate(units):
            lo = max(0, i - WINDOW)
            hi = min(len(units), i + WINDOW + 1)
            neigh = raw[lo:hi]
            avg_scores = {lab: 0.0 for lab in labels}
            avg_intensity = 0.0
            for row in neigh:
                avg_intensity += row["intensity"]
                for lab, val in row["scores"].items():
                    avg_scores[lab] += val
            n = max(1, len(neigh))
            avg_scores = {lab: round(v / n, 6) for lab, v in avg_scores.items()}
            avg_intensity = round(avg_intensity / n, 6)
            total = sum(avg_scores.values())
            dist = (
                {lab: round(v / total, 6) for lab, v in avg_scores.items()}
                if total > 0
                else {lab: 0.0 for lab in labels}
            )
            top = max(dist, key=dist.get) if labels and total > 0 else None
            units_out.append(
                {
                    "unit_id": unit.unit_id,
                    "order": unit.order,
                    "date": unit.date,
                    "scores": avg_scores,
                    "distribution": dist,
                    "top_label": top,
                    "intensity": avg_intensity,
                    "window": WINDOW,
                    "neighbor_count": len(neigh),
                }
            )
        return {
            "outcome": "success",
            "payload": {
                "schema": PAYLOAD_SCHEMA,
                "algorithm_version": ALGORITHM_VERSION,
                "neighbor_window": WINDOW,
                "lexicon_or_model": emotion_lexicon_or_model(),
                "units": units_out,
                "n_units": len(units_out),
            },
        }
