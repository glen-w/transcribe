# Export Exemplars (# export-exemplars)

Find the 10 most representative substantive functional-code files in the workspace about a given topic and copy them (flat, no subfolders) into a new folder on the Desktop named after the topic. If no topic is given, use the plan or topic currently under discussion.

**Usage:** `/export-exemplars [topic]`
Examples:
- `export-exemplars docker setup` → finds 10 files best showing Docker setup and copies them to `~/Desktop/docker setup/`.
- `export-exemplars` (no topic) → infers the topic from the plan or discussion currently in focus and exports for that.

Execute from the workspace root. The topic is everything after "export-exemplars" in the user's message, when present.

---

## 1. Parse the topic

- If the user supplied a topic phrase (e.g. "docker setup", "authentication", "API rate limiting"), use that exactly.
- If the topic is empty or missing, **do not ask** — infer it from the current conversation:
  1. Prefer the active/confirmed plan title or plan file name under discussion (e.g. Cursor plan for the task being implemented).
  2. Otherwise use the main topic of the latest substantive thread (feature, bugfix, or refactor under discussion).
  3. Derive a short Desktop folder name from that plan/topic (plain words, spaces allowed; e.g. "per-segment audio playback").
  4. Briefly state the inferred topic in the summary so the user can see what was assumed.
- The destination folder name is exactly this topic (with spaces allowed): `~/Desktop/<topic>/`.
- Normalize for filesystem: create the folder with the topic as given; avoid characters that are invalid in folder names.

---

## 2. Find representative files

- Use **semantic search** (and optionally grep for filenames) to find files that best illustrate the topic.
- Run multiple targeted searches if needed (e.g. "Where is Docker configured?" "How is the Docker image built?" "docker-compose setup") to get good coverage.
- From the combined results, **choose the 10 most representative files**:
  - Include only substantive functional code that directly implements the topic.
  - Exclude all test-related files and directories, including unit, integration, end-to-end, snapshot, fixture, mock, stub, and test-helper code. Treat common patterns such as `tests/`, `test/`, `__tests__/`, `spec/`, `*_test.*`, `test_*.*`, and `*.spec.*` as test-related.
  - Exclude documentation, examples, demos, generated code, vendored code, binary files, lockfiles, and standalone data or fixture files.
  - Exclude configuration and infrastructure files unless they contain the substantive functional implementation requested by the topic.
  - Do not select a test file even when it is the clearest or only match; copy fewer than 10 files instead.
- If fewer than 10 clearly relevant files exist, copy only those; do not pad with unrelated files.

---

## 3. Copy to Desktop (flat layout)

- Create the folder: `~/Desktop/<topic>/` (e.g. `~/Desktop/docker setup/`).
- Copy each of the 10 (or fewer) files into this folder **without** preserving subfolder structure.
- **Filenames:** use the file's basename (e.g. `Dockerfile`, `docker-compose.yml`). If two files have the same basename, disambiguate (e.g. `README.md` and `README-docs.md`, or `config-1.yaml` and `config-2.yaml`) so nothing is overwritten.
- Use `cp` (or equivalent) to copy; do not move or delete originals.
- If the destination folder already exists, add files into it and disambiguate names if needed; do not delete existing contents unless the user asked to replace.

---

## 4. Summarize

- List the 10 (or fewer) files that were copied and their original paths.
- Give the user the path to the new folder: `~/Desktop/<topic>/`.

---

## Execution rules

- Only copy; never delete or modify the originals.
- Never export test-related files; every selected source file must contain substantive functional implementation.
- Resolve the Desktop path appropriately (e.g. `$HOME/Desktop` or `~/Desktop` on macOS).
- If the topic is empty or missing, infer from the current plan/discussion (see §1); only ask the user if there is no usable plan or discussion context to infer from.
