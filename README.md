# Agentic Staff

Explicit orchestration for native coding agents in Claude, Codex, Pi, and Grok.
Invoke `$staff` or `/staff` to run the workflow. Ordinary requests and followups
stay with the base model, including the first message in a new chat.

The skill is a thin bridge to [staff_graph.py](staff_graph.py). Pydantic Graph
executes the classification branch, phase transitions, review loop, and completion
gates. The host model performs each requested tool or agent action and submits its
result. The OpenAI Decisions API supplies classification, relevance, review filtering,
and confidence using `gpt-6-luna`.

## Install

```sh
uv sync --locked
# If .env.local does not exist, copy .env.local.example and set OPENAI_API_KEY.
uv run --locked python install.py
```

The installer links the shared skills into Claude, Codex, and Grok, registers the
Pi package, updates the managed instruction blocks, and removes legacy staff prompt
hooks. Other hooks and user instructions remain intact. Codex's skill policy and
Claude/Pi's skill frontmatter disable implicit invocation. Start a new session to
refresh cached skill metadata.

`pydantic-graph==2.51.0` is pinned, and `uv.lock` pins its dependencies. The graph
runs locally without a Pydantic account or cloud service. Graph telemetry is off.
Native coding-agent providers retain their existing authentication requirements.
Decisions use a separate OpenAI Platform API key; signing into a native coding
agent does not configure that key.

## Decision configuration

Set `OPENAI_API_KEY` in your shell or the repository's gitignored `.env.local`.
Existing environment variables take precedence. When migrating an existing install,
replace `TYPESAFE_API_KEY` with `OPENAI_API_KEY` in `.env.local`, then run
`uv sync --locked`. Jev and `typesafe-sdk` are no longer used. The installer does
not rewrite your existing credentials.

The decision layer uses `POST /v1/decisions` through the OpenAI Python SDK
(`>=3.26.0,<4`, pinned in `uv.lock`). The endpoint currently supports `gpt-6-luna`
and is in public beta. See the [Decisions guide](https://developers.openai.com/api/docs/guides/decisions)
and [API reference](https://developers.openai.com/api/reference/resources/decisions/methods/create).
Requests send the task and, depending on the phase, conversation excerpts, review
findings, or execution/testing evidence. Native planning and execution models are
still selected by the local severity table.

Categorical decisions use `choice`; yes/no decisions use `predicate`. Scope detection
uses a probability threshold of `0.65`; relevance, inconsequential finding removal,
severity flags, and confident choices use `0.8`. These retain the old thresholds;
they have not been calibrated for parity with Jev. Each finding question identifies
its zero-based input index. Requests with more than 200 questions are split into
batches; refused, missing, or invalid answers remain unknown independently.

Missing query-kind answers use the existing keyword heuristic. Missing ticket
fields use the existing defaults: chore type, unknown scope, and unset flags.
Without a key, change requests therefore become low-severity chores with unknown
scope. Unknown relevance is excluded, unknown findings are retained, and unknown
final confidence stays low. API failures log only the exception class to stderr. SDK
retries are disabled: requests time out after 8 seconds for query kind, relevance,
and final confidence, or 20 seconds per batch for ticket details and finding filters.

## Workflow

In Codex, invoke `$staff-graph` to generate a fresh horizontal diagram and a
clickable localhost URL. Clients with image display support also show the PNG
inline; Codex CLI gets a PNG file link.
The explicit-only skill imports the current Python graph and renders it locally;
it does not start a staff run. The installer adds it to `~/.codex/skills`.

The browser view contains the diagram and zoom controls. To generate it from the
executable graph and open it:

```sh
uv run --locked python render_graph.py --open
```

Rendering uses Mermaid CLI (`mmdc`). `--serve` prints a clickable URL; `--open`
also opens it. The viewer binds only to `127.0.0.1` and stops after an hour without
requests. The generated HTML also works as a standalone local file.
The renderer was verified with `@mermaid-js/mermaid-cli@11.16.0` and local Chrome.
Artifacts (`workflow.html`, `.svg`, `.png`, and `.mmd`) go into a new temporary
directory by default. Use `--output-dir PATH` to choose another location.
Generated diagrams are not checked in; each invocation uses the current graph.
To print Mermaid directly:

```sh
skills/staff/scripts/staff diagram
```

A knowledge question returns directly to the parent. A code change requests
context, planning, execution, five independent reviews, and PR finalization.
The parent and planning agents stay in normal execution mode. The planning phase
returns an implementation plan without entering the harness's Plan mode.
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
- `agentic_staff.py`: OpenAI decisions, severity rules, model selection, and testing policy.
- `skills/staff/SKILL.md`: host transport shim.
- `skills/staff/references/reviewers.md`: isolated reviewer prompts.
- `install.py`: local harness installation and legacy hook migration.

### Updating a local Codex installation

The installer symlinks `~/.codex/skills/staff`, `staff-graph`, and
`isolated-pr-workflow` to this checkout. The staff launcher resolves that link and
starts a fresh Python process using `uv run --locked --project <checkout>` on every
command. Python and script changes in the linked checkout apply on the next command;
no reinstall is needed. Dependency changes require an updated `uv.lock`; `uv run`
syncs automatically, or run `uv sync --locked` explicitly.

After changing skill instructions or references, start a fresh Codex session to
avoid reusing instructions already loaded into a conversation. Rerun
`uv run --locked python install.py` after changing `hosts/sticky.md` or the generated
agent model/effort definitions in `agentic_staff.py`: the installer copies those
into `~/.codex/AGENTS.md` and `~/.codex/agents/*.toml`. Start a fresh session afterward.
Also rerun the installer if the checkout moves.

Only edits in the linked checkout are active. A separate PR worktree does not
change the installed skill. After merging, update the linked checkout; avoid
installing from a temporary worktree that will later be removed. Installs are local
to each machine. To inspect the current link, run `ls -ld ~/.codex/skills/staff`.

### Verification

```sh
uv run --locked ruff check .
uv run --locked ruff format --check .
uv run --locked pytest
```

The default test suite makes no paid API calls. Unit and graph tests cover decision
mapping, thresholds, API failures, refusals, batching, all four harness payloads,
persistent resume, stale callbacks, loop limits, finalization gates, explicit entry,
and installation migration. CLI end-to-end tests run fresh Python processes through
the real graph, SQLite store, and OpenAI SDK against a local HTTP fixture. They
exercise ready and draft completion, retained material findings, refused confidence,
and the knowledge-question branch. Native agent results and PR actions are synthetic;
tests do not launch coding agents or publish test PRs.

To additionally test the real OpenAI endpoint with synthetic evidence (incurs API
usage; requires `OPENAI_API_KEY` and access to `gpt-6-luna`):

```sh
STAFF_LIVE_DECISIONS=1 uv run --locked pytest tests/test_decisions_live.py -v
```

The live checks exercise all four decision functions and a complete CLI/checkpoint
roundtrip with real decisions and synthetic host results. They verify a material
finding keeps the final PR state draft. They are smoke tests, not a calibration
study or a test of native coding-agent execution.
