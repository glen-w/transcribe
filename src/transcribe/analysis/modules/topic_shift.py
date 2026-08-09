"""Topic shift — consecutive-unit cosine drops along order (not timestamps)."""

from __future__ import annotations

from typing import Any

from transcribe.analysis.document import AnalysisDocument
from transcribe.analysis.modules.semantic_similarity import build_unit_vectors, cosine
from transcribe.config.facade import require_operation_config
from transcribe.config.knobs import module_knob_dict

MODULE_ID = "topic_shift"
MODULE_VERSION = "1c.0"
PAYLOAD_SCHEMA = "topic_shift_payload_v1"
ALGORITHM_VERSION = "order_cosine_drop_v1"
TX_COMMIT = "50a0ede8e7acd03bbd9125a5a5237049f3291304"


def topic_shift_config() -> dict[str, Any]:
    cfg = require_operation_config()
    return {
        "payload_schema": PAYLOAD_SCHEMA,
        "algorithm_version": ALGORITHM_VERSION,
        **module_knob_dict(cfg, MODULE_ID),
    }


def provenance_files() -> list[dict[str, str]]:
    return []


class TopicShiftModule:
    module_id = MODULE_ID
    module_version = MODULE_VERSION
    ported_from_commit = TX_COMMIT
    semantic_class = "adaptation"
    semantic_delta = (
        "Shift boundaries from consecutive BoW cosine drops vs unit order; "
        "no segment timestamps"
    )

    def cache_config(self) -> dict[str, Any]:
        return topic_shift_config()

    def run(
        self,
        document: AnalysisDocument,
        *,
        parents: dict | None = None,
        llm_ctx: Any = None,
        question_text: str | None = None,
    ) -> dict[str, Any]:
        _ = llm_ctx, question_text
        _ = parents
        shift_threshold = require_operation_config().analysis.topic_shift.shift_threshold
        if len(document.units) < 2:
            return {
                "outcome": "insufficient_data",
                "payload": {},
                "warnings": [
                    {
                        "code": "need_two_units",
                        "message": "topic_shift requires ≥2 units",
                    }
                ],
            }

        units = sorted(document.units, key=lambda u: u.order)
        unit_ids, vectors, _ = build_unit_vectors(units)
        consecutive: list[dict[str, Any]] = []
        shifts: list[dict[str, Any]] = []
        for i in range(len(unit_ids) - 1):
            sim = round(cosine(vectors[i], vectors[i + 1]), 6)
            row = {
                "from_unit_id": unit_ids[i],
                "to_unit_id": unit_ids[i + 1],
                "from_order": units[i].order,
                "to_order": units[i + 1].order,
                "from_date": units[i].date,
                "to_date": units[i + 1].date,
                "similarity": sim,
                "is_shift": sim < shift_threshold,
            }
            consecutive.append(row)
            if row["is_shift"]:
                shifts.append(
                    {
                        "boundary_after_unit_id": unit_ids[i],
                        "boundary_before_unit_id": unit_ids[i + 1],
                        "order_after": units[i].order,
                        "similarity": sim,
                    }
                )

        return {
            "outcome": "success",
            "payload": {
                "schema": PAYLOAD_SCHEMA,
                "algorithm_version": ALGORITHM_VERSION,
                "shift_threshold": shift_threshold,
                "consecutive": consecutive,
                "shifts": shifts,
                "n_shifts": len(shifts),
                "n_units": len(unit_ids),
            },
        }
