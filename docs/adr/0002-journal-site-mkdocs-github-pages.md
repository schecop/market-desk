# ADR-0002: Publish the learning journal as a site (MkDocs Material on GitHub Pages)

- **Date:** 2026-10-12
- **Status:** accepted
- **Sprint:** 0

## Context
The learning journal (`docs/journal/`) is one long Markdown file per sprint, with tables for decisions, concepts, code map, gotchas and exercises. It is complete but hard to consult: no search, no navigation by task, and the check questions sit next to their answers. The goal is a visual, precise study journal to look back on when recalling what was built and what to remember for future projects. Constraints: no extra cost, no second copy of the content to keep in sync, and it must stay part of the normal workflow (the *Record* step).

## Options considered
1. **MkDocs Material, built from `docs/journal/`, deployed to GitHub Pages by a workflow**: one source (the Markdown already written in the *Record* step); search, dark mode, tags, admonitions, collapsible answers for self-testing, Mermaid diagrams; free; another GitHub Actions workflow right after the CI task. Cons: ~1.5h in Sprint 0; the journal moves from one file per sprint to one page per task; one more dependency (docs only).
2. **Keep plain Markdown on GitHub**: zero work. Cons: no search across sprints, no self-test mode, long tables that are hard to read.
3. **A separate page outside the repo** (e.g. a hosted notes page): richer interactivity. Cons: a second source of truth that drifts from the repo, and not versioned with the code it describes.

## Decision
Option 1, as a Sprint 0 task right after the GitHub Actions CI task. The site is public, like the repo, and reads as a personal learning journal.

## Consequences
- Sprint 0 grows from ~5h to ~6.5h; total effort ~89h → ~90.5h; checkpoint ~39h → ~40.5h.
- From that task on, the *Record* step writes one page per task (what and why, concepts, check questions with hidden answers, guided exercise, mistakes → lessons, "explain it in 2 minutes"), plus cross-sprint review pages (concepts, questions, gotchas, commands).
- Existing entries in `docs/journal/sprint-0.md` are migrated to the new layout in that task; until then they keep being written there.
- Later ADR numbers in `docs/PLAN.md` shift by one (client design is now ADR-0003, through deployment design as ADR-0006).
- `docs/PLAN.md` sections 5, 7 and 8 updated.
- *Added 2026-10-14:* MkDocs 2.0 drops the plugin and theme systems Material depends on, with no migration path ([Material team's analysis](https://squidfunk.github.io/mkdocs-material/blog/2026/02/18/mkdocs-2.0/)). The `docs` group pins `mkdocs>=1.6,<2` so an upgrade can't break the site. If MkDocs 1.x stops being viable, the content (plain Markdown) is unaffected; only the build tool changes, e.g. to Zensical, the Material team's successor, which reads `mkdocs.yml`.
