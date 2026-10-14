---
tags:
  - github
  - ci
---

# 9. Branch protection

**Sprint 0** · **Date:** 2026-10-14 · **Plan item:** Branch protection on `main`: PR + green CI required

## What and why
A repository ruleset, `protect-main`, makes GitHub refuse any change to `main` that doesn't arrive through a pull request with both CI jobs green. Before this, "PRs with green CI, never push to `main`" was a habit; now the server enforces it, for the admin (me) too.

## Decisions
| Date | Decision | Why | Alternatives considered | ADR |
|---|---|---|---|---|
| 2026-10-14 | Repository ruleset instead of classic branch protection | GitHub's current system: rules can stack, visible in UI and API, new features land here | Classic branch protection rules (still work, no new features) | — |
| 2026-10-14 | Require a PR with 0 approvals | Solo repo: you can't approve your own PR, so 1 approval would block every merge; the PR still forces CI and a reviewable unit | 1 approval (blocks everything); no PR rule (direct pushes allowed) | — |
| 2026-10-14 | Required checks: `Lint, types and tests` and `Docker image builds`, not Docs' `Build site (strict)` | Docs is path-filtered: on a code-only PR it never reports, and a required check that never reports blocks the PR forever. Broken docs still can't reach the site: `deploy` needs a green build | Require all checks; make Docs always run and skip work inside the job | — |
| 2026-10-14 | Checks pinned to the GitHub Actions app (`integration_id: 15368`) | Only Actions can turn them green; otherwise anything able to write commit statuses could post a fake pass with the same name | Any source | — |
| 2026-10-14 | Branch must be up to date before merging (`strict`) | The checks must have run on what `main` will actually become, not on a stale base | Allow merging stale branches (two green PRs can still break `main` together) | — |
| 2026-10-14 | No bypass actors, admins included | One `git push origin main` by the admin would defeat the rule | Admin bypass for emergencies | — |
| 2026-10-14 | Block force pushes and deletion of `main` | History on `main` can't be rewritten or lost | Allow them | — |
| 2026-10-14 | Ruleset created by hand in the UI | Claude Code's permission check refused the `gh api` call that changes who can push: a change to access rules is the owner's to make | Grant Claude the permission | — |

## Concepts

### Server-side vs client-side enforcement
pre-commit hooks run on *my* machine: they can be skipped (`--no-verify`) or not installed. CI runs on GitHub but only *reports*: a red check doesn't stop a direct push to `main`. Branch protection is enforced by the server receiving the push, so it can't be skipped from a laptop. The three layers together: hooks are fast feedback, CI is the check, the ruleset makes the check mandatory.

### Rulesets
A named set of rules targeting branches (or tags) by pattern; `~DEFAULT_BRANCH` follows the default branch even if it's renamed. Enforcement is `active` or `disabled` (`evaluate`, a dry-run mode that only logs, isn't available on every plan). `bypass_actors` lists who may skip the rules: empty here.

### Required status checks are matched by name
A required check is identified by the **job `name:`** that reports it (what `gh pr checks` prints), optionally pinned to the app that must report it. Rename the job in the workflow and the required check never reports under the old name: every PR waits forever. Same failure as requiring a path-filtered check.

### "Up to date" before merging
Two PRs can each be green against an old `main` and still break it together. With the strict policy, a PR whose base is behind `main` must merge `main` in (the "Update branch" button) and pass again before it can merge.

## Code map
| File | What it does | Why it exists / why this way |
|---|---|---|
| *(GitHub setting)* ruleset `protect-main` | PR required, 2 required checks from GitHub Actions, up to date, no force push or deletion, no bypass | Lives in the repo settings, not in a file; read it with `gh api repos/schecop/market-desk/rulesets` |

## Gotchas
!!! bug "The rule I asked for doesn't match what the API returns"
    **Cause:** the UI adds defaults the JSON didn't set: `allowed_merge_methods` (merge, squash, rebase) and `require_extra_approval_for_unattributed_changes: true`.
    **Fix:** none needed so far; read the ruleset back after creating it.
    **Lesson:** always read a setting back after changing it; if a merge is blocked unexpectedly, check the extra defaults first.

## Check questions
??? question "Why not require Docs' `Build site (strict)` as well? Doesn't that let broken docs merge?"
    It's path-filtered, so a code-only PR never runs it, and a required check that never reports blocks the PR forever. Broken docs can merge, but can't reach the site: on `main`, `deploy` only runs after a green strict build, so the live site keeps the last good version and the red run on `main` says what to fix.

??? question "Someone renames the CI job `name: Lint, types and tests` to `name: Checks` and opens a PR. What do its checks show, and can it merge?"
    `Checks` goes green, but the required `Lint, types and tests` shows *Expected: waiting for status to be reported*, which never arrives, so the PR is blocked. The fix is to update the ruleset to require `Checks`, timed with the merge: earlier, it blocks every other open PR that still reports the old name; later, this PR can't merge. Better: treat required job names as a contract and don't rename them. The ruleset lives in GitHub's settings, not the repo, so nothing in the PR's diff warns you.

??? question "A help line reads `@echo make demo - one; two (three)`. What does `make help` print from Git Bash?"
    The lines before it print, then `syntax error near unexpected token '('` and make stops: `sh` parses the whole line before running any of it, so not even `make demo - one` is printed, and the help lines after it never run. From PowerShell, `cmd` prints the line as-is.

## Guided exercise
**Task (type):** shared by the `make help` fix and this task. 1: add `@echo make demo - one; two (three)` to `help`, predict and compare Git Bash vs PowerShell, remove it (break on purpose). 2: try `git push origin HEAD:main` from a throwaway branch and read GitHub's rejection (predict/verify). 3: predict what happens to a PR after a required job is renamed.

**Outcome:** predictions given and reviewed (2026-10-14); parts 1 and 2 were **not run** (I chose to move on), so the rejection message and the shell outputs weren't seen first-hand. Part 3 answered.

**What I got wrong:** called `(` a "subcommand" (it starts a *subshell*); didn't spot that `sh` parses the whole line first, so nothing on it prints; didn't explain why `sh` collapses the spaces (it splits the line into words on whitespace, and `echo` rejoins its arguments with single spaces). Part 3: right that it's blocked, but missed that the renamed check shows green while the old required one waits forever, and the timing problem of changing the ruleset.

**Lesson:** a required check is a contract by name with a setting that lives outside the repo; `sh` parses a line before running it.

!!! tip "To do when convenient"
    Run part 2 once to see GitHub's rejection (`GH013 ... Repository rule violations`) first-hand: it lists every rule the push breaks.

## Explain it in 2 minutes
`main` is protected by a repository ruleset, so GitHub refuses anything that doesn't come through a pull request with both CI jobs green: lint, types and tests, and the Docker build. It applies to me as admin too: no bypass, no force pushes, no deleting the branch. The branch must be up to date with `main` before merging, so the checks ran on what `main` will actually become, and the checks are pinned to GitHub Actions so nothing else can report them green. No approvals are required, because you can't approve your own PR. The docs build isn't required on purpose: it only runs when docs change, and a required check that never reports blocks a PR forever; broken docs still can't reach the site because deploy needs a green build. Together: pre-commit gives fast feedback, CI checks, and the ruleset makes the check mandatory.
