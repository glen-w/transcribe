# Backup workspace (# backup)

Back up all code from the workspace to a date-stamped zip file, excluding gitignored and library/cache content.

Execute from the repository root. Resolve paths relative to the repo — do **not** hard-code a personal home directory.

---

## What to do

1. **Resolve backup path and date**
   - `REPO_ROOT` = current workspace / git root (e.g. `$(git rev-parse --show-toplevel)` or `$PWD` when already at root)
   - Base directory: `"$REPO_ROOT backup"` (sibling folder next to the repo, same basename + ` backup`)
   - Archive name: `YYMMDD.zip` (e.g. `250306.zip` for 6 Mar 2025). Use shell: `date +%y%m%d`
   - Full destination: `"$REPO_ROOT backup/YYMMDD.zip"`

2. **Create destination**
   - Create the base directory if it does not exist.
   - **Do not overwrite** an existing zip; if `YYMMDD.zip` already exists, use a suffix like `YYMMDD-HHMM.zip`.

3. **Create zip (code only — exclude data, projects, caches)**
   - Stage filtered files to a temp directory, then zip and remove the staging dir.
   - **Goal:** source code, config, docs, and tests — not user OCR projects, page images, or generated artifacts.
   - **Expected size:** small (code-only). Large zips usually mean project dirs or caches slipped in.
   - **Foundational paths (must end up in the zip when they exist):** `src/`, `tests/`, `scripts/`, `docs/`, `assets/`, root manifests (`pyproject.toml`, `requirements*.txt`, `Dockerfile`, `docker-compose*.yml`, `Makefile`, `pytest.ini`, `.env.example`, `NOTICE`, `LICENSE`), and `.cursor/commands/`.
   - **Always exclude** (these dominate backup size if included):
     - `data/`, `projects/`, `outputs/`, `.transcribe/` — local OCR projects, page renders, exports
     - `.test_outputs/`, `.local/` — disposable / local scratch
     - `.git`, `node_modules`, `__pycache__`, `.venv`, `venv`, `env`, `.env`
     - `.pytest_cache`, `.mypy_cache`, `.ruff_cache`
     - `*.pyc`, `*.pyo`, `*.egg-info`, `dist/`, `build/`
     - Model / weight files anywhere: `*.pt`, `*.pth`, `*.bin`, `*.onnx`, `*.safetensors`, `*.gguf`
     - `.DS_Store`, `*.log`, `*.tmp`, `.coverage`, `coverage.xml`, `coverage.json`, `htmlcov/`
   - Also apply patterns from `.gitignore` via `--exclude-from` when that file exists.
   - **Use a suffix when the date-zip already exists** (run from repository root):
     ```bash
     REPO_ROOT="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
     BACKUP_ROOT="${REPO_ROOT} backup"
     STAMP=$(date +%y%m%d)
     ZIP_PATH="$BACKUP_ROOT/${STAMP}.zip"
     if [ -f "$ZIP_PATH" ]; then
       STAMP=$(date +%y%m%d-%H%M)
       ZIP_PATH="$BACKUP_ROOT/${STAMP}.zip"
     fi
     mkdir -p "$BACKUP_ROOT"
     STAGING=$(mktemp -d "${TMPDIR:-/tmp}/transcribe-backup.XXXXXX")
     RSYNC_EXCLUDES=(
       --exclude='.git'
       --exclude='data'
       --exclude='projects'
       --exclude='outputs'
       --exclude='.transcribe'
       --exclude='.test_outputs'
       --exclude='.local'
       --exclude='node_modules'
       --exclude='__pycache__'
       --exclude='.venv'
       --exclude='venv'
       --exclude='env'
       --exclude='.pytest_cache'
       --exclude='.mypy_cache'
       --exclude='.ruff_cache'
       --exclude='*.pyc'
       --exclude='*.egg-info'
       --exclude='dist'
       --exclude='build'
       --exclude='*.pt'
       --exclude='*.pth'
       --exclude='*.bin'
       --exclude='*.onnx'
       --exclude='*.safetensors'
       --exclude='*.gguf'
       --exclude='.DS_Store'
       --exclude='.coverage'
       --exclude='coverage.xml'
       --exclude='coverage.json'
       --exclude='htmlcov'
     )
     RSYNC_INCLUDES=(
       --include='src/***'
       --include='tests/***'
       --include='scripts/***'
       --include='docs/***'
       --include='assets/***'
       --include='.cursor/***'
       --include='*.md'
       --include='*.toml'
       --include='*.txt'
       --include='*.yml'
       --include='*.yaml'
       --include='*.ini'
       --include='*.sh'
       --include='*.example'
       --include='Makefile'
       --include='Dockerfile'
       --include='LICENSE'
       --include='NOTICE'
       --include='.coveragerc'
       --include='.dockerignore'
       --include='.gitignore'
       --exclude='*'
     )
     if [ -f .gitignore ]; then
       rsync -a "${RSYNC_EXCLUDES[@]}" "${RSYNC_INCLUDES[@]}" --exclude-from='.gitignore' . "$STAGING/"
     else
       rsync -a "${RSYNC_EXCLUDES[@]}" "${RSYNC_INCLUDES[@]}" . "$STAGING/"
     fi
     (cd "$STAGING" && zip -rq "$ZIP_PATH" .)
     rm -rf "$STAGING"
     # Verify foundational paths made it into the archive (skip missing paths on greenfield)
     for req in src/transcribe tests pyproject.toml docs .cursor/commands; do
       if [ -e "$REPO_ROOT/$req" ] || [ -e "$REPO_ROOT/${req%/}" ]; then
         unzip -l "$ZIP_PATH" | grep -q "$req" || { echo "BACKUP VERIFY FAILED: missing $req in $ZIP_PATH"; exit 1; }
       fi
     done
     ```

4. **Back up Cursor custom commands to the backup folder**
   - Create `custom-commands` in the backup root (not inside the zip): `mkdir -p "$BACKUP_ROOT/custom-commands"`.
   - Copy the contents of `.cursor/commands/` into it (e.g. `rsync -a .cursor/commands/ "$BACKUP_ROOT/custom-commands/"` from repository root).
   - This keeps the latest command `.md` files at `"$REPO_ROOT backup/custom-commands/"` for easy restore or inspection.

5. **Confirm**
   - After the command, report: zip path (under `"$REPO_ROOT backup/"`), file size (`ls -lh`), and that it completed successfully.

---

## Execution rules

- Run from repository root (`REPO_ROOT`).
- Do not delete or modify the existing workspace; only create the backup zip and update `custom-commands/`.
- If staging, zip, or cleanup fails, report the error and do not assume success (remove any leftover staging dir under `/tmp` if present).
