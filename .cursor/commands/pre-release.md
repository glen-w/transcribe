# Pre-Release Check (# pre-release)

Local **developer-confidence** report for Transcribe. Execute from the workspace root.

## Authority (hard rules)

This command is **not** the release gate and **must not**:

- Change the package version
- Edit `CHANGELOG.md`
- Create, inspect, or approve git tags for release
- Push commits
- Recommend a push or tag
- Claim to block, verify, or create tags
- Present itself as authoritative release governance

**Authoritative next-tag checklist (when present):** `docs/dev/release_governance.md`. If that doc does not exist yet, say so and keep this report local-confidence only.

**Outcomes for every check:** `pass` / `warning` / `failure` / `skipped` (with reason). Environment-dependent checks that cannot run report **`skipped`**, never a silent pass.

Release model (v1 expectation): versioned git tags; local install via `pip install -e .`. Do **not** assume PyPI upload. Docker checks only when Docker packaging exists.

---

## Shared scripts (prefer these over ad-hoc commands)

When present under `scripts/release/` or `scripts/`, prefer them. If missing on greenfield, run the equivalent inline checks below and mark script-backed rows **`skipped` (script not present)**.

| Check | Script (when present) |
|-------|------------------------|
| Denylist / secrets | `bash scripts/secrets_check.sh` |
| Tracked data allowlist | `python3 scripts/release/check_tracked_data.py` |
| Stale refs + TODO gate | `bash scripts/release/stale_refs.sh` |

---

## 0. Optional backup

If the user has not already run `# backup` in this session, recommend running it. Backup failure is a **warning** for this local-confidence command (not a tag authority).

---

## 1. Worktree snapshot

- Report `git status --short` / porcelain v1 with `--untracked-files=all` when git is initialized.
- Dirty or unexpected paths → **failure** for local readiness (do not advise tagging).
- No git repo yet → **warning** (greenfield).
- Branch / remote sync are informational; being behind remote → **warning**.

---

## 2. Tests (when locally available)

- Interpreter gate: `python --version` must satisfy `requires-python` in `pyproject.toml`.
- Run in order (use Makefile targets when present; otherwise):
  1. `pytest -q -m smoke` if smoke marker exists, else skip with reason
  2. `pytest -q` (default suite; must stay fast/offline)
- Failures → **failure**. Unavailable pytest/env → **skipped** with reason.
- Do not require a live Ollama daemon for the default suite.

---

## 3. Packaging smoke

- `python -m build` when packaging is set up (install `build` if needed).
- Install wheel with `--no-deps` into a throwaway check or report import of built wheel path; prefer clean venv when practical.
- Failure → **failure**. Missing packaging config → **skipped**.

---

## 4. Compose + Docker (optional)

- Only if `docker-compose.yml` / `Dockerfile` exists.
- When Docker available: build and a minimal smoke if documented.
- Docker unavailable or no packaging → **skipped** — never pretend pass.
- Ollama need not run inside the image.

---

## 5. Hygiene gates

- Run secrets / tracked-data / stale-ref scripts when present.
- Spot-check that `projects/`, large images/PDFs, and `.env` are not tracked.
- Any denylist / secrets / tracked-data failure → **failure** for the local readiness report. **Do not** recommend tagging or pushing.

---

## 6. Docs + backup/restore coverage (mandatory)

Ensure recent work did not leave new product surfaces undocumented or outside backup/restore.

Scope: compare this branch / dirty worktree against the base branch (or the session’s plan) for **new or changed features, output artifacts, and settings**.

| Check | Pass when | Failure / warning |
|-------|-----------|-------------------|
| Documented | Each new feature / output / setting appears in the right doc layer (CONTRACT for invariants/schemas; GUIDE for flows; indexes link discoverable surfaces) | Undocumented user-visible knob or export → **failure**; minor index-only drift → **warning** |
| `# backup` paths | Code/config/docs for the surface are covered by `# backup` includes; generated/runtime dirs are listed in excludes | New top-level code/doc path missing from backup includes → **failure**; unclear data vs code boundary → **warning** |
| Restore / reopen | Persisted settings and outputs still load after a fresh open (defaults, schema version, migration note). Custom commands remain restorable via `"$REPO_ROOT backup/custom-commands/"` | Broken reopen or missing schema default → **failure**; product corpus backup/restore still a ROADMAP candidate (no API yet) → **warning** (note gap; do not invent APIs) |

No new surfaces in the diff → **pass** (N/A). Record the list of surfaces checked in the summary.

---

## 7. Soft / optional

- `black --check` / `ruff check` / `mypy` → report; auto-fix only if the user asks (this command is non-mutating by default).
- Docs drift beyond §6 → **warning**.
- CI status via `gh` when available → informational; missing CI/gh → **skipped**.

---

## Final summary

| Area | Outcome |
|------|---------|
| Worktree | pass / failure / warning |
| Tests | pass / failure / skipped |
| Packaging | pass / failure / skipped |
| Docker | pass / failure / skipped |
| Hygiene | pass / failure / skipped |
| Docs + backup/restore | pass / failure / warning / skipped |

Then list failures and warnings. End with a **local confidence** line: `CONFIDENT` / `NEEDS FIXES` / `HIGH RISK` — explicitly **not** a release approval.
