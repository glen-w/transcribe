# Sample notebook

The shipped fixture lives in the package so Docker and editable installs both
see it: [`src/transcribe/samples/demo-notebook/`](../src/transcribe/samples/demo-notebook/).

**Workflow → New notebook → Open sample** copies those placeholder pages into
`TRANSCRIBE_PROJECTS_DIR` through the normal create + import path and seeds
page text so Analyse Quick works without OCR.
