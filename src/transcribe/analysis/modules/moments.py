"""Moments — notebook salience fork (no TX momentum)."""

from __future__ import annotations

import math
from collections import Counter
from typing import Any

from transcribe.analysis.document import AnalysisDocument, content_fingerprint
from transcribe.analysis.modules._tx_lexical_diversity import tokenize
from transcribe.analysis.modules.wordclouds import _load_stopwords
from transcribe.config.facade import require_operation_config
from transcribe.config.knobs import module_knob_dict

MODULE_ID = "moments"
MODULE_VERSION = "1d.0"
PAYLOAD_SCHEMA = "moments_payload_v1"
ALGORITHM_VERSION = "notebook_salience_fork_v1"
TX_COMMIT = "50a0ede8e7acd03bbd9125a5a5237049f3291304"


def moments_config() -> dict[str, Any]:
    cfg = require_operation_config()
    return {
        "payload_schema": PAYLOAD_SCHEMA,
        "algorithm_version": ALGORITHM_VERSION,
        **module_knob_dict(cfg, MODULE_ID),
    }


def provenance_files() -> list[dict[str, str]]:
    return []


def _soft_maps(parents: dict[str, Any]) -> tuple[dict[str, float], dict[str, float], set[str], list[str]]:
    emo_by: dict[str, float] = {}
    sent_by: dict[str, float] = {}
    shift_boundary: set[str] = set()
    warnings: list[str] = []
    emo = parents.get("emotion") or {}
    for row in emo.get("units") or []:
        if isinstance(row, dict) and row.get("unit_id"):
            emo_by[str(row["unit_id"])] = float(row.get("intensity") or 0.0)
    if not emo_by:
        warnings.append("emotion")
    sent = parents.get("sentiment") or {}
    for row in sent.get("units") or []:
        if isinstance(row, dict) and row.get("unit_id"):
            sent_by[str(row["unit_id"])] = abs(float(row.get("compound") or 0.0))
    if not sent_by:
        warnings.append("sentiment")
    shift = parents.get("topic_shift") or {}
    for row in shift.get("shifts") or []:
        if isinstance(row, dict):
            if row.get("boundary_after_unit_id"):
                shift_boundary.add(str(row["boundary_after_unit_id"]))
            if row.get("boundary_before_unit_id"):
                shift_boundary.add(str(row["boundary_before_unit_id"]))
    if not shift.get("shifts") and "topic_shift" not in parents:
        warnings.append("topic_shift")
    return emo_by, sent_by, shift_boundary, warnings


class MomentsModule:
    module_id = MODULE_ID
    module_version = MODULE_VERSION
    ported_from_commit = TX_COMMIT
    semantic_class = "fork"
    semantic_delta = (
        "Notebook salience fork without TX momentum/pauses; "
        "optional soft features from emotion/sentiment/topic_shift"
    )

    def cache_config(self) -> dict[str, Any]:
        return moments_config()

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
        if not document.units or not document.text.strip():
            return {
                "outcome": "insufficient_data",
                "payload": {},
                "warnings": [
                    {"code": "empty_document", "message": "No units / empty document text"}
                ],
            }

        emo_by, sent_by, shift_boundary, missing_soft = _soft_maps(parents)
        stop, _ = _load_stopwords()
        df: Counter[str] = Counter()
        unit_tokens: list[tuple[Any, list[str]]] = []
        for unit in document.units:
            toks = [t for t in tokenize(unit.text) if t not in stop and len(t) > 2]
            unit_tokens.append((unit, toks))
            df.update(set(toks))
        n_docs = max(1, len(unit_tokens))
        doc_fp = content_fingerprint(document)
        scored: list[dict[str, Any]] = []
        for unit, toks in unit_tokens:
            length_score = min(1.0, len(toks) / 40.0)
            if toks:
                idf_mean = sum(math.log((n_docs + 1) / (df[t] + 1)) + 1.0 for t in toks) / len(
                    toks
                )
                info_score = min(1.0, idf_mean / 3.0)
            else:
                info_score = 0.0
            emo = emo_by.get(unit.unit_id, 0.0)
            sent = sent_by.get(unit.unit_id, 0.0)
            shift = 1.0 if unit.unit_id in shift_boundary else 0.0
            score = round(
                0.35 * length_score
                + 0.25 * info_score
                + 0.20 * emo
                + 0.15 * sent
                + 0.05 * shift,
                6,
            )
            quote = unit.text.strip()
            if len(quote) > 160:
                quote = quote[:157] + "..."
            page_id = None
            ref = unit.source_ref if isinstance(unit.source_ref, dict) else {}
            if isinstance(ref.get("page_id"), str) and ref["page_id"]:
                page_id = ref["page_id"]
            scored.append(
                {
                    "unit_id": unit.unit_id,
                    "page_id": page_id,
                    "order": unit.order,
                    "date": unit.date,
                    "score": score,
                    "features": {
                        "length": round(length_score, 6),
                        "information": round(info_score, 6),
                        "emotion": round(emo, 6),
                        "sentiment": round(sent, 6),
                        "topic_shift": shift,
                    },
                    "quote": quote,
                }
            )
        scored.sort(key=lambda r: (-r["score"], r["order"], r["unit_id"]))
        top_n = require_operation_config().analysis.moments.top_n
        top = scored[:top_n]
        evidence = []
        for row in top:
            unit = next(u for u in document.units if u.unit_id == row["unit_id"])
            evidence.append(
                {
                    "unit_id": unit.unit_id,
                    "quote": row["quote"],
                    "content_fingerprint": doc_fp,
                    "source_ref": dict(unit.source_ref),
                }
            )
        warnings = []
        if missing_soft:
            warnings.append(
                {
                    "code": "reduced_soft_features",
                    "message": (
                        "moments running with reduced soft features; missing: "
                        + ", ".join(missing_soft)
                    ),
                }
            )
        return {
            "outcome": "success",
            "payload": {
                "schema": PAYLOAD_SCHEMA,
                "algorithm_version": ALGORITHM_VERSION,
                "moments": top,
                "n_moments": len(top),
                "soft_features_present": {
                    "emotion": bool(emo_by),
                    "sentiment": bool(sent_by),
                    "topic_shift": bool(shift_boundary) or "topic_shift" in parents,
                },
            },
            "evidence": evidence,
            "warnings": warnings,
            "partial": bool(missing_soft),
        }
