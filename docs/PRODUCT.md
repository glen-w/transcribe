Type: PRODUCT
Authority: self — product definition and audience; does not own schemas or runtime invariants

# Transcribe product

**Transcribe** is a local-first personal workbench for turning handwritten notebook pages into editable, portable text.

## Promise

On your machine you can:

1. Import JPEG/PNG/PDF pages into a durable project directory
2. Run local vision OCR via Ollama
3. Review and correct text page by page
4. Run notebook analysis on transcribed text (Overview, Themes, Mood & tone, Moments, Summaries, Ask notebook)
5. Export Markdown, plain text, and a portable `transcribe.notebook` JSON artifact

without requiring a cloud OCR provider or a TranscriptX dependency.

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
- Wave 1 notebook analysis modules and Workflow analysis tabs (optional local text Ollama for LLM modules)

**Out of scope for current core**

- Cloud OCR / hosted inference as a first-class provider
- Audio transcription or speaker diarization
- Shipping TranscriptX integration (future seam only — [INTEGRATION_SEAM.md](INTEGRATION_SEAM.md))
- OpenCV-based preprocessing pipelines (optional Pillow profiles only; default is none)
- Wave 2+ analysis reinterpretations (`ocr_quality`, echoes, etc.) until scheduled on [ROADMAP.md](ROADMAP.md)

## Honesty

See [known_limitations.md](known_limitations.md) for model quality, PDF quirks, analysis capability caveats, and privacy. Shipped vs planned analysis: [ROADMAP.md](ROADMAP.md) · [analysis_wave1_plan.md](analysis_wave1_plan.md).

## Related

- Architecture shape: [ARCHITECTURE.md](ARCHITECTURE.md)
- Contracts: [CONTRACT_INDEX.md](CONTRACT_INDEX.md)
- User flows: [user_guide.md](user_guide.md)
