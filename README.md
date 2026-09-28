# Agentic Staff

Explicit orchestration for native coding agents in Claude, Codex, Pi, and Grok.
Invoke `$staff` or `/staff` to run the workflow. Ordinary requests and followups
stay with the base model, including the first message in a new chat.

The skill is a thin bridge to [staff_graph.py](staff_graph.py). Pydantic Graph
executes the classification branch, phase transitions, review loop, and completion
gates. The host model performs each requested tool or agent action and submits its
result. Jev still supplies classification, relevance, review filtering, and confidence.

## Install

```sh
uv sync --locked
# If .env.local does not exist, copy .env.local.example and configure Jev.
uv run --locked python install.py
```

The installer links the shared skills into Claude, Codex, and Grok, registers the
Pi package, updates the managed instruction blocks, and removes legacy staff prompt
hooks. Other hooks and user instructions remain intact. Codex's skill policy and
Claude/Pi's skill frontmatter disable implicit invocation. Start a new session to
refresh cached skill metadata.

`pydantic-graph==2.51.0` is pinned, and `uv.lock` pins its dependencies. The graph
runs locally without a Pydantic account or cloud service. Graph telemetry is off.
Native agent providers and Jev retain their existing authentication requirements.

## Workflow

In Codex, invoke `$staff-graph` to generate a fresh PNG without progress narration.
Clients with image display support show it inline; Codex CLI gets PNG and HTML links.
The explicit-only skill imports the current Python graph and renders it locally;
it does not start a staff run. The installer adds it to `~/.codex/skills`.

[Open the browser view](docs/workflow.html) for a rendered graph with zoom controls.
It is a standalone local file. To regenerate it from the executable graph and open it:

```sh
uv run --locked python render_graph.py --open
```

Rendering uses Mermaid CLI (`mmdc`); the generated view requires no server or account.
The renderer was verified with `@mermaid-js/mermaid-cli@11.16.0` and local Chrome.
It also writes `workflow.png` and `workflow.mmd`. Use `--output-dir PATH` to
generate all artifacts outside the repository.
[SVG image](docs/workflow.svg) · [Mermaid source](docs/workflow.md).
To print Mermaid directly:

```sh
skills/staff/scripts/staff diagram
```

A knowledge question returns directly to the parent. A code change requests
context, planning, execution, five independent reviews, and PR finalization.
Kept review findings cause another pass up to the ticket's loop cap. An empty
review ends the loop early. Unresolved findings force low confidence. High
confidence requires ready PR confirmation and worktree removal; low confidence
keeps the PR draft and retains the worktree.

The graph yields at `AwaitHost` because native harness tools belong to the current
chat. The shim executes those actions using the selected native agents. Python
does not replace their reasoning, tools, or execution environment. The graph checks
the submitted evidence and sequencing; the host remains responsible for reporting
truthful tool results.

## Graph interface

```sh
# Only explicit invocation creates a run; without --explicit this returns direct.
skills/staff/scripts/staff start --explicit --harness codex \
  --workspace /path/to/repo --query-file /tmp/staff-request.txt

# Show the checkpoint without repeating any agent work.
skills/staff/scripts/staff status --run RUN_ID

# Submit actual results matching the pending action's result_schema.
skills/staff/scripts/staff advance --run RUN_ID --action ACTION_ID \
  --result-file /tmp/staff-result.json

# Preserve the pending action when execution cannot proceed.
skills/staff/scripts/staff block --run RUN_ID --action ACTION_ID --reason 'Missing access'

# On user cancellation; this does not reverse external actions.
skills/staff/scripts/staff cancel --run RUN_ID
```

Each response contains a run ID, status, and pending action or final reply
instruction. Pending actions include their input, host instructions, and JSON
result schema. The graph rejects incorrect action IDs, incomplete review panels,
PR changes during revisions, and finalization inconsistent with confidence.

Checkpoints and action history live in
`${XDG_STATE_HOME:-~/.local/state}/agentic-staff/runs.sqlite3`. Use the global
`--state-dir PATH` option before a command to select another store. Accepted results
and the next pending action are saved atomically. If a tool response is lost, call
`status` before repeating any external action. A new explicit invocation gets a new
run ID; it does not reactivate or overwrite a previous run.

## Development

- `staff_graph.py`: executable nodes, result schemas, checkpoint store, and CLI.
- `agentic_staff.py`: Jev decisions, severity rules, model selection, and testing policy.
- `skills/staff/SKILL.md`: host transport shim.
- `skills/staff/references/reviewers.md`: isolated reviewer prompts.
- `install.py`: local harness installation and legacy hook migration.

```sh
uv run --locked ruff check .
uv run --locked ruff format --check .
uv run --locked pytest
```

Tests run the real graph with substituted Jev decisions and simulated native-agent
results. They cover all four harness payloads, persistent resume, stale callbacks,
loop limits, finalization gates, explicit entry, and installation migration. They
do not launch paid agents or publish test PRs.
