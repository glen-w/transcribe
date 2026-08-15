Type: GUIDE
Authority: export operations — summarizes [notebook-export](../contracts/notebook-export.md); does not redefine schema

# Export

Write portable notebook artifacts from a frozen snapshot. Contract: [contracts/notebook-export.md](../contracts/notebook-export.md). Fine-tune dataset packaging: [finetune_export.md](../finetune_export.md) · [contracts/finetune-export.md](../contracts/finetune-export.md). Full-workspace ZIP backup is separate: [backup_and_restore.md](../backup_and_restore.md).

## This notebook

```bash
./transcribe.sh cli export "$TRANSCRIBE_PROJECTS_DIR/my-notebook"
# … export <project> /path/to/dest
# … export <project> --format pdf --format epub --profile large_print
```

**UI:** **Workflow → Export** (formats, typography, profiles).

### Formats produced

| File | Role |
|------|------|
| `notebook.transcribe.json` | Portable `format: transcribe.notebook` |
| `notebook.md` / `notebook.txt` | Effective text derivatives |
| `notebook.html` / `notebook.epub` / `notebook.pdf` | Reading packages (EPUB needs `ebooklib` / `[export]` or `[ui]`) |
| `export.manifest.json` | Checksums, options, file list |

Default destination is the project `exports/` directory unless overridden (CLI dest / `TRANSCRIBE_EXPORT_DIR`).

Every bundle stamps `content_revision` from the same frozen snapshot used to build all formats.

## Multi-notebook anthology

```bash
./transcribe.sh cli export --notebooks nb-a nb-b --title "Spring journals" /path/to/dest
```

Produces `bundle.transcribe.json` + per-notebook JSON under `notebooks/<slug>/…` with `bundle_revision`.

## Typography profiles

Builtin export profiles: `readable` / `compact` / `large_print` (activate under **Settings → Profiles**, target **export**, or pass `--profile` on the CLI). Settings → Export shows read-only defaults.

## Fine-tune export

Separate CLI for images + preferred/active text packages for external training:

```bash
./transcribe.sh cli export-finetune "$TRANSCRIBE_PROJECTS_DIR/my-notebook"
```

See [finetune_export.md](../finetune_export.md).

## Related

- Settings: [settings.md](settings.md)
- Workspace backup (not notebook export): [backup_and_restore.md](../backup_and_restore.md)
- Golden path: [user_guide.md](../user_guide.md)
