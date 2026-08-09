"""Topic modeling — notebook adaptation; requires notebook_eligibility_v1."""

from __future__ import annotations

from collections import Counter
from typing import Any

from transcribe.analysis.document import AnalysisDocument
from transcribe.analysis.modules._tx_lexical_diversity import tokenize
from transcribe.analysis.modules.wordclouds import _load_stopwords
from transcribe.config.facade import require_operation_config
from transcribe.config.knobs import module_knob_dict

MODULE_ID = "topic_modeling"
MODULE_VERSION = "1c.0"
PAYLOAD_SCHEMA = "topic_modeling_payload_v1"
ALGORITHM_VERSION = "topic_seed_buckets_v1"
TX_COMMIT = "50a0ede8e7acd03bbd9125a5a5237049f3291304"


def topic_modeling_config() -> dict[str, Any]:
    cfg = require_operation_config()
    return {
        "payload_schema": PAYLOAD_SCHEMA,
        "algorithm_version": ALGORITHM_VERSION,
        **module_knob_dict(cfg, MODULE_ID),
    }


def provenance_files() -> list[dict[str, str]]:
    return []


class TopicModelingModule:
    module_id = MODULE_ID
    module_version = MODULE_VERSION
    ported_from_commit = TX_COMMIT
    semantic_class = "adaptation"
    semantic_delta = "Deterministic seed-bucket topics over eligible page units; no sklearn LDA"

    def cache_config(self) -> dict[str, Any]:
        return topic_modeling_config()

    def run(
        self,
        document: AnalysisDocument,
        *,
        parents: dict | None = None,
        llm_ctx: Any = None,
        question_text: str | None = None,
    ) -> dict[str, Any]:
        _ = parents, llm_ctx, question_text
        if len(document.units) < 1:
            return {"outcome": "insufficient_data", "payload": {}}
        stop, _ = _load_stopwords()
        unit_tokens: list[tuple[str, list[str]]] = []
        global_tf: Counter[str] = Counter()
        for unit in document.units:
            toks = [t for t in tokenize(unit.text) if t not in stop and len(t) > 2]
            unit_tokens.append((unit.unit_id, toks))
            global_tf.update(toks)
        if not global_tf:
            return {
                "outcome": "skipped_not_applicable",
                "payload": {},
                "capability_reason": None,
                "warnings": [{"code": "no_tokens", "message": "no eligible tokens"}],
            }
        seeds = [t for t, _ in global_tf.most_common(N_TOPICS)]
        if not seeds:
            return {"outcome": "insufficient_data", "payload": {}}

        topic_term_counts: list[Counter[str]] = [Counter() for _ in seeds]
        topic_units: list[list[str]] = [[] for _ in seeds]
        for unit_id, toks in unit_tokens:
            if not toks:
                continue
            # Assign to seed with max overlap; tie → lowest seed index.
            best_i = 0
            best_score = -1
            for i, seed in enumerate(seeds):
                score = toks.count(seed)
                if score > best_score:
                    best_score = score
                    best_i = i
            topic_term_counts[best_i].update(toks)
            topic_units[best_i].append(unit_id)

        topics = []
        for i, seed in enumerate(seeds):
            terms = [t for t, _ in topic_term_counts[i].most_common(TERMS_PER_TOPIC)]
            if seed not in terms:
                terms = [seed] + [t for t in terms if t != seed][: TERMS_PER_TOPIC - 1]
            topics.append(
                {
                    "topic_id": f"topic_{i}",
                    "label": seed,
                    "terms": terms,
                    "unit_ids": sorted(topic_units[i]),
                    "weight": float(len(topic_units[i])),
                }
            )
        return {
            "outcome": "success",
            "payload": {
                "schema": PAYLOAD_SCHEMA,
                "topics": topics,
                "n_topics": len(topics),
            },
        }
