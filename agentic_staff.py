"""Jev decisions and model policy used by the explicit staff graph."""

import argparse
import json
import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from typesafe_sdk import Choice, Noul, TypeSafeClient

SOL = "gpt-6-sol"
ASTRA = "gpt-6-astra"
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


def load_env() -> None:
    load_dotenv(Path(__file__).with_name(".env.local"), override=False)


def ask(state: dict, questions: dict, timeout: int = 20):
    """Return a Jev response, or None when the call cannot be made."""
    load_env()
    if not os.getenv("TYPESAFE_API_KEY"):
        return None
    try:
        with TypeSafeClient() as client:
            return client.system_one(state=state, questions=questions, timeout=timeout)
    except Exception:
        return None


def choice_label(response, name: str) -> str | None:
    if response is None:
        return None
    answer = response.choices[name]
    return answer.choice


def choice_confident(response, name: str, threshold: float = HIGH) -> str | None:
    if response is None:
        return None
    answer = response.choices[name]
    if answer.confidence < threshold:
        return None
    return answer.choice


def noul_score(response, name: str) -> float | None:
    """Read a yes/no probability. Jev keeps those on `nouls`, not `choices`."""
    if response is None:
        return None
    nouls = getattr(response, "nouls", None) or {}
    answer = nouls.get(name)
    if answer is None:
        return None
    return float(answer.noul)


def is_yes(response, name: str, threshold: float) -> bool:
    score = noul_score(response, name)
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
            "kind": Choice(
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
            "type": Choice(
                instructions="What ticket type is this codebase change?",
                criteria={
                    "chore": "Cleanup, styling, package upgrade, rename, or stylistic refactor.",
                    "bug": "An error a user hit, or one the platform recorded during use.",
                    "feature": "A new feature intended for immediate use.",
                    "experiment": "A new feature not intended for immediate use.",
                },
            ),
            "explicit_severity": Choice(
                instructions="Does the request explicitly name a severity?",
                criteria={
                    "none": "No explicit severity.",
                    "low": "The user said low severity.",
                    "medium": "The user said medium severity.",
                    "high": "The user said high severity.",
                    "critical": "The user said critical severity.",
                },
            ),
            "frontend": Noul(
                instructions="Does the user encounter this on a screen?",
                criteria=yes_no(
                    "A page, button, or other thing they can see. A named page counts.",
                    "Not encountered on a screen.",
                ),
            ),
            "ci_cd": Noul(
                instructions="Does the user encounter this in the build or deploy pipeline?",
                criteria=yes_no("CI, a build, or a deploy.", "Not a build or deploy problem."),
            ),
            "cloud_infra": Noul(
                instructions="Does the user encounter this in cloud infrastructure?",
                criteria=yes_no(
                    "AWS, Terraform, Vercel, or another cloud system.",
                    "Not a cloud problem.",
                ),
            ),
            "backend": Noul(
                instructions="Does the user encounter this through server or service behavior?",
                criteria=yes_no(
                    "An API, stored data, or other server behavior.",
                    "No server behavior is described.",
                ),
            ),
            "bug_latent": Noul(
                instructions="Is this bug latent, not currently hitting users in normal use?",
                criteria={"true": "Latent.", "false": "Users can hit it now."},
            ),
            "bug_unlikely": Noul(
                instructions="Is this bug unlikely to be hit again in normal use?",
                criteria={"true": "Unlikely in normal use.", "false": "Normal use can hit it."},
            ),
            "bug_live": Noul(
                instructions="Did a user encounter this bug live?",
                criteria={"true": "A live user hit it.", "false": "No live encounter."},
            ),
            "feature_uncoupled": Noul(
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
            "relevant": Noul(
                instructions="Is this prior conversation relevant to the current request?",
                criteria={"true": "It bears on the request.", "false": "It does not."},
            )
        },
        timeout=8,
    )
    score = noul_score(response, "relevant")
    if score is None:
        return {"relevant": False, "score": 0.0}
    return {"relevant": score >= HIGH, "score": score}


def filter_findings(task: str, findings: list) -> list:
    if not findings:
        return []
    questions = {
        f"f{index}": Noul(
            instructions="Is this review finding inconsequential for normal use?",
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
            "confidence": Choice(
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
