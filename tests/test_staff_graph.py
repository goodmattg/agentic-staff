import json
from pathlib import Path

import pytest
from pydantic import ValidationError

import staff_graph as staff

CONTEXT = {
    "summary": "Repository context",
    "files": ["app.py"],
    "conversations": [],
    "unavailable_harnesses": ["claude", "codex", "pi", "grok"],
}
EXECUTION = {
    "summary": "Implementation done",
    "pr_url": "https://github.com/example/repo/pull/1",
    "worktree": "/tmp/repo-worktree",
    "tests": ["primary path passed"],
    "draft": True,
}


@pytest.fixture
def store(tmp_path, monkeypatch):
    monkeypatch.setattr(
        staff.jev,
        "classify",
        lambda _: {
            "query_kind": "ccr",
            "ticket": staff.jev.ticket_payload("chore", ["backend"], {}, None),
        },
    )
    monkeypatch.setattr(staff.jev, "relevance", lambda *_: {"relevant": False})
    monkeypatch.setattr(staff.jev, "filter_findings", lambda _, findings: findings)
    monkeypatch.setattr(staff.jev, "confidence", lambda *_: {"confidence": "high"})
    return staff.RunStore(tmp_path)


def start(store, harness="codex"):
    return store.start("Implement the change", harness, Path.cwd(), explicit=True)


def advance(store, reply, result):
    return store.advance(reply["run_id"], reply["action"]["id"], result)


def reviews(findings=False):
    return {
        "reviews": {name: ["Fix the regression"] if findings else [] for name in staff.REVIEWERS}
    }


def execute_pass(store, reply):
    assert reply["action"]["kind"] == "plan"
    reply = advance(store, reply, {"plan": "Implement and verify"})
    assert reply["action"]["kind"] == "execute"
    reply = advance(store, reply, EXECUTION)
    assert reply["action"]["kind"] == "review"
    return reply


def test_plain_request_does_not_classify_or_create_run(store, monkeypatch):
    monkeypatch.setattr(staff.jev, "classify", lambda _: pytest.fail("Unexpected classifier call"))
    assert store.start("Fix something", "codex", Path.cwd())["status"] == "direct"
    with store.connect() as connection:
        assert connection.execute("SELECT count(*) FROM runs").fetchone()[0] == 0


def test_kq_completes_without_agent_actions(store, monkeypatch):
    monkeypatch.setattr(staff.jev, "classify", lambda _: {"query_kind": "kq"})
    reply = start(store)
    assert reply["status"] == "complete"
    assert reply["query_kind"] == "kq"
    assert reply["action"] is None
    assert store.status(reply["run_id"]) == reply


@pytest.mark.parametrize("harness", staff.jev.HARNESSES)
def test_full_graph_host_protocol_and_followup_bypass(store, harness, monkeypatch):
    reply = start(store, harness)
    run_id = reply["run_id"]
    assert reply["action"]["kind"] == "context"
    reply = advance(store, reply, CONTEXT)
    if harness == "codex":
        assert "staff_plan_low" in reply["action"]["instructions"]
    else:
        assert "gpt-6-astra" in reply["action"]["instructions"]
    reply = execute_pass(store, reply)
    reply = advance(store, reply, reviews())
    assert reply["action"]["kind"] == "finalize"
    assert reply["confidence"] == "high"
    assert reply["loops"] == 1
    reply = advance(
        store,
        reply,
        {
            "pr_url": EXECUTION["pr_url"],
            "pr_state": "ready",
            "worktree_removed": True,
        },
    )
    assert reply["status"] == "complete"
    assert reply["action"] is None
    with pytest.raises(ValueError, match="no pending action"):
        store.advance(run_id, "arbitrary", {})
    monkeypatch.setattr(staff.jev, "classify", lambda _: pytest.fail("Followup entered graph"))
    assert store.start("Adjust the change", harness, Path.cwd())["status"] == "direct"


def test_checkpoint_recovery_and_duplicate_result_rejection(store):
    first = start(store)
    reopened = staff.RunStore(store.path.parent)
    assert reopened.status(first["run_id"]) == first
    second = advance(reopened, first, CONTEXT)
    with pytest.raises(ValueError, match="Stale"):
        advance(store, first, CONTEXT)
    assert store.status(first["run_id"]) == second


def test_wrong_result_and_unexpected_state_fields_do_not_advance(store):
    reply = start(store)
    for bad in [{"plan": "Skip context"}, {**CONTEXT, "loops": 99}]:
        with pytest.raises(ValidationError):
            advance(store, reply, bad)
        assert store.status(reply["run_id"]) == reply


def test_review_requires_all_five_distinct_reviewers(store):
    reply = execute_pass(store, advance(store, start(store), CONTEXT))
    with pytest.raises(ValidationError, match="each reviewer"):
        advance(store, reply, {"reviews": {"Jeff": []}})
    assert store.status(reply["run_id"]) == reply


@pytest.mark.parametrize("cap", [1, 2, 3])
def test_loop_cap_and_unresolved_findings_force_low_confidence(store, monkeypatch, cap):
    severity = {1: "low", 2: "medium", 3: "critical"}[cap]
    monkeypatch.setattr(
        staff.jev,
        "classify",
        lambda _: {
            "query_kind": "ccr",
            "ticket": staff.jev.ticket_payload("chore", ["backend"], {}, severity),
        },
    )
    reply = advance(store, start(store), CONTEXT)
    for count in range(cap):
        reply = advance(store, execute_pass(store, reply), reviews(findings=True))
        assert reply["loops"] == count + 1
    assert reply["action"]["kind"] == "finalize"
    assert reply["confidence"] == "low"
    with pytest.raises(ValueError, match="draft"):
        advance(
            store,
            reply,
            {
                "pr_url": EXECUTION["pr_url"],
                "pr_state": "ready",
                "worktree_removed": True,
            },
        )
    assert store.status(reply["run_id"]) == reply
    done = advance(
        store,
        reply,
        {
            "pr_url": EXECUTION["pr_url"],
            "pr_state": "draft",
            "worktree_removed": False,
        },
    )
    assert done["status"] == "complete"
    assert "LOW CONFIDENCE" in done["reply_instruction"]


def test_revision_cannot_replace_pr_or_worktree(store, monkeypatch):
    monkeypatch.setattr(
        staff.jev,
        "classify",
        lambda _: {
            "query_kind": "ccr",
            "ticket": staff.jev.ticket_payload("chore", ["backend"], {}, "medium"),
        },
    )
    reply = execute_pass(store, advance(store, start(store), CONTEXT))
    reply = advance(store, reply, reviews(findings=True))
    reply = advance(store, reply, {"plan": "Address findings"})
    with pytest.raises(ValueError, match="existing PR"):
        advance(store, reply, {**EXECUTION, "pr_url": "https://github.com/example/repo/pull/2"})
    assert store.status(reply["run_id"]) == reply


def test_only_relevant_conversations_reach_planner(store, monkeypatch):
    monkeypatch.setattr(staff.jev, "relevance", lambda _, text: {"relevant": text == "relevant"})
    conversations = [
        {"harness": "codex", "reference": name, "text": name} for name in ["relevant", "irrelevant"]
    ]
    reply = advance(store, start(store), {**CONTEXT, "conversations": conversations})
    assert reply["action"]["payload"]["context"]["conversations"] == [conversations[0]]


def test_block_recover_cancel_and_independent_runs(store):
    first, second = start(store), start(store)
    assert first["run_id"] != second["run_id"]
    blocked = store.block(first["run_id"], first["action"]["id"], "History unavailable")
    assert blocked["status"] == "blocked"
    assert blocked["action"] == first["action"]
    recovered = advance(store, blocked, CONTEXT)
    assert recovered["status"] == "waiting"
    assert recovered["blocked_reason"] is None
    assert store.status(second["run_id"]) == second
    assert store.cancel(first["run_id"])["status"] == "cancelled"
    with pytest.raises(ValueError, match="no pending action"):
        advance(store, recovered, {"plan": "too late"})


def test_cli_direct_path_creates_no_store(tmp_path, monkeypatch, capsys):
    target = tmp_path / "no-state"
    monkeypatch.setattr(
        "sys.argv",
        [
            "staff_graph.py",
            "--state-dir",
            str(target),
            "start",
            "--harness",
            "codex",
            "--query",
            "a followup",
        ],
    )
    staff.main()
    assert json.loads(capsys.readouterr().out)["status"] == "direct"
    assert not target.exists()


def test_diagram_is_built_from_executable_nodes():
    diagram = staff.GRAPH.render()
    assert "Synthesize -->" in diagram
    assert "Confidence --> Finalize" in diagram
    assert "AwaitHost" in diagram
