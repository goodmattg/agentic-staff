import json

import pytest
from conftest import choice_answer, predicate_answer

import agentic_staff


def test_severity_table():
    assert agentic_staff.severity("chore", ["backend"], {}, None) == "low"
    assert agentic_staff.severity("experiment", ["frontend", "backend"], {}, None) == "low"
    flags = {"bug_latent": True, "bug_unlikely": True}
    assert agentic_staff.severity("bug", ["backend"], flags, None) == "low"
    assert agentic_staff.severity("bug", ["backend"], {"bug_latent": True}, None) == "medium"
    live = {"bug_live": True, "bug_unlikely": True}
    assert agentic_staff.severity("bug", ["frontend"], live, None) == "high"
    assert agentic_staff.severity("bug", ["frontend"], {"bug_live": True}, None) == "critical"
    assert (
        agentic_staff.severity("feature", ["frontend"], {"feature_uncoupled": True}, None) == "low"
    )
    assert (
        agentic_staff.severity(
            "feature",
            ["frontend", "backend"],
            {"feature_uncoupled": True},
            None,
        )
        == "medium"
    )
    assert (
        agentic_staff.severity(
            "feature",
            ["frontend", "backend", "ci-cd"],
            {"feature_uncoupled": True},
            None,
        )
        == "high"
    )
    assert agentic_staff.severity("feature", ["frontend"], {}, None) == "critical"
    assert agentic_staff.severity("chore", ["backend"], {}, "critical") == "critical"


def test_testing_ids():
    assert agentic_staff.testing_id("bug", ["backend"]) == "backend-bug"
    assert agentic_staff.testing_id("bug", ["frontend"]) == "frontend-bug"
    assert agentic_staff.testing_id("bug", ["frontend", "backend"]) == "full-stack-bug"
    assert agentic_staff.testing_id("bug", ["cloud-infra"]) == "infra-bug"
    assert agentic_staff.testing_id("chore", ["frontend"]) == "ux"
    scopes = ["frontend", "backend", "ci-cd"]
    assert agentic_staff.testing_id("feature", scopes) == "feature-ux-backend-infra"
    assert agentic_staff.testing_id("bug", []) == "later"
    assert "read the code" in agentic_staff.TESTING["later"].lower()


def test_models_follow_severity():
    ticket = agentic_staff.ticket_payload("bug", ["backend"], {"bug_latent": True}, None)
    assert ticket["severity"] == "medium"
    assert ticket["planning"] == {
        "model": "gpt-6-astra",
        "effort": "high",
        "agent": "staff_plan_medium",
    }
    assert ticket["execution"] == {
        "model": "gpt-6-sol",
        "effort": "high",
        "agent": "staff_exec_medium",
    }
    assert ticket["max_loops"] == 2
    agents = agentic_staff.codex_agent_files()
    assert 'model = "gpt-6-astra"' in agents["staff_plan_medium"]
    assert 'model_reasoning_effort = "high"' in agents["staff_plan_medium"]
    assert 'model = "gpt-6-sol"' in agents["staff_exec_critical"]
    assert 'model_reasoning_effort = "xhigh"' in agents["staff_exec_critical"]


def test_missing_key_classifies_without_network(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setattr(agentic_staff, "load_dotenv", lambda *_, **__: None)
    assert agentic_staff.classify("What does the retry loop do?")["query_kind"] == "kq"
    change = agentic_staff.classify("Fix the retry bug")
    assert change["query_kind"] == "ccr"
    assert change["ticket"]["severity"] == "low"


def test_decisions_kind_and_ticket(decision_api):
    decision_api.enqueue(choice_answer("kind", "ccr"))
    decision_api.enqueue(
        choice_answer("type", "bug"),
        choice_answer("explicit_severity", "none"),
        *[
            predicate_answer(name, score)
            for name, score in {
                "frontend": 0.1,
                "ci_cd": 0.1,
                "cloud_infra": 0.1,
                "backend": 0.9,
                "bug_latent": 0.95,
                "bug_unlikely": 0.1,
                "bug_live": 0.1,
                "feature_uncoupled": 0.1,
            }.items()
        ],
    )
    result = agentic_staff.classify("Users hit a latent backend error")
    first, second = [request["body"] for request in decision_api.requests]
    assert first["model"] == "gpt-6-luna"
    assert json.loads(first["input"]) == {"task": "Users hit a latent backend error"}
    assert [q["name"] for q in first["questions"]] == ["kind"]
    assert first["questions"][0]["choices"][0] == {
        "value": "kq",
        "description": "An explanation or answer, not a change to the codebase.",
    }
    assert len(second["questions"]) == 10
    assert result["ticket"]["type"] == "bug"
    assert result["ticket"]["scopes"] == ["backend"]
    assert result["ticket"]["severity"] == "medium"


def test_old_hook_registration_is_inert():
    assert agentic_staff.hook_output() == {}


def test_filter_drops_only_its_indexed_inconsequential_finding(decision_api):
    # Reverse the response order to prove names, not positions, determine the result.
    decision_api.enqueue(predicate_answer("f1", 0.1), predicate_answer("f0", 0.99))
    assert agentic_staff.filter_findings("task", ["hidden path", "broken button"]) == [
        "broken button"
    ]
    questions = decision_api.requests[0]["body"]["questions"]
    assert "findings[0]" in questions[0]["instructions"]
    assert "findings[1]" in questions[1]["instructions"]
    assert "True: The path cannot be reached" in questions[0]["instructions"]


def test_low_confidence_without_openai(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setattr(agentic_staff, "load_dotenv", lambda *_, **__: None)
    assert agentic_staff.confidence("task", "no tests") == {"confidence": "low"}


def test_cli_classify(monkeypatch, capsys):
    monkeypatch.setattr(agentic_staff, "classify", lambda task: {"query_kind": "kq", "task": task})
    monkeypatch.setattr("sys.argv", ["agentic_staff.py", "classify", "--query", "why"])
    agentic_staff.main()
    assert json.loads(capsys.readouterr().out)["query_kind"] == "kq"


@pytest.mark.parametrize("status", [401, 429, 500])
def test_api_errors_keep_findings_and_log_no_request_data(decision_api, caplog, status):
    decision_api.responses.append((status, {"error": {"message": "SECRET-ECHO"}}))
    findings = ["A real user can hit the regression"]
    assert agentic_staff.filter_findings("task", findings) == findings
    assert len(decision_api.requests) == 1  # No implicit SDK retries.
    assert "using fallback" in caplog.text
    assert "SECRET-ECHO" not in caplog.text


def test_refusals_and_missing_answers_use_independent_fallbacks(decision_api):
    decision_api.enqueue({"type": "refusal", "name": "kind"})
    decision_api.enqueue(choice_answer("type", "feature"))
    result = agentic_staff.classify("Add a feature")
    assert result["query_kind"] == "ccr"
    assert result["ticket"]["type"] == "feature"
    assert result["ticket"]["severity"] == "critical"
    decision_api.enqueue({"type": "refusal", "name": "confidence"})
    assert agentic_staff.confidence("task", "tests passed") == {"confidence": "low"}
    decision_api.enqueue({"type": "refusal", "name": "relevant"})
    assert agentic_staff.relevance("task", "conversation") == {"relevant": False, "score": 0.0}
    decision_api.enqueue({"type": "refusal", "name": "f0"}, predicate_answer("f1", 0.99))
    assert agentic_staff.filter_findings("task", ["unknown", "unreachable"]) == ["unknown"]


@pytest.mark.parametrize("score", [0.79, 0.8, 0.95])
def test_confidence_threshold(decision_api, score):
    decision_api.enqueue(choice_answer("confidence", "high", score))
    assert agentic_staff.confidence("task", "proof")["confidence"] == (
        "high" if score >= 0.8 else "low"
    )


@pytest.mark.parametrize("score", [-0.1, 1.1, float("nan"), float("inf"), None])
def test_invalid_probability_cannot_drop_a_finding(decision_api, score):
    decision_api.enqueue(predicate_answer("f0", score))
    assert agentic_staff.filter_findings("task", ["keep"]) == ["keep"]


def test_unknown_wrong_type_and_duplicate_answers_are_not_trusted(decision_api):
    decision_api.enqueue(
        predicate_answer("f0", 0.99),
        predicate_answer("f0", 0.99),
        choice_answer("f1", "high"),
        predicate_answer("other", 0.99),
    )
    assert agentic_staff.filter_findings("task", ["duplicate", "wrong type"]) == [
        "duplicate",
        "wrong type",
    ]
    decision_api.enqueue(choice_answer("confidence", "invalid"))
    assert agentic_staff.confidence("task", "proof") == {"confidence": "low"}


def test_large_review_batches_preserve_findings_when_one_request_fails(decision_api):
    findings = [f"finding {i}" for i in range(401)]
    decision_api.enqueue(*[predicate_answer(f"f{i}", 0.99) for i in range(200)])
    decision_api.responses.append((500, {"error": {"message": "unavailable"}}))
    decision_api.enqueue(predicate_answer("f400", 0.99))
    assert agentic_staff.filter_findings("task", findings) == findings[200:400]
    assert [len(r["body"]["questions"]) for r in decision_api.requests] == [200, 200, 1]


def test_empty_findings_do_not_call_api(decision_api):
    assert agentic_staff.filter_findings("task", []) == []
    assert not decision_api.requests


def test_timeout_uses_fallback_and_configured_budget(decision_api, monkeypatch):
    from openai import APITimeoutError, OpenAI

    options = []

    def client_factory(**kwargs):
        options.append(kwargs)
        client = OpenAI(**kwargs)

        def timed_out(**_):
            raise APITimeoutError(request=None)

        monkeypatch.setattr(client.decisions, "create", timed_out)
        return client

    monkeypatch.setattr(agentic_staff, "OpenAI", client_factory)
    assert agentic_staff.relevance("task", "context") == {"relevant": False, "score": 0.0}
    assert options == [{"timeout": 8, "max_retries": 0}]


@pytest.mark.parametrize("score", [0.64, 0.65, 0.79, 0.8])
def test_scope_and_relevance_use_their_own_thresholds(decision_api, score):
    decision_api.enqueue(choice_answer("kind", "ccr"))
    decision_api.enqueue(choice_answer("type", "chore"), predicate_answer("backend", score))
    ticket = agentic_staff.classify("Rename a backend variable")["ticket"]
    assert ticket["scopes"] == (["backend"] if score >= 0.65 else [])
    decision_api.enqueue(predicate_answer("relevant", score))
    assert agentic_staff.relevance("task", "context") == {"relevant": score >= 0.8, "score": score}
