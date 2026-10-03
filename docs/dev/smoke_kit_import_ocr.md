# Import → OCR smoke kit (design)

**Status:** design only. Do not implement in the scope-lean docs pull request. PR CI does not run a vision model and does not need a GPU.

## One path

1. **Import** one committed page image into a temporary notebook (`import`, not a TranscriptX inbox).
2. Run OCR through a **stub vision client** that returns a fixed string. The kit must not call Ollama or a GPU.
3. **Correct** the page: write `edited_text`.
4. Run OCR again on the same page.

## Acceptance

- The second OCR does not overwrite `edited_text`. The human correction survives re-OCR. Raw OCR may update its own attempt record. That is the cousin of “no silent overwrite.”
- A stub that returns whitespace is a **miss**. The page shows up as `empty_output` on Review **Failed OCR**. The kit fails if that page is reported as a successful read.
- Vision OCR (the model that reads the page image) and the opt-in text LLM (Summaries / Ask notebook) are different switches. This kit does not enable the text LLM.

## What proves “no GPU in PR CI” today

| Claim | Quote |
| --- | --- |
| Compose check has no model | Job **`compose-config`** runs `scripts/release/assert_compose_bind.sh` on `docker-compose.yml` only (no `docker-compose.override.yml`, no vision pull) |
| Tests are not a vision pass | Job **`tests`** is pytest |

A later implementation may add `transcribe --help` inside `tests` or `compose-config`. It still must not load a vision model.

## Out of this kit

Autobiography importers, cloud OCR, and any TranscriptX package.
