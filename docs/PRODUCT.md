Type: PRODUCT
Authority: self — product definition and audience; does not own schemas or runtime invariants

# Transcribe product

**Transcribe** is a local-first personal workbench for turning handwritten notebook pages into editable, portable text.

## Promise

On your machine you can:

1. Import JPEG/PNG/PDF pages into a durable managed notebook directory
2. Run local vision OCR via Ollama
3. Review and correct text page by page
4. Run notebook analysis on transcribed text (Overview, Themes, Mood & tone, Moments, Summaries, Ask notebook)
5. Export Markdown, plain text, and a portable `transcribe.notebook` JSON artifact

without requiring a cloud OCR provider or a TranscriptX dependency.

Transcribe’s product direction is a **durable notebook corpus** (identity, managed originals, and human edits survive renames and re-OCR). OCR is one derived process over that corpus. Bulk multi-notebook import is gated on prospective contracts: [notebook-corpus](contracts/notebook-corpus.md), [source-asset](contracts/source-asset.md), [import-run](contracts/import-run.md), [corpus-integrity](contracts/corpus-integrity.md).

## Audience

People who keep paper notebooks (or scans of them) and want searchable, editable text while keeping images and results on disk they control.

## Surfaces today

| Surface | Role |
|---------|------|
| Streamlit UI (port **8510**) | Primary interactive workflow |
| CLI (`transcribe` / `python -m transcribe`) | Automation and integrity checks |
| Shared Python services | Single implementation for UI and CLI |

Supported entrypoints: [public_surfaces.md](public_surfaces.md).

## Product boundaries (v1)

**In scope**

- Local Ollama vision models only (no cloud OCR providers)
- Page-first domain (ordered pages, not timed speaker segments)
- Human edits preserved separately from raw OCR attempts
- Portable export without required absolute paths
- Core notebook analysis modules and Analyse → Run Analysis (optional local text Ollama for LLM modules)
- Deepen-in-place: usability wave — trust, Analyse product UX, first-run operability, daily workbench ([ROADMAP.md](ROADMAP.md) · [usability_wave_plan.md](usability_wave_plan.md))

**Out of scope for current core**

- Cloud OCR / hosted inference as a first-class provider
- Audio transcription or speaker diarization
- Shipping TranscriptX integration (future seam only — [INTEGRATION_SEAM.md](INTEGRATION_SEAM.md))
- OpenCV-based preprocessing pipelines (optional Pillow profiles only; default is none). Visual declutter is a separate import-time Pillow lane (scanner-border crop), not OCR preprocess.
- Deferred analysis reinterpretations and `ocr_quality` — **deferred** on [ROADMAP.md](ROADMAP.md); prefer second-pass LLM OCR cleanup/verification for text quality

## Honesty

See [known_limitations.md](known_limitations.md) for model quality, PDF quirks, analysis capability caveats, and privacy. Shipped vs planned analysis: [ROADMAP.md](ROADMAP.md) · [analysis_wave1_plan.md](analysis_wave1_plan.md).

## Related

- Architecture shape: [ARCHITECTURE.md](ARCHITECTURE.md)
- Contracts: [CONTRACT_INDEX.md](CONTRACT_INDEX.md)
- User flows: [user_guide.md](user_guide.md)
