Type: GUIDE
Authority: 0.9-1 unfamiliar-user testing protocol — does not own product sequencing (see ROADMAP) or runtime contracts

# 0.9-1 unfamiliar user testing

**Status:** planned — runs **after** the **0.9.0** package cut (U2 + I0–I6). Sequencing: [ROADMAP.md](../ROADMAP.md) [Path to 0.9.0 / 0.9-1 / 1.0](../ROADMAP.md#path-to-090--09-1--10----planned).

**Purpose:** Strangers (or deliberately unfamiliar testers) complete a first successful notebook using only hosted/README docs — not contracts — so findings can harden Transcribe before **1.0** and leave an additive-ready foundation for After 1.0 autobiography work.

This is **not** an infrastructure track (not I7). It is **not** autobiography testing.

---

## Inputs

- Tagged **0.9.0** (or a 0.9.x patch that includes U2 sample + first-run docs)
- Hosted guide from infrastructure **I4/I5** (or README + `docs/user_guide.md` if Pages is not yet public — prefer hosted)
- Sample notebook path from usability **U2.2**

---

## Scripted happy path (15–30 minutes)

Testers use product docs only. Observers may note blockers; do not coach contract vocabulary.

1. **Install** — follow the first-run install path (local venv or Docker as documented).
2. **Open sample** (or import a few of their own scans if they prefer).
3. **Confirm Ollama** — Home / Diagnostics one-line health; pull or select a vision model if needed.
4. **Transcribe** — run OCR on the sample (or skip if sample is pre-seeded with text for offline Analyse).
5. **Review** — open Review; notice dates / empty text if present; make one edit or approve one date if suggested.
6. **Reading** — open Reading; flip a few pages.
7. **Analyse Quick** — run Quick (deterministic modules; LLM optional).
8. **Overview / Themes / Mood** — glance at View consume pages; note empty or “needs model” states.
9. **Export** — export Markdown or `transcribe.notebook` JSON; notice revision if shown.
10. **Backup** — create a workspace backup ZIP via Settings or CLI; optionally verify.

Then **5–10 minutes free exploration** (Search, Archive, Places, Settings — whatever they try).

---

## Capture

File issues (or a single testing notes doc) for:

| Area | Examples |
|-------|----------|
| Install | Path mounts, port **8510**, Docker/`extra_hosts`, UID/GID, missing Ollama |
| Models | Vision vs text confusion; unverified identity; hang/timeout honesty |
| Review / dates | Unapproved dates on timeline; edit vs Prefer/Promote; empty OCR |
| Analyse | Empty states; “needs text model”; status strip clarity |
| Navigation | Library → Reading; Search jump; Home recent list |
| Backup / restore | Confidence; size; restore refuse messaging |
| Docs | Gaps between README and first success |

Also note anything that would later block “life around a page” (Reading centrality, Search/Archive date filters, jump-to-page) — **without** asking testers to import WhatsApp or photo libraries.

---

## Explicitly out of script

- WhatsApp / Telegram / photo-context imports
- Person identity store, Slices, Autobiography view, reconstruction chat
- Contract reading, doctor deep hashing as a required step
- Live multipass fine-tune export (optional free exploration only)

---

## Outputs and exit

| Output | Owner |
|--------|--------|
| Issue list + severity | Tester / maintainer |
| Fix train on **0.9.x** | Maintainers |
| Go/no-go note for **1.0** | Maintainer |
| Foundation checklist sign-off | [ROADMAP Path to 0.9.0](../ROADMAP.md#path-to-090--09-1--10----planned) Track C |

**0.9-1 → 1.0 exit:** critical install/OCR/review/export/backup issues closed or accepted in [known_limitations.md](../known_limitations.md); foundation checklist complete; [PRODUCT.md](../PRODUCT.md) still page-first.

---

## Related

- [ROADMAP.md](../ROADMAP.md) — Path to 0.9.0 / 0.9-1 / 1.0; After 1.0 (gated)
- [usability_wave_plan.md](../usability_wave_plan.md) — U2 sample + first-run docs
- [infrastructure_wave_0_9_plan.md](../infrastructure_wave_0_9_plan.md) — I0–I6; 0.9.0 cut
- [backup_and_restore.md](../backup_and_restore.md) — backup/verify/restore
- [known_limitations.md](../known_limitations.md) — honesty page
