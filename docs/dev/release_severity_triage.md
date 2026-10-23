# Release severity triage

**Status:** published rules for 0.9.x / 1.0  
**Linked from:** [release_governance.md](release_governance.md), [ROADMAP.md](../ROADMAP.md)

Without explicit severity, hardening expands indefinitely because every
imperfection looks equally important. Apply these rules when triaging findings
before a **0.9.0** or **1.0** tag.

| Severity | Definition | Tag action |
|----------|------------|------------|
| **Release blocker** | Data loss; unsafe deletion; corrupt notebooks or exports; broken supported install; incorrect run truth; security/privacy failure | Must fix before the tag; no known-limitation escape |
| **Must fix** | Principal journey broken (import → transcribe or pre-seeded text → review → export → backup); misleading prominent analysis; unusable error state; first-run docs cannot complete a supported workflow | Must fix before **1.0**. **0.9.0** still keys off U2 + I6, not this pack |
| **May ship as known limitation** | Optional module failure; missing optional extra (BERTopic); unsupported language/model/platform; specialist UI friction; OCR model quality; non-critical performance | Document in [known_limitations.md](../known_limitations.md); do not block 1.0 |
| **Post-1.0** | Aesthetic refactors; new analysis modules; specialist convenience; non-supported configurations; autobiography | Explicitly out of scope for the freeze |

## Gate rules

- Tag each finding with one severity before scheduling work.
- Known limitations must be listed when shipping under that class.
- **0.9.0** still keys off U2 (sample + first-run docs) and I0–I6. This severity pack joins the **1.0** checklist in [release_governance.md](release_governance.md).
- RC / 1.0 entry requires zero open **release blockers** and zero open **must-fix** items.

Ollama vision/text model quality is a **known limitation**, not a blocker, unless a supported install path crashes or silently corrupts pages.
