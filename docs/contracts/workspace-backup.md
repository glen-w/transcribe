Type: CONTRACT
Authority: self — full-workspace backup ZIP package and restore semantics. Peers: [notebook-corpus.md](notebook-corpus.md), [project-on-disk.md](project-on-disk.md), [corpus-integrity.md](corpus-integrity.md), [workspace-settings.md](workspace-settings.md). Does not redefine per-notebook or corpus schemas.

# Workspace backup

## Purpose

Portable ZIP of the **authoritative workspace** (notebooks + corpus + config) so operators can move machines, remount Docker volumes, or recover after mistakes — then verify with corpus/notebook doctors. Archives are local files; Transcribe does not upload them.

## Format

- Envelope: `format: transcribe.workspace-backup`, `schema_version: 1`
- Container: ZIP with `ZIP_DEFLATED`
- Manifest member (required, zip root): `transcribe.workspace-backup.json`

## Package layout (role roots)

Absolute host paths are **not** authority. Members use fixed role prefixes remapped to current `RuntimePaths` on restore:

```text
transcribe.workspace-backup.json
projects/          # TRANSCRIBE_PROJECTS_DIR tree
data/
  config/          # settings, profiles, prompts, detection, interface menus
  corpus/          # index, import/ocr/analysis runs, quarantine
  ocr_preference_ledger.json   # when present at backup time
inbox/             # only when includes.inbox
exports/           # only when includes.exports
```

## Manifest fields (v1)

| Field | Required | Meaning |
|-------|----------|---------|
| `format` | yes | `transcribe.workspace-backup` |
| `schema_version` | yes | `1` |
| `created_at` | yes | ISO-8601 UTC timestamp |
| `transcribe_version` | yes | Application version string that wrote the archive |
| `includes` | yes | Object: `projects`, `config`, `corpus`, `ledger`, `inbox`, `exports` (booleans) |
| `counts` | yes | Object: `notebooks`, `files`, `uncompressed_bytes` (non-negative ints; best-effort) |
| `file_index_sha256` | yes | Hex SHA-256 of the sorted file-index lines used at pack time |
| `roots_note` | no | Operator notes; may list role names; must not be required for restore |

**File index** (internal, used to compute `file_index_sha256`): one line per packed file (excluding the manifest itself), sorted lexicographically by member path:

```text
<path>\t<size>\t<sha256>
```

Verify recomputes this index over non-manifest members and compares the digest.

## Always include (when present on disk)

- Entire projects tree for managed notebooks (`project.json`, `sources/`, `pages/`, `results/`, and present `analysis/`, `detection/`, `page_metrics/`)
- `data/config/**`
- `data/corpus/**`
- `data/ocr_preference_ledger.json` when present

`includes.projects`, `includes.config`, and `includes.corpus` are always `true` in valid v1 archives. `includes.ledger` is `true` only when the ledger file was packed.

## Optional includes (default off)

| Flag | Packs |
|------|-------|
| `include_inbox` | `TRANSCRIBE_INBOX_DIR` → `inbox/` |
| `include_exports` | `TRANSCRIBE_EXPORT_DIR` → `exports/` (never pack the destination archive being written) |

## Always exclude

- `data/cache/**` (including `archive.sqlite`) — disposable; rebuild after restore
- `*.lock` files
- `.staging/` directories
- Project-local `.cache/**` and thumbnail caches
- The destination ZIP path itself when it would fall under a packed root

## Create semantics

1. Refuse if the workspace corpus lock is held.
2. Refuse if any managed notebook holds an OCR or analysis job lock.
3. Write via `*.zip.partial` then atomic rename to the destination.
4. Member names must stay under the role prefixes above (zip-slip rejected on write and read).

Default destination: `{TRANSCRIBE_EXPORT_DIR}/backups/transcribe-workspace-<YYYYMMDD-HHMMSS>.zip`.

## Verify semantics

1. Open ZIP; require and parse the root manifest via `require_format(..., "transcribe.workspace-backup")`.
2. Reject members that escape role roots (`..`, absolute paths, unexpected top-level names).
3. Require `projects/` and `data/config/` and `data/corpus/` presence consistent with `includes`.
4. Recompute `file_index_sha256` over packed files; mismatch → fail.

Verify does **not** mutate the workspace.

## Restore semantics (v1)

**Replace-only.** Restore remaps archive role roots onto the **current** `RuntimePaths` (env/Docker mounts). Absolute paths recorded in notes are ignored for placement.

1. `verify` the archive (fail closed).
2. Refuse corpus lock or any notebook OCR/analysis job lock.
3. Unless disabled, create a **safety backup** of the current workspace (same create path; default options) under `{export_dir}/backups/pre-restore-<stamp>.zip`.
4. Replace role roots present in the archive:
   - Clear children of `projects_dir`, then extract `projects/`
   - Replace `data_dir/config/` and `data_dir/corpus/`
   - Replace ledger file when packed; remove local ledger when archive has `includes.ledger` false and no ledger member (leave untouched when ledger was never in scope — v1: if archive omits ledger member, delete local ledger only when `includes.ledger` is false **and** a prior ledger existed under data — simpler rule: **if ledger member present → write it; if absent → leave local ledger as-is**)
   - When `includes.inbox` / `includes.exports`: replace those roots the same way
5. Delete `data_dir/cache/` when present (Archive/FTS rebuilds on next use).
6. Run corpus doctor (`deep=true`); report findings. Successful restore leaves doctor green or warnings-only for documented quarantine retention ([corpus-integrity.md](corpus-integrity.md)).

Dry-run: perform verify + lock checks + describe replacements; write nothing.

## Non-goals (v1)

- Merge / per-notebook restore
- Incremental or differential backups
- Encryption or cloud upload
- Treating `archive.sqlite` as backup authority
- In-browser Streamlit transfer of full archives
