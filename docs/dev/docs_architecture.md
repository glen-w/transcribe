# Documentation architecture

**Status:** Markdown authority model live; archive hygiene + runtime guide depth landed; Sphinx hosted guide (**I4**) builds this Markdown tree; GitHub Pages landing (**I5**) assembles `website/` + guide.

## Surfaces

| Surface | Role | Authority |
|---------|------|-----------|
| README | Entry + quickstart | Summarizes; links PRODUCT |
| [PRODUCT.md](../PRODUCT.md) | Product definition | Self |
| [ROADMAP.md](../ROADMAP.md) | Product priorities + sequencing (0.9.0 / 0.9-1 / 1.0 and After 1.0 autobiography) | Self |
| [usability_wave_plan.md](../usability_wave_plan.md) | Active usability-wave delivery plan | Self (while U2 open) |
| Contracts + [CONTRACT_INDEX.md](../CONTRACT_INDEX.md) | Behavioural invariants | Contracts |
| `docs/runtime/` | Task-oriented user guides | GUIDE (link contracts) |
| `docs/dev/` | Developer / programme / alignment notes | Developer |
| `docs/reviews/` | Product and module reviews (critique; not contracts) | Product / GUIDE index |
| `docs/archive/` | Historical (banners) | Historical |
| Sphinx HTML (`make docs`) | Hosted view of the same Markdown | [docs_architecture.md](docs_architecture.md) |
| `website/` + GitHub Pages (`make pages-site`) | Public landing + assembled `/guide/` | [website/README.md](../../website/README.md) |
| Root `CHANGELOG.md` / `SECURITY.md` / `CONTRIBUTING.md` | Release notes, trust domain, pointer | Self / `docs/dev/CONTRIBUTING.md` |

## Indexes

- User: [USER_INDEX.md](../USER_INDEX.md)
- Developer: [DEV_INDEX.md](../DEV_INDEX.md)
- Contracts: [CONTRACT_INDEX.md](../CONTRACT_INDEX.md)
- Archive: [ARCHIVE_INDEX.md](../archive/ARCHIVE_INDEX.md)
- Reviews: [reviews/README.md](../reviews/README.md)

## Hosted docs

Owned by infrastructure-wave **I4–I5** ([infrastructure_wave_0_9_plan.md](../infrastructure_wave_0_9_plan.md)) — flip checkboxes when landed:

- [x] Sphinx / Read the Docs scaffold / CI docs job (**I4** — Markdown in-repo remains the corpus; Sphinx builds it; [rtd_go_live_checklist.md](rtd_go_live_checklist.md) for owner hostname go-live)
- [x] Modest `website/` + GitHub Pages assemble (**I5** — `make pages-site`; `.github/workflows/pages.yml`)
- [ ] Workflow walkthroughs with screenshots (**I5**, optional after Pages)

**Content parity:** Sphinx has no separate doc corpus — it builds the Markdown under `docs/` directly. `docs/index.md` uses glob toctrees for `contracts/` and `dev/` so new pages in those trees appear in the hosted nav; `tests/unit/test_sphinx_docs.py` fails if any live `.md` file is missing from that nav. Archive is excluded (`exclude_patterns`). `make docs` → [scripts/release/build_docs.sh](../../scripts/release/build_docs.sh). CI `docs` job uploads HTML. Do not publish a live Read the Docs hostname until the owner checklist is flipped.

Keep entry surfaces concise; detail stays in contracts / runtime / dev. Archive is discoverable via `ARCHIVE_INDEX` only — not listed as live product docs in `USER_INDEX`.

README is the user entry, not a release brief. Do not put `Type:` / `Authority:` headers on Markdown pages (they render on hosted docs). Programme history belongs in ROADMAP / `docs/dev/`, not the first screen.

The public landing, README, and Sphinx “Start here” toctree should tell the same story: what it is → what you can do → privacy → first notebook → install.

Three voices: **user guide** (README, website, Start here, runtime how-tos), **technical reference** (contracts, public surfaces), **maintainer** (ROADMAP, `docs/dev/`, archive, reviews).

## Related

- Docs authority model: [CONTRIBUTING.md](CONTRIBUTING.md)
- Agent SOP: [../../.cursor/commands/docs.md](../../.cursor/commands/docs.md)
