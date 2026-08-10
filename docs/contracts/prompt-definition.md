Type: CONTRACT
Authority: self — versioned prompt definitions, rendering boundaries, hub storage, and structured-output schema identity

# Prompt definition

Generic prompt infrastructure for Transcribe (Prompt Hub). Detection, OCR, and cleanup prompts are addressable as `PromptDefinition` values.

## Identity

- Built-in prompts are identified by `(prompt_id, version)` strings.
- Custom prompts use `prompt_id` under a namespace (e.g. `custom/<slug>`) with monotonic `version`.
- Workspace **overrides** of built-ins keep the same `prompt_id` and bump `version`.
- Prompt identity participates in detection cache identity and OCR job `prompt_sha256` freeze.

## PromptDefinition (logical shape)

| Field | Required | Notes |
|-------|----------|-------|
| `format` | yes (persisted) | `"transcribe.prompt-definition"` |
| `schema_version` | yes (persisted) | `1` |
| `prompt_id` | yes | Stable identifier |
| `version` | yes | Bump on wording or schema change |
| `title` | yes | Catalogue label |
| `description` | no | Human-readable summary |
| `system_prompt` | yes | Fixed instructions; **never** contains template slots |
| `user_template` | yes | Template with data-slot placeholders only |
| `input_mode` | yes | `text` \| `vision` \| `hybrid` |
| `response_schema_id` | yes | Schema id, or `free_text` for OCR/cleanup |
| `prompt_family` | yes | `ocr` \| `cleanup` \| `detection` \| `custom` |
| `model_requirements` | yes | `{capability: text\|vision}` |
| `default_generation_options` | no | Merged with workspace LLM knobs at run time |

## Rendering boundary (normative)

Notebook/page content is **untrusted data**. Renderers must:

1. Keep `system_prompt` free of notebook-derived strings and template slots.
2. Substitute data slots in `user_template` only.
3. Wrap substituted content in explicit delimiters for detection content slots.
4. Never treat notebook text as instructions.

## Storage

| Location | Role |
|----------|------|
| Built-in registry | Code (`prompt_engine.registry` + OCR/cleanup adapters) |
| Workspace custom | `data/config/prompts/custom/<slug>.json` |
| Workspace overrides | `data/config/prompts/overrides/<prompt_id>.json` |
| Project `prompts/` | Optional project-local overrides |

Persisted files use `format: transcribe.prompt-definition` / `schema_version: 1`.

## Resolution order

Project override → workspace override → workspace custom → code builtin (including OCR/cleanup adapters).

## Versioning policy

When `version` changes, prior results remain provenance-addressable. Freshness semantics compare `(prompt_id, version)` in detection cache identity; stale results are marked, not silently upgraded. OCR jobs freeze exact rendered text SHA at job start.
