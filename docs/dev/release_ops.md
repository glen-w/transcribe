# Release operations and support

**Status:** drafted for the **1.0** freeze  
**Extends:** [release_governance.md](release_governance.md)  
**Severity:** [release_severity_triage.md](release_severity_triage.md)  
**Install evidence:** [install_verification_matrix.md](../runtime/install_verification_matrix.md)

Define the maintenance promise so it matches the strength of contracts and
release governance. **0.9.0** still keys off U2 + I6; this policy is part of the
**1.0** checklist.

## Supported install profiles

- **Recommended:** Docker Compose on loopback **8510** with host Ollama for vision OCR ([first_notebook.md](../runtime/first_notebook.md)).
- **Development:** host Python via `./transcribe.sh` / `pip install -e .`.
- **Python:** versions declared in `pyproject.toml` / CI (**3.10–3.12**).
- **OS:** macOS and Linux for supported Docker/native cells; Windows best-effort unless a matrix cell says otherwise.
- There is **no** PyPI publish automation. Distribution is versioned git tags plus Docker Compose.

Never bind or document port **8501** (sibling-product port).

## What maintainers will debug

- Supported install paths in the matrix (Docker preferred; native when claimed).
- Import, OCR job truth, Review edits surviving re-OCR, export, backup/restore.
- Offline analysis modules in the frozen 25-id set.
- Loopback bind, Compose mounts, Diagnostics / doctor.

## What maintainers will not debug as a 1.0 defect

- Vision or text **model quality** on a given page (known limitation).
- Missing optional extras (`bertopic`) when the run records `unavailable_extra`.
- Remote Ollama hosts, LAN binds (`0.0.0.0`), or unofficial Streamlit browsers.
- Audio, speakers, TranscriptX runtime integration, autobiography.

## CHANGELOG and migration notes

- Keep [CHANGELOG.md](../../CHANGELOG.md) in Keep a Changelog form.
- Schema or storage behaviour changes require an explicit **migration note**.
- Bumping an on-disk schema that Transcribe cannot load must **refuse** with a clear message; recover via backup ([backup_and_restore.md](../backup_and_restore.md)). Do not silently migrate.

## Tags

- Integration branch: `main`.
- Release tags: `vMAJOR.MINOR.PATCH`. Do not rewrite published tags.
- Local tags for this programme (`v0.9.0`, `v1.0.0`) are not pushed unless the owner asks after they exist locally.

## Issue reporting

- Use GitHub Issues with the templates under `.github/ISSUE_TEMPLATE/`.
- Security-sensitive reports: GitHub private vulnerability reporting only — [SECURITY.md](../../SECURITY.md).

## Support expectations (1.0.x)

- Best-effort maintainer response on GitHub for supported profiles.
- No SLA / paid support in 1.0 scope.
- Unsupported profiles and experimental modules may be closed as known limitations.

## Patch-release policy

- 1.0.x patches: blockers, must-fix regressions, security fixes, documentation corrections.
- No new analysis modules in patch releases unless required to repair a release-critical journey.
- Known limitations stay documented rather than silently “fixed” by removing features.

## Rollback

- Prefer the previous Git tag / previous Compose image.
- If a bad build writes corrupt derived state: stop, restore from a user backup, open an advisory; do not auto-delete notebooks.

## Non-goals

- SLA / paid support
- Multi-tenant hosted operations
- PyPI publish
- Debugging Ollama model quality as if it were a Transcribe defect
