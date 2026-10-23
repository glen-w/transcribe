# Analysis quality audit

**Status:** freeze sheet for the **25** core module ids  
**Pins:** [analysis_port_pins.md](analysis_port_pins.md)  
**Severity:** [release_severity_triage.md](release_severity_triage.md)  
**Porting map:** [analysis_module_porting.md](analysis_module_porting.md)

Living sheet — one row per registered `MODULE_ID`. **0.9.x / 1.0 freeze:** no new
modules unless an audit proves a release-critical repair. Do not rewrite these
to TranscriptX-depth stacks (sklearn LDA, spaCy NER, speaker momentum).

`semantic_class` is copied from the pin registry. A unit test fails if a
registered `MODULE_ID` disappears from that list.

## Honesty on thinner algorithms

These notebook adaptations are **weaker** than the TranscriptX originals and
must stay labelled as such:

| Module | Algorithm in Transcribe | Must not silently become |
|--------|-------------------------|--------------------------|
| `topic_modeling` | Deterministic **seed-bucket** topics (`topic_seed_buckets_v1`); no sklearn LDA | A different topic engine under the same id |
| `keyphrases` | Notebook **TF-IDF** unigram/bigram ranking | spaCy / TX keyphrase stack |
| `wordclouds` | **Baseline** token frequencies (`enrichment_mode: baseline`) | Keyphrase-enriched clouds without a version bump |
| `bertopic` | Optional extra; missing extra → `unavailable_extra` | Seed-bucket / LDA substitute under this id |
| `moments` | Notebook salience **fork** (no TX momentum) | Speaker-momentum scoring |

Optional extras and LLM modules that cannot run must abstain honestly
(`unavailable_extra` / `unavailable_model`), never invent a substitute payload.

## Rows

| module_id | semantic_class | Intended question | Algorithm honesty | Recommendation | Severity |
|-----------|----------------|-------------------|-------------------|----------------|----------|
| `stats` | adaptation | How long / varied is this notebook? | Page/unit distributions; no speaker rollups | retain | — |
| `lexical_diversity` | adaptation | How diverse is the vocabulary? | Document + per-unit metrics | retain | — |
| `understandability` | adaptation | How readable is the text? | Pure-Python readability (no nltk/textstat) | retain | — |
| `wordclouds` | adaptation | What words dominate? | Baseline frequency path | retain; keep baseline labelled | known limitation vs TX viz |
| `ner` | adaptation | Which names and places appear? | Notebook NER adaptation | retain | — |
| `sentiment` | adaptation | What is the tone by page? | Lexicon / unit sentiment; no speakers | retain | — |
| `epistemic_markers` | adaptation | How certain is the language? | Lexicon markers | retain | — |
| `keyphrases` | adaptation | What phrases stand out? | Notebook TF-IDF | retain; document thinner stack | known limitation vs TX |
| `entity_sentiment` | adaptation | How does tone attach to entities? | Join NER × sentiment | retain | — |
| `topic_modeling` | adaptation | What is this notebook about? | Seed-bucket topics; no sklearn | retain; document thinner stack | known limitation vs TX |
| `semantic_similarity` | adaptation | Which pages are alike? | BoW cosine; multi-speaker gate dropped | retain | — |
| `topic_shift` | adaptation | Where does the subject change? | Order-based cosine-drop | retain | — |
| `bertopic` | adaptation | Clustering when the extra is installed | Optional extra; no silent substitute | retain as optional | known limitation |
| `emotion` | adaptation | What emotions show in the text? | Lexicon emotion | retain | — |
| `contextual_emotion` | adaptation | How does emotion move across pages? | Order-neighbor window | retain | — |
| `fine_grained_emotion` | adaptation | Finer emotion labels | Optional extra → `unavailable_extra` | retain as optional | known limitation |
| `affect_tension` | adaptation | Where does affect tighten? | Join adaptation | retain | — |
| `moments` | fork | Which pages are salient? | Notebook salience; no momentum | retain as fork | known limitation vs TX |
| `highlights` | adaptation | Which quotes matter? | Notebook salience quotes | retain | — |
| `summary` | adaptation | What is the brief? | From-highlights executive brief | retain | — |
| `insights` | adaptation | What themes compose? | Highlights + topics; `notebook_eligibility_v1` | retain | — |
| `llm_summary` | adaptation | Abstractive summary | Optional Ollama; abstain offline | retain | known limitation (model) |
| `llm_action_items` | adaptation | Actions / decisions / questions | Optional Ollama | retain | known limitation (model) |
| `llm_custom_qa` | adaptation | Ask the notebook | Grounded QA; refuse unsupported | retain | known limitation (model) |
| `narrative_summary` | adaptation | Longer narrative | Optional Ollama; `unavailable_model` offline | retain | known limitation (model) |

## Mandatory scrutiny

Deterministic highlights / summaries vs LLM equivalents — keep both, but do not
present an LLM skip as if the deterministic brief were the same claim. Seed-bucket
topics, TF-IDF keyphrases, and baseline wordclouds stay **adaptations**, not
parity with TranscriptX.
