"""llm_custom_qa — grounded Ask notebook with unit evidence."""

from __future__ import annotations

from typing import Any

from transcribe.analysis.document import AnalysisDocument
from transcribe.analysis.modules._llm_common import (
    GENERATION_SETTINGS,
    GROUND_DOC_CHUNKS_V1,
    PROMPT_VERSION,
    chunk_context,
    grounded_unit_ids,
    llm_preflight,
    parse_json_object,
)

MODULE_ID = "llm_custom_qa"
MODULE_VERSION = "1e.2.0"
PAYLOAD_SCHEMA = "llm_custom_qa_payload_v1"
TX_COMMIT = "50a0ede8e7acd03bbd9125a5a5237049f3291304"
SYSTEM = (
    "Answer only from the notebook excerpts. JSON only: "
    '{"answer":"...","unit_ids":["..."],"abstain":false}. '
    "If unsupported, set abstain true and empty answer."
)


def llm_custom_qa_config(*, question_text: str = "") -> dict[str, Any]:
    return {
        "payload_schema": PAYLOAD_SCHEMA,
        "prompt_version": PROMPT_VERSION,
        "grounding_strategy_id": GROUND_DOC_CHUNKS_V1,
        "question_text": question_text,
    }


def provenance_files() -> list[dict[str, str]]:
    return []


class LLMCustomQAModule:
    module_id = MODULE_ID
    module_version = MODULE_VERSION
    ported_from_commit = TX_COMMIT
    semantic_class = "adaptation"
    semantic_delta = "Grounded QA with unit citations; refuses unsupported answers"

    def __init__(self, question_text: str = "") -> None:
        self.question_text = question_text

    def cache_config(self) -> dict[str, Any]:
        return llm_custom_qa_config(question_text=self.question_text)

    def run(self, document: AnalysisDocument, *, parents: dict | None = None) -> dict[str, Any]:
        _ = parents
        if not document.units or not document.text.strip():
            return {"outcome": "insufficient_data", "payload": {}}
        question = (self.question_text or "").strip()
        if not question:
            return {
                "outcome": "insufficient_data",
                "payload": {},
                "warnings": [
                    {"code": "missing_question", "message": "question_text required"}
                ],
            }
        pre = llm_preflight()
        if not pre["ok"]:
            return pre["result"]
        client = pre["client"]
        model = pre["model"]
        allowed = grounded_unit_ids(document)
        prompt = (
            f"Question: {question}\n\nExcerpts:\n{chunk_context(document)}\n\n"
            "Answer JSON with unit_ids drawn only from the excerpts."
        )
        try:
            raw = client.generate(
                model=model,
                prompt=prompt,
                system=SYSTEM,
                options=GENERATION_SETTINGS,
            )
        except Exception as exc:  # noqa: BLE001
            return {
                "outcome": "failed",
                "payload": {"error": {"code": "llm_generate", "message": str(exc)}},
            }
        parsed = parse_json_object(raw)
        if not parsed:
            return {
                "outcome": "skipped_not_applicable",
                "payload": {"raw": raw[:2000]},
                "warnings": [
                    {
                        "code": "abstain_unparseable",
                        "message": "model output abstained / unparseable",
                    }
                ],
            }
        if parsed.get("abstain"):
            return {
                "outcome": "skipped_not_applicable",
                "payload": {
                    "schema": PAYLOAD_SCHEMA,
                    "answer": None,
                    "abstain": True,
                    "question": question,
                },
                "warnings": [
                    {
                        "code": "abstain_unsupported",
                        "message": "question unsupported by notebook text",
                    }
                ],
            }
        unit_ids = [u for u in (parsed.get("unit_ids") or []) if u in allowed]
        answer = str(parsed.get("answer") or "").strip()
        if not answer or not unit_ids:
            return {
                "outcome": "skipped_not_applicable",
                "payload": {
                    "schema": PAYLOAD_SCHEMA,
                    "answer": None,
                    "abstain": True,
                    "question": question,
                },
                "warnings": [
                    {
                        "code": "abstain_ungrounded",
                        "message": "refused: missing grounded unit evidence",
                    }
                ],
            }
        evidence = []
        by_id = {u.unit_id: u for u in document.units}
        for uid in unit_ids:
            u = by_id[uid]
            evidence.append(
                {"unit_id": uid, "source_ref": dict(u.source_ref), "question": question}
            )
        return {
            "outcome": "success",
            "payload": {
                "schema": PAYLOAD_SCHEMA,
                "question": question,
                "answer": answer,
                "unit_ids": unit_ids,
                "honesty_label": "llm_generated",
                "model": model,
            },
            "evidence": evidence,
        }
