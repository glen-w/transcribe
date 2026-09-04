# OCR preference ledger

Related: [page-result.md](page-result.md), [ocr-multipass.md](ocr-multipass.md), [finetune-export.md](finetune-export.md).

## Ledger file

- Path: `<TRANSCRIBE_DATA_DIR>/ocr_preference_ledger.json` (workspace, not per-notebook)
- `format`: `transcribe.ocr-preference-ledger`
- `schema_version`: `1`
- Append-only `events` array

## Event fields

| Field | Required | Notes |
|-------|----------|-------|
| `ts` | yes | ISO timestamp |
| `notebook_id` | yes | Corpus / project id |
| `page_id` | yes | |
| `attempt_id` | yes | |
| `model_name` | yes | Empty string only if unknown |
| `model_digest` | no | |
| `attempt_kind` | yes | `vision` \| `composite` |
| `action` | yes | `prefer` \| `promote` \| `auto_composite` |
| `pass_id` | no | Multipass id when applicable |

## Authority

- Ledger is product authority for preference **history** and pre-run hints.
- Page `preferred_attempt_id` is authority for the current preferred attempt on that page.
- Doctor may recount current prefers from page results as a secondary check; it must not rewrite the ledger.

## Rollup

Aggregate by `model_name` (optional digest sets): prefer counts, promote counts, composite-prefer counts, distinct pages, last event time. Shown beside vision model pickers before run.
