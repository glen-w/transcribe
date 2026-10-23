# Install verification matrix

Evidence cells for a **0.9.0 / 1.0** tag. Fill `pass` / `failure` / `skipped` (with
reason). Do not record a silent pass. Docker is the preferred everyday path.

Related: [first_notebook.md](first_notebook.md) · [installation.md](installation.md) ·
[docker.md](docker.md) · [release_governance.md](../dev/release_governance.md)

| Profile | Ollama | Check | Result |
|---------|--------|-------|--------|
| Docker Compose (`transcribe-web`, port **8510**, loopback bind) | Host Ollama on loopback | Image builds; UI health; `transcribe models` via `docker compose exec` | |
| Docker Compose | Host Ollama missing | Diagnostics / Home show not reachable; no crash | |
| Native `./transcribe.sh setup` + `ui` | Host Ollama | App on **8510**; first notebook import | |
| Native | No Streamlit extra | CLI `transcribe --help` still works | |
| Linux Docker Engine | Host Ollama via `host.docker.internal` | extra_hosts works; OCR picker sees models | |
| macOS Docker Desktop | Host Ollama | Same as Docker row | |

Leave cells blank until a human or `# pre-release` fills them for a tag SHA.
Skipped cells need a reason (no Docker on the machine, no vision model, …).
