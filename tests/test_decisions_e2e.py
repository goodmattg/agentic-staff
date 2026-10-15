"""CLI -> checkpointed graph -> real OpenAI SDK -> local HTTP contract fixture."""

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest
from conftest import choice_answer, predicate_answer

import agentic_staff
import staff_graph

ROOT = Path(__file__).resolve().parents[1]
TASK = "Low severity chore: rename a backend variable without changing behavior."
PR_URL = "https://github.com/example/repo/pull/1"


def cli(tmp_path, *args, env=None):
    result = subprocess.run(
        [sys.executable, str(ROOT / "staff_graph.py"), "--state-dir", str(tmp_path), *args],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
        check=True,
    )
    assert "Decisions API request failed" not in result.stderr
    return json.loads(result.stdout)


def roundtrip(tmp_path, harness, *, env=None):
    """Submit synthetic host results; do not launch workers or modify real PRs."""
    direct = cli(tmp_path, "start", "--harness", harness, "--query", TASK, env=env)
    assert direct["status"] == "direct"
    assert not (tmp_path / "runs.sqlite3").exists()
    reply = cli(tmp_path, "start", "--explicit", "--harness", harness, "--query", TASK, env=env)
    run_id = reply["run_id"]
    assert reply["action"]["kind"] == "context"
    ticket = reply["action"]["payload"]["ticket"]
    assert ticket["severity"] == "low"
    assert ticket["planning"]["model"] == agentic_staff.ASTRA
    assert ticket["execution"]["model"] == agentic_staff.SOL
    steps = []
    while reply["status"] != "complete":
        # Each command runs in a fresh process and reloads the SQLite checkpoint.
        assert cli(tmp_path, "status", "--run", run_id, env=env) == reply
        kind = reply["action"]["kind"]
        steps.append(kind)
        if kind == "context":
            result = {
                "summary": "Synthetic host context for transport verification",
                "files": ["service.py"],
                "conversations": [
                    {
                        "harness": harness,
                        "reference": "prior",
                        "text": f"Earlier discussion of this same request: {TASK}",
                    }
                ],
                "unavailable_harnesses": [],
            }
        elif kind == "plan":
            assert reply["action"]["payload"]["context"]["conversations"]
            result = {"plan": "Rename the local variable and verify behavior."}
        elif kind == "execute":
            result = {
                "summary": "Synthetic host execution result",
                "pr_url": PR_URL,
                "worktree": "/tmp/synthetic-staff-e2e",
                "tests": ["Synthetic host verification evidence"],
                "draft": True,
            }
        elif kind == "review":
            result = {"reviews": {name: [] for name in staff_graph.REVIEWERS}}
            result["reviews"][staff_graph.REVIEWERS[0]] = [
                "This renamed variable breaks a real user-facing API request.",
                "Unreachable branch: there is no caller or input that can reach this code.",
            ]
        else:
            assert kind == "finalize"
            high = reply["confidence"] == "high"
            result = {
                "pr_url": PR_URL,
                "pr_state": "ready" if high else "draft",
                "worktree_removed": high,
            }
        result_file = tmp_path / "result.json"
        result_file.write_text(json.dumps(result))
        reply = cli(
            tmp_path,
            "advance",
            "--run",
            run_id,
            "--action",
            reply["action"]["id"],
            "--result-file",
            str(result_file),
            env=env,
        )
    assert steps == ["context", "plan", "execute", "review", "finalize"]
    assert cli(tmp_path, "status", "--run", run_id, env=env) == reply
    return reply


@pytest.mark.parametrize("harness", agentic_staff.HARNESSES)
@pytest.mark.parametrize("scenario", ["ready", "unresolved", "refusal"])
def test_cli_graph_decisions_roundtrip(tmp_path, decision_api, harness, scenario):
    decision_api.enqueue(choice_answer("kind", "ccr"))
    decision_api.enqueue(
        choice_answer("type", "chore"),
        choice_answer("explicit_severity", "low"),
        predicate_answer("backend", 0.99),
    )
    decision_api.enqueue(predicate_answer("relevant", 0.99))
    decision_api.enqueue(
        predicate_answer("f0", 0.99 if scenario == "ready" else 0.01),
        predicate_answer("f1", 0.99),
    )
    decision_api.enqueue(
        {"type": "refusal", "name": "confidence"}
        if scenario == "refusal"
        else choice_answer("confidence", "high")
    )
    reply = roundtrip(tmp_path, harness)
    assert reply["confidence"] == ("high" if scenario == "ready" else "low")
    assert reply["loops"] == 1
    assert len(decision_api.requests) == 5
    assert not decision_api.responses
    for request in decision_api.requests:
        assert request["path"] == "/v1/decisions"
        assert request["body"]["model"] == "gpt-6-luna"
    state = staff_graph.RunStore(tmp_path)
    with state.connect() as connection:
        run = state.load(connection, reply["run_id"])
    assert len(run.findings) == (0 if scenario == "ready" else 1)
    assert run.history[-1]["result"]["pr_state"] == ("ready" if scenario == "ready" else "draft")
    assert run.history[-1]["result"]["worktree_removed"] == (scenario == "ready")


def test_cli_knowledge_question_and_missing_key(tmp_path, decision_api):
    decision_api.enqueue(choice_answer("kind", "kq"))
    reply = cli(
        tmp_path,
        "start",
        "--explicit",
        "--harness",
        "codex",
        "--query",
        "What does the retry loop do?",
    )
    assert reply["status"] == "complete"
    assert reply["query_kind"] == "kq"
    assert len(decision_api.requests) == 1
    env = {**os.environ, "OPENAI_API_KEY": ""}
    result = subprocess.run(
        [sys.executable, str(ROOT / "agentic_staff.py"), "confidence", "--query", TASK],
        input="No verification evidence",
        env=env,
        capture_output=True,
        text=True,
        timeout=10,
        check=True,
    )
    assert json.loads(result.stdout) == {"confidence": "low"}
    assert len(decision_api.requests) == 1
