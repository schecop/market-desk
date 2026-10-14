# Learning Journal

The trace of **what was built, why, and what was learned**: one folder per sprint, one page per task. Written during the work, not after. Re-read it whenever you come back after a break, or before explaining the project to someone. Self-test with the check questions on each page: the answers stay hidden until clicked.

| Sprint | Overview |
|---|---|
| 0 — Scaffold | [sprint-0/](sprint-0/index.md) |

## Adding pages
- **New sprint:** copy `_template-sprint.md` to `sprint-N/index.md`, and add it to the `nav` in `mkdocs.yml`.
- **New task:** copy `_template-task.md` to `sprint-N/NN-<slug>.md`, add it to the `nav` and to the sprint's task table.
- Preview with `make docs-serve`; `make docs-build` must pass (it fails on broken links and anchors).

## What goes where
| Record | Where | When |
|---|---|---|
| Where we are, next step | `PROGRESS.md` | end of every session |
| Decisions (with alternatives) | task page → Decisions (sprint-wide ones on the sprint overview) | when made |
| Lasting architectural decisions | `docs/adr/NNNN-*.md` + a row on the task page | when made |
| Concepts learned | task page → Concepts, one `###` each | when first met |
| Which file does what, and why | task page → Code map | when the file is created or changes role |
| Bugs, surprises | task page → Gotchas | when solved |
| Check questions and answers | task page → Check questions | after the task works |
| Guided exercise (what I did, what I got wrong) | task page → Guided exercise | when the exercise passes |
| Why a change was made | commit body + PR description | every commit / PR |
