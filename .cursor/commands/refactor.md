# Refactor Assessment (# refactor-audit)

Analyze the codebase (or specified module) to identify where refactoring may be needed.
Do not change code. This is an assessment and planning pass only.

Run from the workspace root.

After completion, summarize findings and prioritize recommendations.

---

## 1. Complexity Review

- Identify long functions or large files.
- Flag deeply nested conditionals.
- Highlight complex branching logic.
- Detect high cognitive load sections.

---

## 2. Duplication & Repetition

- Identify repeated logic across modules.
- Detect similar helper functions that could be unified.
- Flag copy-paste patterns.

---

## 3. Structural Issues

- Identify mixed responsibilities within modules.
- Flag tight coupling between components.
- Detect violations of intended architecture (UI must not own OCR business rules; providers must not own prompts/persistence; core must not import Streamlit).
- Highlight unclear data flow across `domain` → `services` → `providers` / `persistence` / `export`.

---

## 4. Naming & Clarity

- Flag ambiguous or inconsistent naming.
- Identify misleading abstractions.
- Detect overly generic utility functions.

---

## 5. Test Coverage Gaps

- Identify core logic without sufficient test coverage.
- Highlight fragile areas that may benefit from refactor before extension.

---

## 6. Risk Assessment

- Identify high-risk files (large, central, frequently modified).
- Flag areas likely to cause regressions.
- Highlight modules that would block future features (including a future TranscriptX import adapter).

---

## Execution Rules

- Do not modify code.
- Do not propose full rewrites unless strictly necessary.
- Focus on incremental, realistic improvements.
- After completion, summarize:
  - Top 5 refactor candidates
  - Why they matter
  - Suggested order of refactor
  - Estimated risk level (low / medium / high)

If requested, convert findings into a stepwise refactor plan.
