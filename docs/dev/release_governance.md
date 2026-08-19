Type: GUIDE
Authority: self

# Release governance (manual next-tag checklist)

This document is the **authoritative release gate** for public version tags. It is **not** enforced by `.cursor/commands/pre-release.md` (local developer confidence only).

**Do not create the next version tag until every item below is green.**

Distribution (v1): versioned git tags; local install via `pip install -e .` / `./transcribe.sh`; Docker Compose. There is **no** PyPI publish automation.

## Checklist

1. **Green CI** on the exact intended release commit: jobs `compose-config`, `lint`, `tests` (Python **3.10–3.12**), `docs`, and `release-checks`. Failed or cancelled matrix members block.
2. `pyproject.toml` version matches `transcribe.__version__` and the intended tag (`v` prefix aside).
3. Dated Keep-a-Changelog section for that version in `CHANGELOG.md`.
4. Clean worktree (`git status --porcelain=v1 --untracked-files=all` empty of unexpected paths).
5. Release-evidence bundle complete (runbook below).
6. Fixable CVEs cleared **or** exceptional waiver filled in [dependency_audit.md](dependency_audit.md).
7. No denylist violations; `scripts/secrets_check.sh` green.
8. Compose default bind remains loopback (`scripts/release/assert_compose_bind.sh`).
9. **I5–I6 not yet required for 0.8 tags:** GitHub Pages, nightly, and full Docker image audit wait for **0.9.0**. Sphinx/CI docs (**I4**) is required on the intended SHA. When I5–I6 land, they join this checklist.

Humans (or an explicit user instruction outside the pre-release command) perform tag/push after this checklist is satisfied.

## Release-evidence bundle

Record each outcome as `pass` / `failure` / `skipped` (with reason). Environment-dependent checks that cannot run must be **`skipped`**, never a silent pass.

### A. Always-run hygiene (no Docker required)

```bash
bash scripts/release/stale_refs.sh
python3 scripts/release/check_tracked_data.py
bash scripts/secrets_check.sh
python3 scripts/release/repo_hygiene_audit.py --strict --checks root_md,archive_banners
python3 -c "import re, pathlib; from transcribe import __version__; t=pathlib.Path('pyproject.toml').read_text(); m=re.search(r'^version\s*=\s*\"([^\"]+)\"', t, re.M); assert m and m.group(1)==__version__, (m.group(1) if m else None, __version__); print(__version__)"
```

Prefer `pip install -e .` (or `PYTHONPATH=src`) so the version check reads this tree.

### B. Compose bind

```bash
bash scripts/release/assert_compose_bind.sh
```

Static file check always runs. Live `docker compose config` runs when Docker is available; set `TRANSCRIBE_STRICT_COMPOSE=1` to require Docker.

### C. Tests + coverage

```bash
make test-smoke
make test-fast
make test-coverage
```

Default suite stays **offline** (no live Ollama). Coverage `fail_under` is `.coveragerc`.

### D. Package build + import smoke

```bash
python -m pip install -U build
python -m build --wheel
python -c "import glob, subprocess, sys; w=glob.glob('dist/transcribe-*.whl')[-1]; subprocess.check_call([sys.executable, '-m', 'pip', 'install', '--no-deps', w]); import transcribe; print(transcribe.__version__)"
```

### E. Docker (optional until I6; required for tag when Docker is available)

```bash
docker compose -f docker-compose.yml build
make docker-smoke
```

Expected: `pass`, or `skipped (Docker not available)` until I6 makes image smoke a CI job.

### F. CI on exact commit

Confirm GitHub Actions on the intended SHA: `tests` (3.10–3.12), `compose-config`, `lint`, `docs`, `release-checks` are green.

## Relationship to `# pre-release`

`.cursor/commands/pre-release.md` is a **local confidence** report. It must not bump versions, edit the changelog, or create tags. This file is the tag checklist. Prefer the scripts in the table in that SOP over inline fallbacks.
