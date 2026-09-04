# Transcribe website

Modest public landing (plain HTML/CSS, minimal JS for mobile nav). Product front door: hero → what the app does → outcomes → privacy → first path → install.

- Open `index.html` locally, or deploy via GitHub Pages (`.github/workflows/pages.yml`).
- Optional screenshots can live in [images/](images/) later (workflow stills); the landing ships without them.
- Footer version should match [pyproject.toml](../pyproject.toml) `version` (currently **0.8.7**).
- Install snippet matches README: native `./transcribe.sh setup` then `./transcribe.sh ui`; Docker is the alternative (`HOST_PROJECTS_DIR` + `docker compose up --build transcribe-web`).
- Docs CTAs point at the **Sphinx HTML guide** published beside this landing (`./guide/`), rebuilt from `docs/` on every qualifying `main` push.
- The sticky header nav is shared with `/guide/` via `website/chrome/` (Sphinx injects the same chrome).
- Full local preview (landing + guide): `pip install -e '.[docs]' && make pages-site` then open `_site/index.html`.
- Ko-fi support link in footer: https://ko-fi.com/C0C1XK8G
