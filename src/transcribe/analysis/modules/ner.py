"""NER — spaCy optional extra; speaker assumptions stripped; evidence spans."""

from __future__ import annotations

from collections import Counter
from pathlib import Path
from typing import Any, Callable

from transcribe.analysis.document import AnalysisDocument, content_fingerprint
from transcribe.domain.fingerprint import sha256_bytes

MODULE_ID = "ner"
MODULE_VERSION = "1.3.0"
PAYLOAD_SCHEMA = "ner_payload_v1"
ALGORITHM_VERSION = "spacy_ner_v1"
DEFAULT_MODEL = "en_core_web_sm"

TX_COMMIT = "50a0ede8e7acd03bbd9125a5a5237049f3291304"

# Optional injectable for tests: Callable[[str], list[tuple[str, str, int, int]]]
# returns (surface, label, char_start, char_end)
NlpFn = Callable[[str], list[tuple[str, str, int, int]]]


def _try_spacy_extract(text: str) -> list[tuple[str, str, int, int]] | None:
    try:
        import spacy
    except ImportError:
        return None
    try:
        try:
            nlp = spacy.load(DEFAULT_MODEL)
        except OSError:
            nlp = spacy.load("en_core_web_md")
    except Exception:  # noqa: BLE001
        return None
    doc = nlp(text)
    return [(ent.text, ent.label_, ent.start_char, ent.end_char) for ent in doc.ents]


def ner_config() -> dict[str, Any]:
    return {
        "payload_schema": PAYLOAD_SCHEMA,
        "algorithm_version": ALGORITHM_VERSION,
        "model_name": DEFAULT_MODEL,
    }


def ner_lexicon_or_model() -> dict[str, Any]:
    return {"model_name": DEFAULT_MODEL, "algorithm_version": ALGORITHM_VERSION}


class NERModule:
    module_id = MODULE_ID
    module_version = MODULE_VERSION
    semantic_class = "adaptation"
    semantic_delta = (
        "speaker gates/maps/geocoding removed; page unit evidence; "
        "spaCy optional → unavailable_extra when missing"
    )
    ported_from_commit = TX_COMMIT

    def __init__(self, extract_fn: NlpFn | None = None) -> None:
        self._extract_fn = extract_fn

    def cache_config(self) -> dict[str, Any]:
        return ner_config()

    def run(self, document: AnalysisDocument) -> dict[str, Any]:
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
                "partial": False,
            }

        extract = self._extract_fn
        if extract is None:
            probe = _try_spacy_extract("Alice")
            if probe is None:
                return {
                    "outcome": "skipped_not_applicable",
                    "capability_reason": "unavailable_extra",
                    "payload": {
                        "schema": PAYLOAD_SCHEMA,
                        "error": {
                            "code": "unavailable_extra",
                            "message": "spaCy NER model not available",
                        },
                    },
                    "warnings": [
                        {
                            "code": "unavailable_extra",
                            "message": f"Install spaCy + {DEFAULT_MODEL} for NER",
                        }
                    ],
                    "partial": False,
                }
            extract = lambda text: _try_spacy_extract(text) or []

        doc_fp = content_fingerprint(document)
        entity_counter: Counter[str] = Counter()
        label_counter: Counter[str] = Counter()
        entities: list[dict[str, Any]] = []
        evidence: list[dict[str, Any]] = []
        units_out: list[dict[str, Any]] = []

        for unit in sorted(document.units, key=lambda u: u.order):
            found = extract(unit.text)
            unit_entities: list[dict[str, Any]] = []
            for surface, label, start, end in found:
                entity_counter[surface] += 1
                label_counter[label] += 1
                row = {
                    "surface": surface,
                    "label": label,
                    "unit_id": unit.unit_id,
                    "order": unit.order,
                    "date": unit.date,
                    "char_start": start,
                    "char_end": end,
                }
                unit_entities.append(row)
                entities.append(row)
                quote = unit.text[start:end] if 0 <= start <= end <= len(unit.text) else surface
                evidence.append(
                    {
                        "unit_id": unit.unit_id,
                        "char_start": start,
                        "char_end": end,
                        "quote": quote,
                        "content_fingerprint": doc_fp,
                        "source_ref": dict(unit.source_ref),
                        "label": label,
                    }
                )
            units_out.append(
                {
                    "unit_id": unit.unit_id,
                    "order": unit.order,
                    "date": unit.date,
                    "entity_count": len(unit_entities),
                    "entities": unit_entities,
                }
            )

        payload = {
            "schema": PAYLOAD_SCHEMA,
            "algorithm_version": ALGORITHM_VERSION,
            "model_name": DEFAULT_MODEL,
            "entity_counts": dict(sorted(entity_counter.items(), key=lambda x: (-x[1], x[0]))),
            "label_counts": dict(sorted(label_counter.items(), key=lambda x: (-x[1], x[0]))),
            "entities": entities,
            "units": units_out,
        }
        return {
            "outcome": "success",
            "payload": payload,
            "warnings": [],
            "partial": False,
            "evidence": evidence,
        }


def provenance_files() -> list[dict[str, str]]:
    return [
        {
            "path": "src/transcriptx/core/analysis/ner/__init__.py",
            "sha256": "ec0fc4cce47da61023b3c040ce524fe26b762666445ba3a52e2a1f37432ca99a",
        }
    ]


def code_digest() -> str:
    return sha256_bytes(Path(__file__).read_bytes())
