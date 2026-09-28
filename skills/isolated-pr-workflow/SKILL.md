---
name: isolated-pr-workflow
description: Run implementation work in an isolated git worktree, create a new feature branch from an up-to-date base branch, commit and push the result, capture browser screenshots or video evidence for user-visible changes, open a ready-for-review GitHub pull request through the repository's template/browser flow when required, then clean up the temporary local worktree. Use when the user asks for isolated worktree development, "new worktree branch off main", "open a PR with my GitHub template", "clean up the worktree", or similar end-to-end branch-to-PR workflows.
---

# Isolated PR Workflow

## Overview

Implement requested code changes in a temporary git worktree instead of the current checkout, publish them as a ready-for-review PR from a fresh feature branch, then remove the temporary worktree after the PR handoff is complete.

## Workflow

1. Read repository instructions before changing files:
   - Start with the nearest `AGENTS.md`.
   - Read contribution or PR workflow docs if present.
   - Follow repo-specific rules for base branch, fork remote, PR template usage, checks, and generated files.
2. Inspect the current repository state from the original checkout:
   - `git status --short --branch`
   - `git remote -v`
   - `git branch --show-current`
   - `gh auth status` when a GitHub PR will be opened.
3. Determine the base branch:
   - Use the branch named by the user when provided.
   - Otherwise prefer repository guidance.
   - Otherwise default to `main`.
4. Fetch and update the base branch without disturbing unrelated local work:
   - Fetch the upstream remote that owns the base branch.
   - Avoid destructive commands.
   - If the local base branch cannot be fast-forwarded cleanly, create the worktree from `origin/<base>` or the correct upstream tracking ref instead of rewriting local state.
5. Create an isolated worktree:
   - Use a branch name like `feat/<short-slug>` for features, `fix/<short-slug>` for bug fixes, or the repo's established convention.
   - Use a worktree path outside the main checkout, such as `../<repo>-worktrees/<branch-slug>` or another clearly temporary sibling path.
   - Create it from the fetched base ref:

```bash
git fetch <base-remote> <base-branch>
git worktree add -b <branch-name> <worktree-path> <base-remote>/<base-branch>
```

6. Do all implementation, formatting, and tests inside the worktree:
   - Change the shell working directory to the worktree before editing.
   - Re-read any nested `AGENTS.md` that applies to touched files.
   - Keep edits scoped to the user's request.
   - Run the repository's targeted verification for the touched area.
7. Verify the result in a real browser and capture PR-ready visual evidence:
   - Open the changed app, page, or workflow in an actual browser session before PR creation; use Chrome when available, otherwise use the Codex Browser surface available in the session.
   - Exercise the user-visible path that changed rather than relying only on static inspection.
   - Capture screenshots for static visual changes and a short video or screenshot sequence for interactions, animations, or multi-step workflows.
   - Use the captured evidence to fill the PR template's screenshots/videos section. For non-visual changes, write `N/A` with a short reason.
   - If browser verification or capture is blocked by environment, authentication, missing services, or unavailable hardware, record the blocker in the PR body and final response.
8. Review and commit only intended changes:
   - Inspect `git status --short` and `git diff`.
   - Stage paths explicitly; do not stage unrelated files.
   - Commit with a concise message matching repository style.
9. Push to the correct writable remote:
   - Identify whether the repository requires a fork remote.
   - Push to the user's fork when repo guidance says not to push directly to upstream.
   - Set upstream tracking for the feature branch.
10. Open the pull request:
   - Prefer the repository's required PR creation flow.
   - Open a ready-for-review PR by default; do not pass `--draft` unless the user or repository explicitly requests a draft PR.
   - When the user asks to use their filled-out GitHub template, or repository guidance requires template prefill/disclosures, use GitHub's browser PR flow:

```bash
gh pr create --web --base <base-branch> --head <owner>:<branch-name>
```

   - Use `--draft` only when the user or repo asks for a draft PR and the CLI/browser combination supports it.
   - If using `--web`, tell the user that GitHub opened the PR creation page and any remaining template fields, including visual artifacts that require manual upload, must be completed there.
11. Clean up the temporary worktree only after the work is safely committed and pushed:
    - Confirm the worktree has no uncommitted changes.
    - Confirm the branch has an upstream and no unpushed commits.
    - Return to the original checkout before removing the worktree.
    - Remove only the temporary worktree created for this task.

```bash
git -C <worktree-path> status --short --branch
git -C <worktree-path> rev-list --left-right --count @{u}...HEAD
git worktree remove <worktree-path>
```

## Guardrails

- Never remove a worktree that has uncommitted changes, untracked deliverables, or unpushed commits.
- Never delete or rewrite the user's original checkout to make this workflow succeed.
- Never use `git reset --hard`, `git checkout --`, or force-push unless the user explicitly asks for that specific destructive operation.
- If PR creation is blocked by authentication, missing fork permissions, or required browser interaction, stop after pushing the branch and report the exact branch, remote, and PR URL or command needed.
- If browser-based visual verification is impossible, do not invent screenshots or videos. Explain the blocker and whether the change is non-visual.
- If checks fail, fix them when the failure is in scope. If the failure is external or unrelated, report it clearly before PR cleanup decisions.

## Reporting

In the final response, include the branch name, worktree cleanup status, PR handoff status or URL, ready/draft status, browser screenshots or videos captured for the PR, and the checks that ran. If the PR was opened with `gh pr create --web`, state that the browser flow was used so the repository template could be filled in.
