from types import SimpleNamespace

import agentic_staff


def test_jev_selects_astra(monkeypatch):
    monkeypatch.setenv("TYPESAFE_API_KEY", "test-key")

    class Client:
        def __enter__(self):
            return self

        def __exit__(self, *_):
            return None

        def system_one(self, *, state, questions, timeout):
            assert state == {"task": "Investigate a complex failure"}
            assert "model" in questions
            assert timeout == 8
            return SimpleNamespace(choices={"model": SimpleNamespace(choice="astra")})

    monkeypatch.setattr(agentic_staff, "TypeSafeClient", Client)
    assert agentic_staff.choose_model("Investigate a complex failure") == agentic_staff.ASTRA


def test_missing_key_defaults_to_sol(monkeypatch):
    monkeypatch.delenv("TYPESAFE_API_KEY", raising=False)
    monkeypatch.setattr(agentic_staff, "load_dotenv", lambda *_, **__: None)
    assert agentic_staff.choose_model("Fix a typo") == agentic_staff.SOL


def test_bad_jev_reply_defaults_to_sol(monkeypatch):
    monkeypatch.setenv("TYPESAFE_API_KEY", "test-key")

    class Client:
        def __enter__(self):
            return self

        def __exit__(self, *_):
            return None

        def system_one(self, **_):
            return SimpleNamespace(choices={"model": SimpleNamespace(choice="unknown")})

    monkeypatch.setattr(agentic_staff, "TypeSafeClient", Client)
    assert agentic_staff.choose_model("Any task") == agentic_staff.SOL


def test_hook_output_names_selected_agent_and_model():
    context = agentic_staff.hook_output(agentic_staff.ASTRA)["hookSpecificOutput"]
    assert context["hookEventName"] == "UserPromptSubmit"
    assert "routed_worker" in context["additionalContext"]
    assert "model=gpt-6-astra" in context["additionalContext"]
