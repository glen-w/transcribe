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

## Indexes

- Users: [../USER_INDEX.md](../USER_INDEX.md)
- Developers: [../DEV_INDEX.md](../DEV_INDEX.md)
- Contracts: [../CONTRACT_INDEX.md](../CONTRACT_INDEX.md)

## When code changes

Update the **owning** doc:

| Change | Update |
|--------|--------|
| Corpus index / notebook identity / workspace locks | [contracts/notebook-corpus.md](../contracts/notebook-corpus.md) |
| Source fingerprints / duplicates / source-render invariants | [contracts/source-asset.md](../contracts/source-asset.md) |
| ImportRun / ImportPlan / bulk resume | [contracts/import-run.md](../contracts/import-run.md) |
| Corpus doctor / bulk-import acceptance gate | [contracts/corpus-integrity.md](../contracts/corpus-integrity.md) |
| Project layout / journal / locks / optional `analysis/` | [contracts/project-on-disk.md](../contracts/project-on-disk.md) |
| Page-result / fingerprint fields | [contracts/page-result.md](../contracts/page-result.md) |
| Analysis document / result / run storage / eligibility | [contracts/analysis-document.md](../contracts/analysis-document.md) · [analysis-result.md](../contracts/analysis-result.md) · [analysis-run-storage.md](../contracts/analysis-run-storage.md) · [notebook-eligibility.md](../contracts/notebook-eligibility.md) |
| Export files / notebook JSON | [contracts/notebook-export.md](../contracts/notebook-export.md) |
| Full-workspace backup ZIP / restore | [contracts/workspace-backup.md](../contracts/workspace-backup.md) · [backup_and_restore.md](../backup_and_restore.md) |
| CLI/UI entrypoints | [public_surfaces.md](../public_surfaces.md) + README links |
| Ownership / component shape | [ARCHITECTURE.md](../ARCHITECTURE.md) |
| Vision / roadmap | [PRODUCT.md](../PRODUCT.md) / [ROADMAP.md](../ROADMAP.md) / [usability_wave_plan.md](../usability_wave_plan.md) (active focus) / [product_hardening_plan.md](../product_hardening_plan.md) (U0/U1 checklist) |

Then skim guides for stale summaries (replace normative drift with a one-line summary + link).

## Formatting

`pyproject.toml` pins **Black** and **Ruff** to line-length **100** and **py310**. Before opening a PR that touches Python:

```bash
black src tests
ruff check --fix src tests
black --check src tests && ruff check src tests
```

## Code orientation

See [developer_quickstart.md](../developer_quickstart.md). Prefer tests that stay offline. Do not add a TranscriptX dependency.
