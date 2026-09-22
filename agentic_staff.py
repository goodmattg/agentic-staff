"""Choose a Codex subagent model for one user request."""

import argparse
import json
import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from typesafe_sdk import Choice, TypeSafeClient

SOL = "gpt-6-sol"
ASTRA = "gpt-6-astra"
EFFORT = {SOL: "medium", ASTRA: "low"}


def choose_model(task: str) -> str:
    """Ask Jev for one model choice; use Sol if routing is unavailable."""
    load_dotenv(Path(__file__).with_name(".env.local"), override=False)
    if not task.strip() or not os.getenv("TYPESAFE_API_KEY"):
        return SOL

    try:
        with TypeSafeClient() as client:
            response = client.system_one(
                state={"task": task},
                questions={
                    "model": Choice(
                        instructions=(
                            "Choose the least capable Codex model that can complete this task well."
                        ),
                        criteria={
                            "sol": "Everyday, clear, or complex work within one focused task.",
                            "astra": "Hard multi-step work needing sustained judgment.",
                        },
                    )
                },
                timeout=8,
            )
        return {"sol": SOL, "astra": ASTRA}.get(response.choices["model"].choice, SOL)
    except Exception:
        return SOL


def hook_output(model: str) -> dict:
    """Build Codex's UserPromptSubmit hook response."""
    effort = EFFORT[model]
    return {
        "hookSpecificOutput": {
            "hookEventName": "UserPromptSubmit",
            "additionalContext": (
                "Delegate this user request to one routed_worker subagent with "
                f"model={model} and model_reasoning_effort={effort}. "
                "Wait for its result, then complete the response to the user."
            ),
        }
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("task", nargs="?", help="Request to route")
    parser.add_argument("--hook", action="store_true", help="Read a Codex hook event from stdin")
    args = parser.parse_args()

    if args.hook:
        try:
            event = json.load(sys.stdin)
            task = event.get("prompt", "") if isinstance(event, dict) else ""
        except json.JSONDecodeError:
            task = ""
        model = choose_model(task if isinstance(task, str) else "")
        print(json.dumps(hook_output(model)))
        return

    if not args.task:
        parser.error("provide a task or use --hook")
    print(choose_model(args.task))


if __name__ == "__main__":
    main()
