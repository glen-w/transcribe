Type: GUIDE
Authority: operational Docker / Compose layout only — does not define project-format invariants

# Docker

Recommended way to run Transcribe without installing Python packages on the host.
Ollama stays on the host (or another service); the container only runs the app + Streamlit UI.

Native install alternative: [installation.md](installation.md). Product entry: [../PRODUCT.md](../PRODUCT.md).

## Quick start

1. Copy env templates:

```bash
cp .env.example .env
cp docker-compose.override.example docker-compose.override.yml   # optional local overrides
```

2. Set **`HOST_PROJECTS_DIR`** in `.env` to an absolute path **outside this repository**.

```bash
# Example
HOST_PROJECTS_DIR=/Users/you/Documents/transcribe-projects
HOST_INBOX_DIR=/Users/you/Documents/notebook-scans
HOST_EXPORT_DIR=/Users/you/Documents/transcribe-exports
```

3. Build and start:

```bash
docker compose up --build transcribe-web
```

Open http://127.0.0.1:8510 (Transcribe uses **8510**, not 8501).

## Path pattern (same idea as TranscriptX)

| Host (Compose) | Container mount | App env |
|----------------|-----------------|---------|
| `HOST_PROJECTS_DIR` | `/mnt/projects` | `TRANSCRIBE_PROJECTS_DIR` |
| `HOST_INBOX_DIR` | `/mnt/inbox` | `TRANSCRIBE_INBOX_DIR` |
| `HOST_EXPORT_DIR` | `/mnt/exports` | `TRANSCRIBE_EXPORT_DIR` |
| `HOST_DATA_DIR` (default `./data`) | `/data` | `TRANSCRIBE_DATA_DIR` |
| `HOST_BULK_IMPORT_DIR` (optional, via override) | `/mnt/notebooks` | — (paste path in Import → Batch) |

Separate `HOST_*` vs `TRANSCRIBE_*` names avoid Compose `.env` vs `environment:` precedence surprises.

Prefer absolute host paths **outside the git clone** for projects, inbox, and exports so wiping the repo never deletes notebook work.

Project folder internals: [../contracts/project-on-disk.md](../contracts/project-on-disk.md).

### Bulk import paths (Import → Batch / CLI in Docker)

The Streamlit process only sees **container** paths. In **Workflow → Import → Batch**, enter:

| Goal | Path to paste |
|------|----------------|
| Default inbox mount | `/mnt/inbox` (or a subfolder) |
| Extra scans mount (override) | `/mnt/notebooks` |

Do **not** paste host paths such as `/Users/you/Documents/notebooks`. Those are invisible inside the container; relative resolution against `working_dir: /data` often surfaces as `not a directory: /data/Users/...`.

To expose another host folder, set `HOST_BULK_IMPORT_DIR` in `.env` and mount it in `docker-compose.override.yml` (see the `.example`), then recreate:

```bash
# .env
HOST_BULK_IMPORT_DIR=/Users/you/Documents/notebooks

# docker-compose.override.yml volumes entry
# - ${HOST_BULK_IMPORT_DIR}:/mnt/notebooks:ro

docker compose up -d --force-recreate transcribe-web
```

CLI via Compose uses the same mounts: `docker compose exec transcribe-web transcribe bulk-import folders /mnt/notebooks …`.

## Ollama

Compose defaults `TRANSCRIBE_OLLAMA_BASE_URL` to `http://host.docker.internal:11434`.
`extra_hosts: host.docker.internal:host-gateway` covers Linux Docker Engine.

Ensure a vision-capable model is already pulled on the host Ollama instance. Privacy caveats: [../known_limitations.md](../known_limitations.md).

## Local override

`docker-compose.override.yml` (from the `.example`) can:

- Mount `./src/transcribe` into site-packages for live code edits
- Drop `:ro` on the inbox mount
- Mount `HOST_BULK_IMPORT_DIR` → `/mnt/notebooks` for Import → Batch of a folder tree outside the default inbox

The override file is gitignored; keep machine-specific paths there or in `.env`.

## Security bind

Published port defaults to loopback:

```yaml
"${TRANSCRIBE_BIND_HOST:-127.0.0.1}:8510:8510"
```

LAN opt-in: `TRANSCRIBE_BIND_HOST=0.0.0.0` (unauthenticated UI access on your network).

## Ownership

Service runs as `${UID:-1000}:${GID:-1000}`. On macOS/Linux, export matching ids if mounts look root-owned:

```bash
export UID="$(id -u)"
export GID="$(id -g)"
```

## Related

- Surfaces: [../public_surfaces.md](../public_surfaces.md)
- User flows: [../user_guide.md](../user_guide.md)
