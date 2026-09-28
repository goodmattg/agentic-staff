---
name: staff
description: >
  Run the Python staff graph when the user explicitly invokes /staff, $staff,
  or the harness's staff skill command. The graph directs native coding agents.
  Ordinary software requests and followups use the base model without this skill.
disable-model-invocation: true
---

# Staff

This is a transport shim. Use it only for an explicit invocation, not a quoted or
discussed command. The parent stays in this chat. Python owns the workflow.

1. Write the current request verbatim to a temporary UTF-8 file. Call the executable
   `scripts/staff` next to this skill (it resolves symlinks and pins dependencies):

   ```sh
   "<skill>/scripts/staff" start --explicit --harness codex --workspace "<repo>" --query-file "<request-file>"
   ```

   Use the actual harness: `claude`, `codex`, `pi`, or `grok`.
2. Keep the returned `run_id`. Execute only its pending `action`, following its
   `instructions` and `payload`. Use native harness tools to run requested agents.
   Keep the parent and agents in normal execution mode, including the planning
   phase. Planning returns an implementation plan; do not enter Plan mode or
   request a mode switch.
   Write their actual result as JSON matching `result_schema` to a temporary file:

   ```sh
   "<skill>/scripts/staff" advance --run "<run_id>" --action "<action.id>" --result-file "<result-file>"
   ```

   Repeat until the graph returns `complete`. Do not choose phases, models, loop
   counts, or confidence yourself. Do not start another run for the same invocation.
3. If an action cannot complete, use `block --run <id> --action <id> --reason <reason>`
   and report the blocker. Never fabricate results. To recover a lost tool response
   or resume an interrupted run, use `status --run <id>` before repeating any work.
   If the user cancels, use `cancel --run <id>`; cancellation does not undo tool actions.
4. On `complete`, follow `reply_instruction` and stop. Later messages use the base
   model directly. Preserve an unfinished run ID in compaction summaries.
