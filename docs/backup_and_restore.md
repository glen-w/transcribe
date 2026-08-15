Type: GUIDE
Authority: user flows and examples — summarizes [contracts/workspace-backup.md](contracts/workspace-backup.md); does not redefine schemas

# Workspace backup and restore

Full-workspace ZIP archives let you copy notebooks, corpus metadata, and config between machines or recover after a bad change. Transcribe never uploads these files.

Operator quick commands also live in [user_guide.md](user_guide.md) §7b. Normative rules: [contracts/workspace-backup.md](contracts/workspace-backup.md). Limits: [known_limitations.md](known_limitations.md).

## What is packed

| Always (when present) | Optional (default off) | Never |
|-----------------------|------------------------|-------|
| Notebooks under `TRANSCRIBE_PROJECTS_DIR` | Inbox (`--include-inbox`) | `data/cache/` (including `archive.sqlite`) |
| `data/config/` (settings, prompts, menus, …) | Exports (`--include-exports`) | `*.lock`, `*.partial`, `.staging/`, thumbs / `.cache/` |
| `data/corpus/` (index, import/OCR/analysis runs) | | Absolute host paths (role roots only) |
| `data/ocr_preference_ledger.json` when present | | |

Archives use format `transcribe.workspace-backup` (schema v1). Members are **role roots** (`projects/`, `data/…`, optional `inbox/`, `exports/`). Restore remaps those roles onto the **current** `TRANSCRIBE_*` mounts — useful when Docker volume paths differ on a new host.

## Recommended practice

1. Keep backups under `{TRANSCRIBE_EXPORT_DIR}/backups/` (default create path).
2. Prefer the **CLI** for large corpora; the Settings UI only accepts on-disk paths (no browser upload/download of multi-GB ZIPs).
3. Run `backup verify` after copying an archive to another disk or machine.
4. Always `restore --dry-run` before `--yes`.
5. Treat ZIP contents as sensitive: page images plus OCR/analysis text, unencrypted.
6. Create a backup before major workspace changes (bulk overwrite imports, host moves, Transcribe upgrades you care about rolling back).

## Create a backup

**CLI**

```bash
# Default: {EXPORT}/backups/transcribe-workspace-<stamp>.zip
./transcribe.sh cli backup create

# Custom destination (refuses overwrite unless --force)
./transcribe.sh cli backup create --dest /safe/path/workspace.zip
./transcribe.sh cli backup create --dest /safe/path/workspace.zip --force

# Also pack inbox and/or exports (skips the zip being written)
./transcribe.sh cli backup create --include-inbox --include-exports
```

Create refuses while a corpus lock or any notebook OCR/analysis job lock is held, when free disk space is too low, or when the destination already exists without `--force`.

**UI:** **Settings → Configuration → Backup** → optional Include inbox / Include exports → **Create backup**. Writes under Exports → `backups/`.

## Verify an archive

```bash
./transcribe.sh cli backup verify /path/to/workspace.zip
```

Checks the manifest, rejects zip-slip / unexpected top-level members, and recomputes `file_index_sha256`. Does not change the workspace.

**UI:** paste the archive path → **Verify archive**.

## Restore (replace-only)

Restore **replaces** notebooks, `data/config`, and `data/corpus` from the archive (plus inbox/exports when those were packed). There is no merge or per-notebook restore in v1.

```bash
# Preview only
./transcribe.sh cli restore /path/to/workspace.zip --dry-run

# Write: requires --yes; writes a safety ZIP first
./transcribe.sh cli restore /path/to/workspace.zip --yes

# Skip the automatic pre-restore safety ZIP (not recommended)
./transcribe.sh cli restore /path/to/workspace.zip --yes --no-safety-backup
```

Default safety archive: `{EXPORT}/backups/pre-restore-<stamp>.zip` with **default** create options (inbox/exports **not** included). After replace, Transcribe deletes rebuildable `data/cache/` and runs corpus doctor (`deep`).

**UI:** paste path → optional **Dry-run restore** → confirm checkbox → **Restore from backup**. Safety ZIP is always written for real restores.

### Guards

- Archive must not sit under a tree restore will wipe (`projects`, `data/config`, `data/corpus`, or inbox/exports when those includes are true).
- Archives under `{EXPORT}/backups/` are safe even when the archive includes exports (that folder is preserved during exports replace).
- Insufficient free disk space refuses before destructive work.
- Busy locks refuse create and restore.

## Moving machines or remounting Docker volumes

1. On the source host: `backup create` (add `--include-inbox` / `--include-exports` if you need those trees).
2. Copy the ZIP to the destination (USB, `scp`, shared disk). Keep it outside trees you will replace, or under the destination’s `exports/backups/`.
3. Point the new host’s `TRANSCRIBE_*` / Compose `HOST_*` mounts at the desired empty or disposable volumes ([runtime/docker.md](runtime/docker.md)).
4. `backup verify` the copied ZIP.
5. `restore --dry-run`, then `restore --yes`.
6. Open **System → Diagnostics** (or `corpus-doctor --deep`) and confirm doctor is green / warnings-only for known quarantine retention.

Role-root layout means you do **not** need identical absolute paths on the new machine.

## If restore fails

1. Read the error: if a safety ZIP was written, the message includes its path.
2. Do **not** keep using a half-replaced workspace for OCR/import until recovered.
3. Restore from the `pre-restore-*.zip` safety archive (`restore --yes` again), or from an older known-good backup.
4. Re-run doctor after a successful restore.

Mid-restore failure after trees were cleared is the main risk; the safety ZIP is the recovery path. Keeping a second copy of important backups off the workspace disk is wise.

## Related surfaces (not the same)

| Surface | Purpose |
|---------|---------|
| Workflow → Export / `transcribe.notebook` JSON | Per-notebook portable export, not full workspace |
| `data/cache/archive.sqlite` | Rebuildable search cache — **not** backup authority |
| Interface “restore built-in” menus | Resets menu defaults only |
| `.cursor/commands/backup.md` | Developer **source-code** zip for agents — not user data |
