# Documentation Maintenance (# docs)

Refactor and update project documentation so it matches the current codebase and the documentation architecture.

Run from the workspace root.

Do not modify code during this step unless explicitly requested. After completion, summarize what documentation was updated, which authority boundaries were established, and any remaining documentation gaps or ambiguities.

⸻

Documentation model (must enforce)

Transcribe docs are structured into explicit layers:
	•	CONTRACT — owns invariants, schemas, support policy, and rule definitions (project on-disk format, provenance fields, provider interface expectations, export schema).
	•	GUIDE — owns user/developer flows and examples; may summarize contracts briefly, but may not define rules.
	•	ARCHITECTURE — owns system shape, boundaries, and extension points; defers to contracts for invariants.
	•	PRODUCT — owns roadmap, vision, and planning/status material.

Hard rules
	•	Every major concept must have one authoritative home.
	•	Guides must not define rules.
	•	Architecture docs must not define rules.
	•	Runtime/ops docs must not define invariants or support policy; they may only describe runtime behavior and operations and then link to contracts.
	•	If a guide, architecture doc, or runtime doc contains normative language for project layout, provenance, export schema, or support policy, move or delete it and replace it with a short summary plus a link to the authoritative contract.
	•	Do not create new contract docs lightly; prefer extending an existing authoritative contract when possible.
	•	Do not document TranscriptX integration as shipped behavior until an explicit post-1.0 effort; keep “future consumer” notes in PRODUCT/ARCHITECTURE only.
	•	Shipped delivery history belongs under `docs/archive/` with an **Archived / superseded** banner; do not list archived plans as live product docs in `USER_INDEX`.
	•	Surfaces map: `docs/dev/docs_architecture.md`.

Lint rules (must fail #docs)
	•	Concept uniqueness:
		•	Fail if the same core concept (project layout, provenance, export schema, provider contract) is normatively defined in more than one CONTRACT doc.
	•	GUIDEs:
		•	Fail if any GUIDE contains “must”, “required”, or “invariant” language that defines behavior or rules instead of summarizing a CONTRACT doc.
	•	ARCHITECTURE:
		•	Fail if `docs/ARCHITECTURE.md` (when present) defines behavior or invariants instead of describing structure and boundaries.
	•	TERMS:
		•	Fail if `docs/TERMS.md` (when present) introduces new meanings or rule text instead of acting as a non-authoritative index that points to CONTRACT sections.
	•	Archive:
		•	Fail if a live `USER_INDEX` row presents an archived plan as current product guidance without the archive path / “Not in this index” pattern.
		•	Fail if a file under `docs/archive/` lacks an **Archived / superseded** banner.

⸻

1. Classify docs and add headers

Ensure each core doc begins with:

```text
Type: CONTRACT | GUIDE | ARCHITECTURE | PRODUCT
Authority: <what this doc owns / does not own>
```

**Exception:** `README.md` does **not** require `Type:` / `Authority:` headers (keep the repo landing page lightweight). It should still behave as an entry guide in substance: link to contracts, avoid duplicating normative rules.

Apply or verify at minimum when files exist:
	•	Contracts for project format, provenance, exports, provider expectations
	•	User guide (import → run → review → export)
	•	Developer / architecture overview
	•	Product / roadmap notes

On greenfield with almost no docs: create a minimal set (`README.md` + one ARCHITECTURE + one CONTRACT for the on-disk project format) rather than a large doc tree.

⸻

2. Align docs with code

	•	Walk `src/transcribe/` and confirm documented modules match reality.
	•	Update CLI / Streamlit entrypoints in README when they change.
	•	Ensure Ollama base URL, vision discovery, and offline-test guidance are accurate.
	•	Ensure “preprocessing off by default” and “no OpenCV in v1” (or current policy) are consistent across docs.
	•	Remove stale references to Ollama-OCR APIs that were not carried forward.

⸻

3. README as entry guide

	•	What Transcribe is (local handwritten notebook OCR via Ollama).
	•	Install / run (venv, `pip install -e .`, Streamlit / CLI).
	•	Prerequisites (Ollama + a vision model).
	•	Links to contracts and deeper guides — no duplicated normative schema dumps.
	•	Focus sync: when changing ROADMAP **Now** / product-focus copy, keep [docs/usability_wave_plan.md](../../docs/usability_wave_plan.md) status in sync and ensure README Direction + [USER_INDEX](../../docs/USER_INDEX.md) / [DEV_INDEX](../../docs/DEV_INDEX.md) / [index.md](../../docs/index.md) still link the active focus plan. Historical delivery plans live under [docs/archive/](../../docs/archive/README.md).

⸻

4. Finish

	•	List docs created/updated.
	•	List authority boundaries enforced.
	•	List remaining gaps or ambiguities.
	•	Do not change application code unless the user asked.
