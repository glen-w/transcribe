Type: PRODUCT
Authority: pin registry template and process for TranscriptX analysis ports — not a runtime contract. Normative result provenance: [../contracts/analysis-result.md](../contracts/analysis-result.md).

# Analysis port pins

Exact TranscriptX source pins for modules copied into Transcribe. A core module must not be marked done without a filled row and a `semantic_class`.

External analytical dependencies (models, lexicons, packages) that affect reproducibility are recorded on the result envelope / cache identity per [analysis-result.md](../contracts/analysis-result.md); they are not a substitute for TX source pins below.

## Process

1. Identify the **concrete** upstream TX commit (or tag that resolves to that commit) and file paths copied — slogan-only provenance is non-conformant ([analysis-result](../contracts/analysis-result.md))
2. Record `sha256` of each copied file as landed in Transcribe
3. Set `semantic_class` to `parity` | `adaptation` | `fork` with a short note in the delivery history / result `semantic_delta`
4. Add the row **before** calling the module implemented
5. Envelope `provenance.ported_from.commit` must match this registry row so later TX diffs are reproducible

## Registry

| module_id | TX commit/tag | source paths | sha256 (per file) | semantic_class | recorded_date |
|-----------|---------------|--------------|-------------------|----------------|---------------|
| `stats` | n/a (notebook-native adaptation) | — | — | adaptation | 2026-08-09 |
| `lexical_diversity` | `50a0ede8e7acd03bbd9125a5a5237049f3291304` | `src/transcriptx/core/utils/lexical_diversity.py` → `transcribe/analysis/modules/_tx_lexical_diversity.py` | `a26acfcd923b32d8b2dc834f06dd6b2dae7064148621bce802e7bc04c0750f3e` | adaptation | 2026-08-09 |
| `understandability` | n/a (notebook-native pure-Python adaptation; TX uses nltk/textstat) | — | — | adaptation | 2026-08-09 |
| `wordclouds` | n/a (notebook-native adaptation; TX wordclouds uses spaCy/speaker/viz stack — baseline frequency path only) | — | stopwords digest `59b09014b432830d8fc50e4421fd984602d17fb5b0900f4ddce3e2bbe3fa04e6` (`wordclouds_stopwords_v1`) | adaptation | 2026-08-09 |
| `ner` | `50a0ede8e7acd03bbd9125a5a5237049f3291304` | `src/transcriptx/core/analysis/ner/__init__.py` | `ec0fc4cce47da61023b3c040ce524fe26b762666445ba3a52e2a1f37432ca99a` | adaptation | 2026-08-09 |
| `sentiment` | `50a0ede8e7acd03bbd9125a5a5237049f3291304` | `src/transcriptx/core/analysis/sentiment/__init__.py` | `94070e07c0ac03844a370ab044a47849312b8e2c9c3b145cf8f48a3ab036272c` | adaptation | 2026-08-09 |
| `epistemic_markers` | `50a0ede8e7acd03bbd9125a5a5237049f3291304` | `src/transcriptx/preprocessing/lexicons/epistemic_markers_en.json`; `src/transcriptx/core/analysis/lexicon_markers/__init__.py` | lexicon `eb260297c1880ee04fdf4ed3167ce5c59e91e20ee95b7aed1fe93355a2f31a34`; markers `85879f6d34591c90403b0f25ccadc5581ce76d84c70bd378a41e5e86cfa67a9d` | adaptation | 2026-08-09 |
| `keyphrases` | `50a0ede8e7acd03bbd9125a5a5237049f3291304` | `src/transcriptx/core/analysis/keyphrases/` (scoring idea) | n/a notebook TF-IDF adaptation | adaptation | 2026-08-09 |
| `entity_sentiment` | `50a0ede8e7acd03bbd9125a5a5237049f3291304` | `src/transcriptx/core/analysis/entity_sentiment/` | n/a join adaptation | adaptation | 2026-08-09 |
| `topic_modeling` | `50a0ede8e7acd03bbd9125a5a5237049f3291304` | `src/transcriptx/core/analysis/topic_modeling/` | n/a seed-bucket adaptation (no sklearn) | adaptation | 2026-08-09 |
| `semantic_similarity` | `50a0ede8e7acd03bbd9125a5a5237049f3291304` | `src/transcriptx/core/analysis/semantic_similarity/` | n/a BoW cosine adaptation; multi-speaker gate dropped | adaptation | 2026-08-09 |
| `topic_shift` | `50a0ede8e7acd03bbd9125a5a5237049f3291304` | `src/transcriptx/core/analysis/topic_shift/` | n/a order-based cosine-drop adaptation | adaptation | 2026-08-09 |
| `bertopic` | `50a0ede8e7acd03bbd9125a5a5237049f3291304` | `src/transcriptx/core/analysis/bertopic/` | n/a optional extra → `unavailable_extra` (no silent substitute) | adaptation | 2026-08-09 |
| `emotion` | `50a0ede8e7acd03bbd9125a5a5237049f3291304` | `src/transcriptx/core/analysis/emotion/` | lexicon digest via `emotion_lexicon_v1` | adaptation | 2026-08-09 |
| `contextual_emotion` | `50a0ede8e7acd03bbd9125a5a5237049f3291304` | `src/transcriptx/core/analysis/contextual_emotion/` | n/a order-neighbor window adaptation | adaptation | 2026-08-09 |
| `fine_grained_emotion` | `50a0ede8e7acd03bbd9125a5a5237049f3291304` | `src/transcriptx/core/analysis/fine_grained_emotion/` | n/a optional extra → `unavailable_extra` | adaptation | 2026-08-09 |
| `affect_tension` | `50a0ede8e7acd03bbd9125a5a5237049f3291304` | `src/transcriptx/core/analysis/affect_tension/` | n/a join adaptation | adaptation | 2026-08-09 |
| `moments` | `50a0ede8e7acd03bbd9125a5a5237049f3291304` | `src/transcriptx/core/analysis/moments/` | n/a notebook salience **fork** (no momentum) | fork | 2026-08-09 |
| `highlights` | `50a0ede8e7acd03bbd9125a5a5237049f3291304` | `src/transcriptx/core/analysis/highlights/` | n/a notebook salience adaptation | adaptation | 2026-08-09 |
| `summary` | `50a0ede8e7acd03bbd9125a5a5237049f3291304` | `src/transcriptx/core/analysis/summary/` | n/a from-highlights adaptation | adaptation | 2026-08-09 |
| `insights` | `50a0ede8e7acd03bbd9125a5a5237049f3291304` | `src/transcriptx/core/analysis/insights/` | n/a; eligibility via `notebook_eligibility_v1` | adaptation | 2026-08-09 |
| `llm_summary` | `50a0ede8e7acd03bbd9125a5a5237049f3291304` | `src/transcriptx/core/analysis/llm_summary.py` | n/a Ollama text adaptation | adaptation | 2026-08-09 |
| `llm_action_items` | `50a0ede8e7acd03bbd9125a5a5237049f3291304` | `src/transcriptx/core/analysis/llm_action_items.py` | n/a Ollama text adaptation | adaptation | 2026-08-09 |
| `llm_custom_qa` | `50a0ede8e7acd03bbd9125a5a5237049f3291304` | `src/transcriptx/core/analysis/llm_custom_qa/` | n/a grounded QA adaptation | adaptation | 2026-08-09 |
| `narrative_summary` | `50a0ede8e7acd03bbd9125a5a5237049f3291304` | `src/transcriptx/core/analysis/narrative_summary.py` | n/a; unavailable_model when LLM offline | adaptation | 2026-08-09 |

## Implementation gate

No core module may land until:

1. Contracts indexed: analysis-document, analysis-result, analysis-run-storage, notebook-eligibility
2. [project-on-disk.md](../contracts/project-on-disk.md) reconciled (`analysis/` optional)
3. `notebook_eligibility_v1` has normative ownership in [notebook-eligibility.md](../contracts/notebook-eligibility.md)
4. This registry has an exact TX pin row and semantic classification for that module
