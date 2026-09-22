# Agentic Staff

Agentic Staff makes one Jev decision for a Codex user request: use GPT-6 Sol or GPT-6 Astra for a delegated task.  Sol is the fallback when Jev or the TypeSafe key is unavailable.  The main Codex thread keeps its own model.

## Local setup

```sh
uv sync
cp .env.local.example .env.local
# Put a TypeSafe AI API key in .env.local.
uv run python agentic_staff.py "Investigate this difficult failure"
uv run pytest
uv run pre-commit install
```

`.env.local` stays outside Git.  The router sends the full request to TypeSafe AI and does not log it.  The key is read from `.env.local`; an existing `TYPESAFE_API_KEY` environment variable takes precedence.

## Codex registration later

The repo is currently local and inactive.  Codex does not discover agents or hooks inside a nested `~/.codex/agentic-staff` directory.  When ready, place or link this repo there, link `agents/routed_worker.toml` into `~/.codex/agents/`, and add this entry to `~/.codex/hooks.json` (merge it with any existing hooks):

```json
{
  "hooks": {
    "UserPromptSubmit": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "\"$HOME/.local/bin/uv\" run --project \"$HOME/.codex/agentic-staff\" python \"$HOME/.codex/agentic-staff/agentic_staff.py\" --hook",
            "timeout": 15
          }
        ]
      }
    ]
  }
}
```

Review and trust the new hook in Codex before use.  The hook reads the request, asks Jev for `sol` or `astra`, and instructs Codex to start the one `routed_worker` subagent with that model.  Codex custom agent files are TOML; `AGENTS.md` is an instruction file, not the custom agent format.

## Checks

```sh
uv run ruff check .
uv run ruff format --check .
uv run pytest
uv run pre-commit run --all-files
```
