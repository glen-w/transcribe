Type: GUIDE
Authority: documentation authority model and maintainer checklist for doc changes

# Contributing (docs and code orientation)

## Documentation layers

| Type | Owns | Must not |
|------|------|----------|
| **CONTRACT** | Invariants, schemas, support policy | Duplicate the same rule in a second contract |
| **GUIDE** | Flows and examples | Invent “must/required/invariant” rules |
| **ARCHITECTURE** | Shape and boundaries | Define persisted schemas or support policy |
| **PRODUCT** | Vision, roadmap, status | Own on-disk schema details |

Every live doc starts with:

```text
Type: CONTRACT | GUIDE | ARCHITECTURE | PRODUCT
Authority: …
```

Exception: root `README.md` stays a lightweight entry guide (no Type/Authority banner) and links out.

Archived docs under `docs/archive/` carry an **Archived / superseded** banner and link to a current authority. Do not list them as live product docs in `USER_INDEX`.

## Indexes

- Users: [../USER_INDEX.md](../USER_INDEX.md)
- Developers: [../DEV_INDEX.md](../DEV_INDEX.md)
- Contracts: [../CONTRACT_INDEX.md](../CONTRACT_INDEX.md)
- Archive: [../archive/ARCHIVE_INDEX.md](../archive/ARCHIVE_INDEX.md)
- Surfaces map: [docs_architecture.md](docs_architecture.md)

## Contract authorities (single source of truth)

When you change behaviour for a concept, update the **owning** contract first, then adjust guides to summarize and link.

| Concept | Authority |
|---------|-----------|
| Project layout / journal / locks | [contracts/project-on-disk.md](../contracts/project-on-disk.md) |
| Page results / prefer / fingerprints | [contracts/page-result.md](../contracts/page-result.md) |
| Export / `content_revision` | [contracts/notebook-export.md](../contracts/notebook-export.md) |
| Workspace settings / profiles | [contracts/workspace-settings.md](../contracts/workspace-settings.md) |
| Workspace backup | [contracts/workspace-backup.md](../contracts/workspace-backup.md) |
| Public surfaces / support policy | [public_surfaces.md](../public_surfaces.md) |
| Corpus / import / integrity | [contracts/notebook-corpus.md](../contracts/notebook-corpus.md) · [import-run.md](../contracts/import-run.md) · [corpus-integrity.md](../contracts/corpus-integrity.md) |
| Analysis / detection | analysis-* and detection-* under [CONTRACT_INDEX](../CONTRACT_INDEX.md) |
| Terminology index | [TERMS.md](../TERMS.md) (GUIDE; not authoritative alone) |

## Documentation sync checklist

### 1. Contract changes

It is a docs failure if behaviour changes are only described in README, runtime guides, or architecture without being reflected in the owning contract.

### 2. Guides, architecture, and runtime docs

Hard failure conditions:

- Any GUIDE or ARCHITECTURE that defines project layout, provenance, export schema, or support policy as new rules
- Any `docs/runtime/*` doc that invents invariants instead of summarizing + linking a contract

Fix by moving the rule into the contract and replacing the original with a short summary + link.

### 3. Entry points and examples

1. Confirm CLI / UI examples in README and [public_surfaces.md](../public_surfaces.md) match code
2. Confirm [runtime/docker.md](../runtime/docker.md) matches `docker-compose.yml` mounts and ports
3. Confirm no archived plans are presented as active roadmaps in `USER_INDEX` / README Direction
4. When changing ROADMAP **Now** / product-focus copy, keep [usability_wave_plan.md](../usability_wave_plan.md) in sync and ensure indexes still link the active focus plan. Do not present [ROADMAP.md](../ROADMAP.md) **After 1.0** as current core while U2 / 0.9 remain the path to 1.0.

### 4. When code changes (quick map)

| Change | Update |
|--------|--------|
| Corpus / import / doctor | corpus contracts |
| Page-result / multipass / preference | page-result · ocr-multipass · ocr-preference |
| Analysis / detection | analysis-* · detection-* · notebook-eligibility |
| Tags / organisation catalog | [tag-catalog.md](../contracts/tag-catalog.md) |
| Export / backup | notebook-export · workspace-backup · runtime guides |
| CLI/UI entrypoints | public_surfaces + README links |
| Ownership / shape | ARCHITECTURE |
| Vision / roadmap | PRODUCT · ROADMAP (through 1.0 + After 1.0) · usability_wave_plan |


Then skim guides for stale summaries.

## Formatting

`pyproject.toml` pins **Black** and **Ruff** to line-length **100** and **py310**. Before opening a PR that touches Python:

```bash
black src tests
ruff check --fix src tests
black --check src tests && ruff check src tests
```

## Code orientation

See [developer_quickstart.md](../developer_quickstart.md). Prefer tests that stay offline. Do not add a TranscriptX dependency.
