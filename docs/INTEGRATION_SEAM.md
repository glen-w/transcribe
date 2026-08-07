# Future TranscriptX integration seam

Transcribe does **not** depend on TranscriptX and must not be integrated into
TranscriptX before its 1.0 release.

## Handoff

```text
transcribe.notebook JSON
        ↓
future pure adapter (post–TranscriptX 1.0)
        ↓
whatever TranscriptX's post-1.0 document/import contract requires
```

## Non-goals for this seam document

- Do **not** lock synthetic timestamps (e.g. page `i` → `[i, i+1)`).
- Do **not** lock fake speaker labels (e.g. `PAGE` / `NOTEBOOK`).
- Those may be *one* future compatibility strategy among others, but synthetic
  timing/speakers can leak into timing-, interaction-, or speaker-based analysis
  as plausible nonsense.

## What Transcribe guarantees

- Portable `format: "transcribe.notebook"` interchange with page order,
  effective/raw/edited text, content fingerprints, and provenance.
- No required absolute filesystem paths in the export.
- Page-first domain (not timed speaker segments).
