import json
from types import SimpleNamespace

import agentic_staff


def choice(label, confidence=0.95):
    return SimpleNamespace(choice=label, confidence=confidence)


def noul(score):
    return SimpleNamespace(noul=score)


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
    monkeypatch.delenv("TYPESAFE_API_KEY", raising=False)
    monkeypatch.setattr(agentic_staff, "load_dotenv", lambda *_, **__: None)
    assert agentic_staff.classify("What does the retry loop do?")["query_kind"] == "kq"
    change = agentic_staff.classify("Fix the retry bug")
    assert change["query_kind"] == "ccr"
    assert change["ticket"]["severity"] == "low"


def test_jev_kind_and_ticket(monkeypatch):
    monkeypatch.setenv("TYPESAFE_API_KEY", "test-key")
    calls = []

    class Client:
        def __enter__(self):
            return self

        def __exit__(self, *_):
            return None

        def system_one(self, *, state, questions, timeout):
            calls.append((set(questions), timeout, state["task"]))
            if "kind" in questions:
                return SimpleNamespace(choices={"kind": choice("ccr")}, nouls={})
            return SimpleNamespace(
                choices={
                    "type": choice("bug"),
                    "explicit_severity": choice("none"),
                },
                nouls={
                    "frontend": noul(0.1),
                    "ci_cd": noul(0.1),
                    "cloud_infra": noul(0.1),
                    "backend": noul(0.9),
                    "bug_latent": noul(0.95),
                    "bug_unlikely": noul(0.1),
                    "bug_live": noul(0.1),
                    "feature_uncoupled": noul(0.1),
                },
            )

    monkeypatch.setattr(agentic_staff, "TypeSafeClient", Client)
    result = agentic_staff.classify("Users hit a latent backend error")
    assert calls[0][0] == {"kind"}
    assert calls[0][1] == 8
    assert result["ticket"]["type"] == "bug"
    assert result["ticket"]["scopes"] == ["backend"]
    assert result["ticket"]["severity"] == "medium"


def test_old_hook_registration_is_inert():
    assert agentic_staff.hook_output() == {}


def test_filter_drops_inconsequential(monkeypatch):
    monkeypatch.setenv("TYPESAFE_API_KEY", "test-key")

    class Client:
        def __enter__(self):
            return self

        def __exit__(self, *_):
            return None

        def system_one(self, **_):
            return SimpleNamespace(nouls={"f0": noul(0.99), "f1": noul(0.1)})

    monkeypatch.setattr(agentic_staff, "TypeSafeClient", Client)
    kept = agentic_staff.filter_findings("task", ["hidden path", "broken button"])
    assert kept == ["broken button"]


def test_low_confidence_without_jev(monkeypatch):
    monkeypatch.delenv("TYPESAFE_API_KEY", raising=False)
    monkeypatch.setattr(agentic_staff, "load_dotenv", lambda *_, **__: None)
    assert agentic_staff.confidence("task", "no tests") == {"confidence": "low"}


def test_cli_classify(monkeypatch, capsys):
    monkeypatch.setattr(agentic_staff, "classify", lambda task: {"query_kind": "kq", "task": task})
    monkeypatch.setattr("sys.argv", ["agentic_staff.py", "classify", "--query", "why"])
    agentic_staff.main()
    assert json.loads(capsys.readouterr().out)["query_kind"] == "kq"
