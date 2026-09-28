import copy
import json

import install


def test_splice_inserts_once_then_replaces():
    first = install.splice("Existing rules.\n", "Use staff.")
    second = install.splice(first, "Explicit staff only.")
    assert second.count(install.MARKER_START) == 1
    assert "Explicit staff only." in second
    assert "Use staff.\n" not in second
    assert second.startswith("Existing rules.")


def test_remove_only_managed_hooks_in_mixed_groups():
    other = {"type": "command", "command": "/tmp/unrelated-hook", "timeout": 3}
    payload = {
        "setting": True,
        "hooks": {
            "UserPromptSubmit": [
                {"hooks": [{"command": '/usr/bin/uv run python "/tmp/agentic_staff.py" --hook'}]},
                {
                    "matcher": "*",
                    "hooks": [other, {"command": "python /tmp/agentic-staff.py --hook"}],
                },
            ],
            "Stop": [{"hooks": [other]}],
        },
    }
    result = install.remove_staff_hooks(copy.deepcopy(payload))
    assert result == {
        "setting": True,
        "hooks": {
            "UserPromptSubmit": [{"matcher": "*", "hooks": [other]}],
            "Stop": payload["hooks"]["Stop"],
        },
    }
    assert install.remove_staff_hooks(copy.deepcopy(result)) == result
    assert install.remove_staff_hooks({}) == {}


def test_install_migrates_old_rules_preserves_unrelated_config_and_is_repeatable(tmp_path):
    codex = tmp_path / ".codex"
    claude = tmp_path / ".claude"
    codex.mkdir()
    claude.mkdir()
    config = "[features]\nhooks = true\nother_feature = true\n"
    (codex / "config.toml").write_text(config)
    (codex / "AGENTS.md").write_text(install.splice("Network rules.\n", "Always use staff."))
    (claude / "CLAUDE.md").write_text(install.splice("User rules.\n", "Always use staff."))
    (codex / "hooks.json").write_text(
        json.dumps(
            {
                "hooks": {
                    "UserPromptSubmit": [
                        {"hooks": [{"command": "python /old/agentic_staff.py --hook"}]},
                        {"hooks": [{"command": "/bin/other-hook"}]},
                    ]
                }
            }
        )
    )
    install.apply(tmp_path)
    first = {
        name: (codex / name).read_text() for name in ["AGENTS.md", "hooks.json", "config.toml"]
    }
    install.apply(tmp_path)
    assert first == {name: (codex / name).read_text() for name in first}
    assert first["config.toml"] == config
    assert "Always use staff" not in first["AGENTS.md"]
    assert first["AGENTS.md"].startswith("Network rules.")
    assert (claude / "CLAUDE.md").read_text().startswith("User rules.")
    hooks = json.loads(first["hooks.json"])["hooks"]["UserPromptSubmit"]
    assert hooks == [{"hooks": [{"command": "/bin/other-hook"}]}]
    assert (codex / "skills/staff").resolve() == install.ROOT / "skills/staff"


def test_fresh_install_creates_no_prompt_hook_or_hook_feature(tmp_path):
    install.apply(tmp_path)
    assert not (tmp_path / ".codex/hooks.json").exists()
    assert not (tmp_path / ".codex/config.toml").exists()
