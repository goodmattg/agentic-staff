"""Opt-in smoke/e2e checks against api.openai.com using synthetic evidence."""

import os

import pytest
from test_decisions_e2e import roundtrip

import agentic_staff

pytestmark = pytest.mark.skipif(
    os.getenv("STAFF_LIVE_DECISIONS") != "1",
    reason="Set STAFF_LIVE_DECISIONS=1 to run paid live API checks",
)


@pytest.fixture(autouse=True)
def live_credentials(monkeypatch):
    agentic_staff.load_env()
    if not os.getenv("OPENAI_API_KEY"):
        pytest.fail("Live testing requires OPENAI_API_KEY in the environment or .env.local")
    monkeypatch.setenv("OPENAI_BASE_URL", "https://api.openai.com/v1")
    original_ask = agentic_staff.ask

    def require_live_answers(state, questions, timeout=20):
        answers = original_ask(state, questions, timeout=timeout)
        assert answers is not None and set(answers) == set(questions), (
            "Live API returned missing, refused, or invalid answers; fallback is not a live pass"
        )
        return answers

    monkeypatch.setattr(agentic_staff, "ask", require_live_answers)


def test_live_decision_functions():
    assert (
        agentic_staff.classify("What does this repository's retry loop do?")["query_kind"] == "kq"
    )
    change = agentic_staff.classify(
        "Medium severity bug: fix the backend API returning HTTP 500 for every request. "
        "Users are hitting the error now. There is no frontend or infrastructure change."
    )
    assert change["query_kind"] == "ccr"
    assert change["ticket"]["type"] == "bug"
    assert "backend" in change["ticket"]["scopes"]
    assert change["ticket"]["severity"] == "medium"
    task = "Fix the backend retry loop that retries failed API requests forever."
    assert agentic_staff.relevance(
        task, "The backend API retry loop retries forever because it never increments its counter."
    )["relevant"]
    assert not agentic_staff.relevance(task, "The cafeteria serves soup on Tuesdays.")["relevant"]
    material = "The backend retry counter still never increments, so failed requests retry forever."
    unreachable = (
        "An old unused function has a typo; it has no callers, is never imported or executed, "
        "and cannot be reached by any normal user or operator path."
    )
    assert agentic_staff.filter_findings(task, [material, unreachable]) == [material]
    assert agentic_staff.confidence(
        task, "No implementation was made, no tests ran, and the infinite retry bug is unresolved."
    ) == {"confidence": "low"}


def test_live_api_cli_graph_roundtrip(tmp_path):
    # Real decisions and persisted CLI transitions; native host actions remain synthetic.
    reply = roundtrip(tmp_path, "codex")
    assert reply["confidence"] == "low"  # The material finding must keep the PR draft.
    assert len(reply["evidence"]["findings"]) == 1
