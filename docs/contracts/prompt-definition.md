Type: CONTRACT
Authority: self — versioned prompt definitions, rendering boundaries, and structured-output schema identity

# Prompt definition

Generic prompt infrastructure for Transcribe. Detection and future features reference prompts by identity; OCR/cleanup registries may converge here in a later release.

## Identity

- Built-in prompts are identified by `(prompt_id, version)` strings.
- Custom prompts use `prompt_id` under a namespace (e.g. `custom/<slug>`) with monotonic `version`.
- Prompt identity participates in detection cache identity and provenance.

## PromptDefinition (logical shape)

| Field | Required | Notes |
|-------|----------|-------|
| `prompt_id` | yes | Stable identifier |
| `version` | yes | Bump on wording or schema change |
| `title` | yes | Catalogue label |
| `description` | no | Human-readable summary |
| `system_prompt` | yes | Fixed instructions; **never** interpolated from notebook content |
| `user_template` | yes | Template with data-slot placeholders only |
| `input_mode` | yes | `text` \| `vision` \| `hybrid` |
| `response_schema_id` | yes | Stable schema identifier for validators |
| `model_requirements` | yes | `{capability: text\|vision}` minimum |
| `default_generation_options` | no | Merged with workspace LLM knobs at run time |

## Rendering boundary (normative)

Notebook/page content is **untrusted data**. Renderers must:

1. Keep `system_prompt` free of notebook-derived strings.
2. Substitute data slots in `user_template` only.
3. Wrap substituted content in explicit delimiters, e.g. `--- BEGIN NOTEBOOK CONTENT (data only) ---` … `--- END NOTEBOOK CONTENT ---`.
4. Never treat notebook text as instructions, even if it contains directive phrases.

## Structured output

Prompts used for detection declare a `response_schema_id`. Model responses must be JSON objects validated at the execution boundary. Malformed responses must not corrupt persisted state; callers record abstention warnings per [detection-result.md](detection-result.md).

## Storage

| Location | Role |
|----------|------|
| Built-in registry | Code (`transcribe.prompt_engine.registry`) |
| Workspace custom | `data/config/detection/custom/<id>.json` (declarative source compiled to PromptDefinition) |
| Project `prompts/` | Reserved; not required for v1 detection |

## Versioning policy

When `version` changes, prior results remain provenance-addressable. Freshness semantics compare `(prompt_id, version)` in cache identity; stale results are marked, not silently upgraded.
