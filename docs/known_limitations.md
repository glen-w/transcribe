Type: GUIDE
Authority: public honesty page for limits and caveats — does not redefine contracts

# Known limitations

Single place for “what can go wrong / what we are not promising.” Product promise: [PRODUCT.md](PRODUCT.md).

## OCR quality

- Handwriting quality varies widely by model, lighting, and page density
- Vision model availability and architectures differ across Ollama builds (a listed “vision” model may still fail to load)
- Preprocess default is **none**; `gentle_contrast` is optional and Pillow-based (no OpenCV in v1)

## Import / PDF

- Encrypted PDFs are rejected
- Very large sources/PDFs fail closed on configured byte/page/render budgets
- PDF rendering uses PyMuPDF; unusual PDF constructs may render poorly

## Jobs and identity

- Fingerprint skip requires **verified** model identity (digest from Ollama discovery). Unverified tags are always re-run
- Cancelling stops scheduling after the current page; in-flight pages still finish
- Mid-job settings changes apply to the next job only

## Archive / cache

- Workspace search/timeline depends on a rebuildable SQLite cache. Corrupt or incompatible caches are deleted and rebuilt
- Cache signatures use mtimes — acceptable only because projects remain authoritative

## Privacy

- Local-by-default Ollama. Remote hosts exfiltrate page images by design of that configuration
- Transcribe does not ship cloud OCR providers

## Integration

- No TranscriptX dependency. Future notebook handoff is documented separately and is not shipped behaviour: [INTEGRATION_SEAM.md](INTEGRATION_SEAM.md)
