Type: PRODUCT
Authority: self — documentation surfaces map for Transcribe; does not own product roadmap or contracts

# Documentation architecture

**Status:** Markdown authority model live; archive hygiene + runtime guide depth landed; Sphinx / hosted guide / workflow walkthroughs deferred.

## Surfaces

| Surface | Role | Authority |
|---------|------|-----------|
| README | Entry + quickstart | Summarizes; links PRODUCT |
| [PRODUCT.md](../PRODUCT.md) | Product definition | Self |
| [ROADMAP.md](../ROADMAP.md) | Product priorities + sequencing | Self |
| [usability_wave_plan.md](../usability_wave_plan.md) | Active usability-wave delivery plan | Self (while U2 open) |
| Contracts + [CONTRACT_INDEX.md](../CONTRACT_INDEX.md) | Behavioural invariants | Contracts |
| `docs/runtime/` | Task-oriented user guides | GUIDE (link contracts) |
| `docs/dev/` | Developer / programme / alignment notes | Developer |
| `docs/archive/` | Historical (banners) | Historical |
| Root `CHANGELOG.md` / `SECURITY.md` / `CONTRIBUTING.md` | Release notes, trust domain, pointer | Self / `docs/dev/CONTRIBUTING.md` |

## Indexes

- User: [USER_INDEX.md](../USER_INDEX.md)
- Developer: [DEV_INDEX.md](../DEV_INDEX.md)
- Contracts: [CONTRACT_INDEX.md](../CONTRACT_INDEX.md)
- Archive: [ARCHIVE_INDEX.md](../archive/ARCHIVE_INDEX.md)

## Hosted docs

- [ ] Sphinx / Read the Docs / GitHub Pages guide (deferred — Markdown in-repo is the corpus)
- [ ] Workflow walkthroughs with screenshots (deferred)

Keep entry surfaces concise; detail stays in contracts / runtime / dev. Archive is discoverable via `ARCHIVE_INDEX` only — not listed as live product docs in `USER_INDEX`.

## Related

- Docs authority model: [CONTRIBUTING.md](CONTRIBUTING.md)
- Agent SOP: [../../.cursor/commands/docs.md](../../.cursor/commands/docs.md)
