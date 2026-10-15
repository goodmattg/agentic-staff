"""OpenAI decisions and model policy used by the explicit staff graph."""

import argparse
import json
import logging
import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from openai import APIError, OpenAI

SOL = "gpt-6-sol"
ASTRA = "gpt-6-astra"
DECISION_MODEL = "gpt-6-luna"
QUESTION_LIMIT = 200
LOGGER = logging.getLogger(__name__)
HIGH = 0.8
MODERATE = 0.65
HARNESSES = ("claude", "codex", "pi", "grok")

PLANNING = {
    "low": {"model": ASTRA, "effort": "medium", "agent": "staff_plan_low"},
    "medium": {"model": ASTRA, "effort": "high", "agent": "staff_plan_medium"},
    "high": {"model": ASTRA, "effort": "xhigh", "agent": "staff_plan_high"},
    "critical": {"model": ASTRA, "effort": "xhigh", "agent": "staff_plan_critical"},
}
EXECUTION = {
    "low": {"model": SOL, "effort": "medium", "agent": "staff_exec_low"},
    "medium": {"model": SOL, "effort": "high", "agent": "staff_exec_medium"},
    "high": {"model": SOL, "effort": "high", "agent": "staff_exec_high"},
    "critical": {"model": SOL, "effort": "xhigh", "agent": "staff_exec_critical"},
}
MAX_LOOPS = {"low": 1, "medium": 2, "high": 3, "critical": 3}
TESTING = {
    "ux": "No retained tests.",
    "infra-bug": (
        "Dry-run the infra change if possible. No unit tests. End-to-end test after execution."
    ),
    "infra-change": (
        "Dry-run the infra change if possible. No unit tests. End-to-end test after execution."
    ),
    "backend-bug": (
        "Modify an existing unit test when coverage exists, otherwise add one. "
        "End-to-end test the UI this backend touches, or its busiest path if it has no UI."
    ),
    "frontend-bug": "End-to-end test the frontend feature.",
    "full-stack-bug": (
        "Modify an existing unit test when coverage exists, otherwise add one. "
        "End-to-end test the busiest full-stack path."
    ),
    "feature-ux-backend": "Add backend unit tests. End-to-end test the primary operator path.",
    "feature-ux-backend-infra": (
        "Add backend unit tests. End-to-end test the primary operator path."
    ),
    "default": "No retained unit tests unless the request names a path to test.",
    "later": (
        "No layer was sure from the request. Read the code the change touches, "
        "then test the layer you find. Do not skip tests only because the request named no layer."
    ),
}


def yes_no(yes: str, no: str) -> dict[str, str]:
    return {"true": yes, "false": no}


def choice_question(*, instructions: str, criteria: dict[str, str]) -> dict:
    return {
        "type": "choice",
        "instructions": instructions,
        "choices": [
            {"value": value, "description": description} for value, description in criteria.items()
        ],
    }


def predicate_question(*, instructions: str, criteria: dict[str, str]) -> dict:
    return {
        "type": "predicate",
        "instructions": f"{instructions}\nTrue: {criteria['true']}\nFalse: {criteria['false']}",
    }


def load_env() -> None:
    load_dotenv(Path(__file__).with_name(".env.local"), override=False)


def probability(value) -> float | None:
    if isinstance(value, (int, float)) and not isinstance(value, bool) and 0 <= value <= 1:
        return float(value)
    return None


def ask(state: dict, questions: dict[str, dict], timeout: int = 20) -> dict | None:
    """Return usable answers by name; failed batches and refused answers stay unknown."""
    load_env()
    if not os.getenv("OPENAI_API_KEY") or not questions:
        return None
    answers = {}
    items = list(questions.items())
    # Disable SDK retries so a failing service does not multiply the phase timeout.
    with OpenAI(timeout=timeout, max_retries=0) as client:
        for offset in range(0, len(items), QUESTION_LIMIT):
            batch = dict(items[offset : offset + QUESTION_LIMIT])
            try:
                response = client.decisions.create(
                    model=DECISION_MODEL,
                    input=json.dumps(state),
                    questions=[{**question, "name": name} for name, question in batch.items()],
                )
            except APIError as exc:
                # Do not print API error bodies, which can include request data.
                LOGGER.warning(
                    "Decisions API request failed (%s); using fallback", type(exc).__name__
                )
                continue
            seen = set()
            for answer in getattr(response, "answers", None) or []:
                name = getattr(answer, "name", None)
                if not isinstance(name, str) or name not in batch:
                    continue
                if name in seen:
                    answers.pop(name, None)
                    continue
                seen.add(name)
                question = batch[name]
                if getattr(answer, "type", None) != question["type"]:
                    continue
                if answer.type == "predicate":
                    score = probability(getattr(answer, "probability", None))
                    if score is not None:
                        answers[name] = {"probability": score}
                elif answer.type == "choice":
                    label = getattr(answer, "choice", None)
                    score = probability(getattr(answer, "confidence", None))
                    if score is not None and any(
                        label == option["value"] for option in question["choices"]
                    ):
                        answers[name] = {"choice": label, "confidence": score}
    return answers


def choice_label(response, name: str) -> str | None:
    return (response or {}).get(name, {}).get("choice")


def choice_confident(response, name: str, threshold: float = HIGH) -> str | None:
    answer = (response or {}).get(name, {})
    if answer.get("confidence", 0) < threshold:
        return None
    return answer.get("choice")


def predicate_score(response, name: str) -> float | None:
    return (response or {}).get(name, {}).get("probability")


def is_yes(response, name: str, threshold: float) -> bool:
    score = predicate_score(response, name)
    return score is not None and score >= threshold


def heuristic_kind(task: str) -> str:
    text = task.lower()
    change_words = (
        "fix",
        "implement",
        "add ",
        "change",
        "refactor",
        "bug",
        "deploy",
        "upgrade",
        "pr ",
    )
    if any(word in text for word in change_words):
        return "ccr"
    return "kq"


def severity(ticket_type: str, scopes: list[str], flags: dict, explicit: str | None) -> str:
    """Escalate from the planning table. An explicit severity wins."""
    if explicit in MAX_LOOPS:
        return explicit
    count = len(scopes)
    if ticket_type in {"chore", "experiment"}:
        return "low"
    if ticket_type == "bug":
        if flags.get("bug_latent") and flags.get("bug_unlikely"):
            return "low"
        if flags.get("bug_latent"):
            return "medium"
        if flags.get("bug_live") and flags.get("bug_unlikely"):
            return "high"
        return "critical"
    if ticket_type == "feature":
        if flags.get("feature_uncoupled") and count == 1:
            return "low"
        if flags.get("feature_uncoupled") and count <= 2:
            return "medium"
        if flags.get("feature_uncoupled"):
            return "high"
    return "critical"


def testing_id(ticket_type: str, scopes: list[str]) -> str:
    if not scopes:
        return "later"
    scope_set = set(scopes)
    infra = bool(scope_set & {"ci-cd", "cloud-infra"})
    frontend = "frontend" in scope_set
    backend = "backend" in scope_set
    if ticket_type == "bug" and infra and not frontend and not backend:
        return "infra-bug"
    if ticket_type != "bug" and infra and not frontend and not backend:
        return "infra-change"
    if ticket_type == "bug" and frontend and backend:
        return "full-stack-bug"
    if ticket_type == "bug" and backend:
        return "backend-bug"
    if ticket_type == "bug" and frontend:
        return "frontend-bug"
    if ticket_type == "feature" and frontend and backend and infra:
        return "feature-ux-backend-infra"
    if ticket_type == "feature" and frontend and backend:
        return "feature-ux-backend"
    if frontend and not backend:
        return "ux"
    return "default"


def _agent_toml(name: str, description: str, model: str, effort: str, instructions: str) -> str:
    return (
        f'name = "{name}"\n'
        f'description = "{description}"\n'
        f'model = "{model}"\n'
        f'model_reasoning_effort = "{effort}"\n'
        'developer_instructions = """\n'
        f"{instructions.strip()}\n"
        '"""\n'
    )


def codex_agent_files() -> dict[str, str]:
    """Codex agent files that pin the planning and execution model table."""
    files: dict[str, str] = {}
    for severity, spec in PLANNING.items():
        files[spec["agent"]] = _agent_toml(
            spec["agent"],
            f"Staff planning worker for {severity} severity.",
            spec["model"],
            spec["effort"],
            "Use normal execution mode. Do not enter Plan mode or request a mode switch. "
            "Produce the implementation plan as your response. "
            "Do not edit files and do not open a pull request. "
            "Do not switch model or reasoning effort.",
        )
    for severity, spec in EXECUTION.items():
        files[spec["agent"]] = _agent_toml(
            spec["agent"],
            f"Staff execution worker for {severity} severity.",
            spec["model"],
            spec["effort"],
            "Implement the plan with the isolated-pr-workflow skill. "
            "Open the pull request as a draft. Do not switch model or reasoning effort.",
        )
    return files


def ticket_payload(ticket_type: str, scopes: list[str], flags: dict, explicit: str | None) -> dict:
    level = severity(ticket_type, scopes, flags, explicit)
    test_key = testing_id(ticket_type, scopes)
    return {
        "type": ticket_type,
        "scopes": scopes,
        "severity": level,
        "planning": PLANNING[level],
        "execution": EXECUTION[level],
        "max_loops": MAX_LOOPS[level],
        "testing": {"id": test_key, "instruction": TESTING[test_key]},
    }


def classify(task: str) -> dict:
    """Return query kind, and a ticket when the query is a codebase change."""
    kind_response = ask(
        {"task": task},
        {
            "kind": choice_question(
                instructions="Is this a knowledge question or a codebase change request?",
                criteria={
                    "kq": "An explanation or answer, not a change to the codebase.",
                    "ccr": "A change to code, config, infrastructure, CI, or the product.",
                },
            )
        },
        timeout=8,
    )
    kind = choice_label(kind_response, "kind") or heuristic_kind(task)
    if kind != "ccr":
        return {"query_kind": "kq", "harnesses": list(HARNESSES)}

    response = ask(
        {"task": task},
        {
            "type": choice_question(
                instructions="What ticket type is this codebase change?",
                criteria={
                    "chore": "Cleanup, styling, package upgrade, rename, or stylistic refactor.",
                    "bug": "An error a user hit, or one the platform recorded during use.",
                    "feature": "A new feature intended for immediate use.",
                    "experiment": "A new feature not intended for immediate use.",
                },
            ),
            "explicit_severity": choice_question(
                instructions="Does the request explicitly name a severity?",
                criteria={
                    "none": "No explicit severity.",
                    "low": "The user said low severity.",
                    "medium": "The user said medium severity.",
                    "high": "The user said high severity.",
                    "critical": "The user said critical severity.",
                },
            ),
            "frontend": predicate_question(
                instructions="Does the user encounter this on a screen?",
                criteria=yes_no(
                    "A page, button, or other thing they can see. A named page counts.",
                    "Not encountered on a screen.",
                ),
            ),
            "ci_cd": predicate_question(
                instructions="Does the user encounter this in the build or deploy pipeline?",
                criteria=yes_no("CI, a build, or a deploy.", "Not a build or deploy problem."),
            ),
            "cloud_infra": predicate_question(
                instructions="Does the user encounter this in cloud infrastructure?",
                criteria=yes_no(
                    "AWS, Terraform, Vercel, or another cloud system.",
                    "Not a cloud problem.",
                ),
            ),
            "backend": predicate_question(
                instructions="Does the user encounter this through server or service behavior?",
                criteria=yes_no(
                    "An API, stored data, or other server behavior.",
                    "No server behavior is described.",
                ),
            ),
            "bug_latent": predicate_question(
                instructions="Is this bug latent, not currently hitting users in normal use?",
                criteria={"true": "Latent.", "false": "Users can hit it now."},
            ),
            "bug_unlikely": predicate_question(
                instructions="Is this bug unlikely to be hit again in normal use?",
                criteria={"true": "Unlikely in normal use.", "false": "Normal use can hit it."},
            ),
            "bug_live": predicate_question(
                instructions="Did a user encounter this bug live?",
                criteria={"true": "A live user hit it.", "false": "No live encounter."},
            ),
            "feature_uncoupled": predicate_question(
                instructions="Does existing behavior keep working if this new feature fails?",
                criteria=yes_no(
                    "Existing behavior does not depend on it.",
                    "Existing behavior depends on it.",
                ),
            ),
        },
    )
    ticket_type = choice_label(response, "type") or "chore"
    if ticket_type not in {"chore", "bug", "feature", "experiment"}:
        ticket_type = "chore"
    scopes = [
        scope
        for scope, key in (
            ("frontend", "frontend"),
            ("ci-cd", "ci_cd"),
            ("cloud-infra", "cloud_infra"),
            ("backend", "backend"),
        )
        if is_yes(response, key, MODERATE)
    ]
    flags = {
        "bug_latent": is_yes(response, "bug_latent", HIGH),
        "bug_unlikely": is_yes(response, "bug_unlikely", HIGH),
        "bug_live": is_yes(response, "bug_live", HIGH),
        "feature_uncoupled": is_yes(response, "feature_uncoupled", HIGH),
    }
    explicit = choice_confident(response, "explicit_severity")
    if explicit == "none":
        explicit = None
    return {
        "query_kind": "ccr",
        "harnesses": list(HARNESSES),
        "ticket": ticket_payload(ticket_type, scopes, flags, explicit),
    }


def relevance(task: str, conversation: str) -> dict:
    response = ask(
        {"task": task, "conversation": conversation},
        {
            "relevant": predicate_question(
                instructions="Is this prior conversation relevant to the current request?",
                criteria={"true": "It bears on the request.", "false": "It does not."},
            )
        },
        timeout=8,
    )
    score = predicate_score(response, "relevant")
    if score is None:
        return {"relevant": False, "score": 0.0}
    return {"relevant": score >= HIGH, "score": score}


def filter_findings(task: str, findings: list) -> list:
    if not findings:
        return []
    questions = {
        f"f{index}": predicate_question(
            instructions=(
                f"Evaluate only findings[{index}] in the input (zero-based index). "
                "Is this review finding inconsequential for normal use?"
            ),
            criteria={
                "true": "The path cannot be reached in normal use.",
                "false": "A normal user or operator can hit it.",
            },
        )
        for index, _finding in enumerate(findings)
    }
    state = {"task": task, "findings": findings}
    response = ask(state, questions)
    if response is None:
        return findings
    kept = []
    for index, finding in enumerate(findings):
        if not is_yes(response, f"f{index}", HIGH):
            kept.append(finding)
    return kept


def confidence(task: str, evidence: str) -> dict:
    response = ask(
        {"task": task, "evidence": evidence},
        {
            "confidence": choice_question(
                instructions="Did this change meet a high quality bar?",
                criteria={
                    "high": "Small blast radius, real tests, and no open material defect.",
                    "low": "Missing proof, a wide blast radius, or an unresolved material defect.",
                },
            )
        },
        timeout=8,
    )
    label = choice_confident(response, "confidence")
    return {"confidence": "high" if label == "high" else "low"}


def hook_output() -> dict:
    """Old hook registrations are inert until the installer removes them."""
    return {}


def _query_from_args(parser: argparse.ArgumentParser, query: str | None) -> str:
    if query:
        return query
    if not sys.stdin.isatty():
        return sys.stdin.read()
    parser.error("provide a query")
    return ""


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--hook", action="store_true", help="Codex UserPromptSubmit hook")
    sub = parser.add_subparsers(dest="command")

    classify_parser = sub.add_parser("classify")
    classify_parser.add_argument("--query")
    classify_parser.add_argument("query_arg", nargs="?")

    relevance_parser = sub.add_parser("relevance")
    relevance_parser.add_argument("--query", required=True)
    relevance_parser.add_argument("--conversation", required=True)

    filter_parser = sub.add_parser("filter")
    filter_parser.add_argument("--query", required=True)

    confidence_parser = sub.add_parser("confidence")
    confidence_parser.add_argument("--query", required=True)

    args = parser.parse_args()
    if args.hook:
        print(json.dumps(hook_output()))
        return

    if args.command == "classify":
        text = args.query or args.query_arg or _query_from_args(parser, None)
        print(json.dumps(classify(text)))
        return
    if args.command == "relevance":
        print(json.dumps(relevance(args.query, args.conversation)))
        return
    if args.command == "filter":
        findings = json.load(sys.stdin)
        print(json.dumps(filter_findings(args.query, findings)))
        return
    if args.command == "confidence":
        print(json.dumps(confidence(args.query, sys.stdin.read())))
        return
    parser.error("choose classify, relevance, filter, confidence, or --hook")


if __name__ == "__main__":
    main()
