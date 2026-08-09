Type: CONTRACT
Authority: self — normative `interface_menus` envelope, schema versioning, fail-closed load, sanitisation, and lock+revision CAS write rules for durable user-owned action-menu preferences.

# Interface menus

Durable user configuration for configurable action-link strips in the Streamlit UI (Archive / View notebook cards; Settings → Interface).

**Format identity:** `transcribe.interface-menus` schema version **1**.

**On-disk location:** `{TRANSCRIBE_DATA_DIR}/config/interface_menus.json` (default `data/config/interface_menus.json`).

## Envelope

```json
{
  "schema_version": 1,
  "prefs": {
    "standard_menu_mode": "built_in",
    "standard_menu": [],
    "sections": {
      "archive_notebook": {
        "show_menu": true,
        "mode": "section_default",
        "selected": []
      }
    }
  },
  "prefs_hash": "<sha256 of canonical prefs JSON>"
}
```

| Field | Rule |
|-------|------|
| `schema_version` | Must be integer `1` for this build |
| `prefs` | Object; merged onto built-ins then sanitised |
| `prefs_hash` | SHA-256 hex of `json.dumps(prefs, sort_keys=True, separators=(",", ":"))` UTF-8; mismatch → fail-closed |

## Fail-closed load

Missing file, unreadable file, corrupt JSON, non-object envelope, missing/unknown/`schema_version` ≠ 1, or `prefs_hash` mismatch → runtime uses **built-in prefs**, file is **preserved**, and a bounded recovery diagnostic is recorded. Load never raises into Archive/View rendering.

Unsupported / future schema versions are **rejected** (no silent accept). Migration requires an explicit migrator and a schema bump.

## Sanitisation (load and save)

- Drop unknown action IDs and unknown section IDs
- Deduplicate actions (catalogue order after first-seen set)
- Intersect each section’s `selected` with that section’s allowlist
- If a shown section’s configured menu is empty after sanitise (e.g. empty manual selection), restore that section’s built-in defaults into `selected`
- Empty custom `standard_menu` restores the built-in standard menu list

## Merge

Partial prefs merge onto `built_in_prefs()`: missing sections/actions receive current built-ins; valid known customisations are kept.

## Writes (Save and Restore built-ins)

Under process + file lock:

1. Read current bytes (or empty if missing)
2. Compare SHA-256 of those bytes to the draft’s `raw_file_revision`
3. On mismatch → conflict; do not write
4. On match → atomic write of a new schema-v1 envelope

Atomic rename alone is insufficient. **Restore built-ins** is a persisted CAS write with the same revision check as Save (optional timestamped `.bak.` copy under the same lock).

## Frozen identifiers (v1)

| Kind | IDs |
|------|-----|
| Actions | `open`, `transcribe`, `analyse`, `export`, `rename`, `delete` |
| Sections | `archive_notebook`, `view_notebook` |

Do not rename or remove these IDs after release without migration logic and a schema bump. Additive action IDs are allowed within schema v1 when catalogue, allowlists, and handlers stay closed.

## Capability freshness

Archive `NotebookSummary` is advisory for listing. Action availability (`has_pages`, project existence) is derived from **live** project state at strip resolve time, not from stale summary fields alone.
