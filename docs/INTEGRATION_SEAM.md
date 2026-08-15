Type: PRODUCT
Authority: future handoff intent only — not shipped behaviour; export schema owned by contracts/notebook-export.md

# Future TranscriptX integration seam

Transcribe does **not** depend on TranscriptX and must not be integrated into TranscriptX before its 1.0 release.

## Handoff

```text
transcribe.notebook JSON
        ↓
future pure adapter (post–TranscriptX 1.0)
        ↓
whatever TranscriptX's post-1.0 document/import contract requires
```

Portable export rules: [contracts/notebook-export.md](contracts/notebook-export.md).

## Non-goals for this seam document

- Do **not** lock synthetic timestamps (e.g. page `i` → `[i, i+1)`).
- Do **not** lock fake speaker labels (e.g. `PAGE` / `NOTEBOOK`).
- Those may be *one* future compatibility strategy among others, but synthetic timing/speakers can leak into timing-, interaction-, or speaker-based analysis as plausible nonsense.

## What Transcribe guarantees (export)

- Portable `format: "transcribe.notebook"` interchange with page order, effective/raw/edited text, content fingerprints, provenance, and notebook `content_revision` when present
- No required absolute filesystem paths in the export
- Page-first domain (not timed speaker segments)

## Related

- Product boundaries: [PRODUCT.md](PRODUCT.md)
- Analysis port planning: [ROADMAP.md](ROADMAP.md) · [analysis_module_porting.md](dev/analysis_module_porting.md) · [analysis_wave1_plan.md](archive/plans/analysis_wave1_plan.md)

Note: analysis ports use a **canonical `AnalysisDocument`** inside Transcribe ([contracts/analysis-document.md](contracts/analysis-document.md)). That is separate from this future *export* handoff into TranscriptX.
