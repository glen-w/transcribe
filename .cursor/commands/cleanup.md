# Workspace Cleanup & Quality Pass (# cleanup)

Run a code quality and hygiene pass to ensure the codebase is clean, consistent, and type-safe.
Execute from the workspace root.

After running, summarize issues found and confirm whether the workspace is clean.

---

## 0. Run backup first (mandatory)

Before doing anything else, run the **backup** custom command (`# backup`). Wait for it to complete, then proceed with the steps below.

---

## Dry-run first & sanity checks (mandatory)

- **Dry-run first:** Any destructive step must have a preview/list step run first; apply/delete only after reviewing.
- **No recursive delete at root:** No `rmtree`/`rm -rf` on `.`, `..`, or any path that could contain the whole repo (e.g. workspace root, `src/`, or any dir containing `pyproject.toml`). If a command would delete outside a known-safe scratch subdir (`data/`, `projects/`, `outputs/`, `.test_outputs/`), do not run the apply step and report the risk.
- **Flag or abort on large deletions:** Before deleting many files under project/output dirs:
  - List or estimate size/count first.
  - If the scope suggests a **huge** deletion (e.g. > ~1 GB or very large file count), **do not delete**; report and skip.
  - Only remove a small, explicitly confirmed set after the user agrees.
- **Never delete user OCR projects** under `projects/` (or configured project roots) without explicit per-path confirmation.

---

## 0. Cleanup Before Quality Pass

<!-- DISABLED: Delete/remove steps commented out after repeated data loss. Re-enable only with explicit user request and extreme care. -->
- **List (dry-run only)** ad hoc summaries and test reports in `tests/` without deleting: e.g. `TEST_EXPANSION_SUMMARY.md`, `TEST_HEALTH_REPORT.md`, `TEST_SUITE_ASSESSMENT.md`, and similar `TEST_*_SUMMARY.md` / `TEST_*_REPORT.md` / `TEST_*_ASSESSMENT.md`. Report the list; do **not** delete.
- **Test / project artifact cleanup:** If the user asks to clean artifacts, list candidates under `outputs/`, `.test_outputs/`, or temp render dirs and only delete with explicit confirmation; do not run bulk deletes without preview.
<!-- - **Delete ad hoc summaries...** then delete only those files - DISABLED -->

---

## 1. Formatting

- **Run formatter**
  Use the project formatter: `black src/ tests/ scripts/*.py` (config in `pyproject.toml` when present). Do not run `black .` at repo root (can touch .venv/site-packages).
- **Sort imports**
  If the project uses ruff for import sorting, run `ruff check --fix .` (handled in step 2). Otherwise ensure no separate isort step is required.
- **Ensure no formatting diffs remain**
  After formatting, run `black --check src/ tests/ scripts/*.py` to confirm no further changes; fix any remaining diffs.

---

## 2. Linting

- **Run ruff** (or the configured linter)
  `ruff check src/ tests/ --fix`
- **Fix auto-fixable issues**
  Apply fixes from the first run; re-run if ruff made changes.
- **Summarize remaining issues**
  List any remaining warnings or errors that are not auto-fixable.

---

## 3. Type Checking

- **Run mypy**
  `mypy src/` (or project roots as in `pyproject.toml` [tool.mypy]). Use `--ignore-missing-imports` if the project does so (e.g. pre-commit).
- **Summarize type errors**
  List file and line for each error.
- **Suggest minimal fixes**
  Propose only the minimal change to satisfy the type checker. Do not refactor beyond that unless explicitly requested.

---

## Execution Rules

- Do **not** introduce new features.
- Do **not** perform structural refactors.
- Only fix **formatting**, **lint**, and **type** issues unless explicitly asked.
- After completion, provide a short summary with:
  - **Formatting:** what was changed (files/lines) or "no changes."
  - **Lint:** issues fixed and any remaining warnings/errors.
  - **Types:** type errors found and minimal fixes applied or suggested.
  - **Tests:** status (e.g. "all passed" or "N failed" with summary).
