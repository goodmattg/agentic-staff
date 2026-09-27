# Agentic Staff

WRONG INVOCIATION PATTERN: We must support entry here through either the ChatGPT app, Codex CLI, claude cli, or pi harness. The idea is as I'm entering software development specific queries, I want to route those through this pathway.

## Local setup

```sh
uv sync
cp .env.local.example .env.local
# Put a TypeSafe AI API key in .env.local.
uv run python agentic_staff.py "Investigate this difficult failure"
uv run pytest
uv run pre-commit install
```

`.env.local` stays outside Git. The router sends the full request to TypeSafe AI and does not log it. The key is read from `.env.local`; an existing `TYPESAFE_API_KEY` environment variable takes precedence.

## Checks

```sh
uv run ruff check .
uv run ruff format --check .
uv run pytest
uv run pre-commit run --all-files
```
