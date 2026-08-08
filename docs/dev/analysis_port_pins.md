Type: PRODUCT
Authority: pin registry template and process for TranscriptX analysis ports — not a runtime contract. Normative result provenance: [../contracts/analysis-result.md](../contracts/analysis-result.md).

# Analysis port pins

Exact TranscriptX source pins for modules copied into Transcribe. A Wave 1 module must not be marked done without a filled row and a `semantic_class`.

External analytical dependencies (models, lexicons, packages) that affect reproducibility are recorded on the result envelope / cache identity per [analysis-result.md](../contracts/analysis-result.md); they are not a substitute for TX source pins below.

## Process

1. Identify the **concrete** upstream TX commit (or tag that resolves to that commit) and file paths copied — slogan-only provenance is non-conformant ([analysis-result](../contracts/analysis-result.md))
2. Record `sha256` of each copied file as landed in Transcribe
3. Set `semantic_class` to `parity` | `adaptation` | `fork` with a short note in the Wave 1 plan / result `semantic_delta`
4. Add the row **before** calling the module implemented
5. Envelope `provenance.ported_from.commit` must match this registry row so later TX diffs are reproducible

## Registry

| module_id | TX commit/tag | source paths | sha256 (per file) | semantic_class | recorded_date |
|-----------|---------------|--------------|-------------------|----------------|---------------|
| `lexical_diversity` | `50a0ede8e7acd03bbd9125a5a5237049f3291304` | `src/transcriptx/core/utils/lexical_diversity.py` (landed as `modules/_tx_lexical_diversity.py`) | `a26acfcd923b32d8b2dc834f06dd6b2dae7064148621bce802e7bc04c0750f3e` | `adaptation` | 2026-08-09 |
| `stats` | n/a (notebook-native adaptation; no TX file copy) | — | — | `adaptation` | 2026-08-09 |
| `understandability` | n/a (notebook-native readability wrap; no TX file copy yet) | — | — | `adaptation` | 2026-08-09 |

## Implementation gate

No Wave 1 module may land until:

1. Contracts indexed: analysis-document, analysis-result, analysis-run-storage, notebook-eligibility
2. [project-on-disk.md](../contracts/project-on-disk.md) reconciled (`analysis/` optional)
3. `notebook_eligibility_v1` has normative ownership in [notebook-eligibility.md](../contracts/notebook-eligibility.md)
4. This registry has an exact TX pin row and semantic classification for that module
