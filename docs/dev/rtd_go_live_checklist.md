# Read the Docs go-live checklist

**Status:** prep only (**I4**) — do **not** publish a live Read the Docs hostname in-repo until the project exists.
`scripts/release/stale_refs.sh` denylists the public RTD hostname pattern until then.

## Prerequisites

- [x] Sphinx tree builds locally / CI (`make docs`, `.readthedocs.yml`)
- [ ] Owner creates the RTD project and chooses slug / custom domain

## Flip steps (when slug is ready)

1. Confirm RTD builds from `.readthedocs.yml` on the default branch.
2. Note the public docs URL for the chosen slug (RTD project homepage).
3. Update `scripts/release/stale_refs.sh`: remove or narrow the RTD hostname denylist so the intentional URL is allowed.
4. Point README and [docs_architecture.md](docs_architecture.md) at the live URL.
5. Optionally enable Sphinx `linkcheck` in CI against the published tree.
6. Run `bash scripts/release/stale_refs.sh` and docs CI green before tagging.

## Until then

- User docs remain in-repo via [USER_INDEX.md](../USER_INDEX.md).
- Sphinx HTML is rebuilt from the same `docs/` Markdown on every CI run (`make docs`).
- GitHub Pages assemble (`website/` + `/guide/`) is infrastructure-wave **I5**, not this checklist.
