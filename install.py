"""Link the shared skills into Claude, Codex, Pi, and Grok."""

import argparse
import json
import shlex
import shutil
import subprocess
from datetime import datetime
from pathlib import Path

import agentic_staff

ROOT = Path(__file__).resolve().parent
SKILLS = ("staff", "isolated-pr-workflow")
STICKY = (ROOT / "hosts" / "sticky.md").read_text()
MARKER_START = "<!-- agentic-staff:start -->"
MARKER_END = "<!-- agentic-staff:end -->"
HOOK_FILENAMES = {"agentic_staff.py", "agentic-staff.py"}


def splice(text: str, block: str) -> str:
    wrapped = f"{MARKER_START}\n{block.strip()}\n{MARKER_END}\n"
    if MARKER_START in text and MARKER_END in text:
        pre, rest = text.split(MARKER_START, 1)
        _old, post = rest.split(MARKER_END, 1)
        return pre.rstrip() + "\n\n" + wrapped + post.lstrip("\n")
    if text and not text.endswith("\n"):
        text += "\n"
    if text.strip():
        return text + "\n" + wrapped
    return wrapped


def is_staff_hook(command: str) -> bool:
    try:
        words = shlex.split(command)
    except ValueError:
        return False
    return "--hook" in words and any(Path(word).name in HOOK_FILENAMES for word in words)


def remove_staff_hooks(existing: dict) -> dict:
    """Migrate automatic staff installs without disabling other tools' hooks."""
    payload = existing if isinstance(existing, dict) else {}
    hooks = payload.get("hooks", {})
    if "UserPromptSubmit" not in hooks:
        return payload
    kept_groups = []
    for group in hooks["UserPromptSubmit"]:
        previous = group.get("hooks", [])
        kept = [hook for hook in previous if not is_staff_hook(hook.get("command", ""))]
        if kept or not previous:
            group["hooks"] = kept
            kept_groups.append(group)
    hooks["UserPromptSubmit"] = kept_groups
    return payload


def link_skill(name: str, dest_root: Path) -> None:
    dest_root.mkdir(parents=True, exist_ok=True)
    dest = dest_root / name
    src = ROOT / "skills" / name
    if dest.exists() and not dest.is_symlink():
        stamp = datetime.now().strftime("%Y%m%d%H%M%S")
        dest.rename(dest_root / f"{name}.pre-staff-{stamp}")
    elif dest.is_symlink() or dest.exists():
        dest.unlink()
    dest.symlink_to(src)


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)


def apply(home: Path | None = None) -> None:
    home = home or Path.home()
    for skills_dir in (
        home / ".claude" / "skills",
        home / ".codex" / "skills",
        home / ".grok" / "skills",
    ):
        for name in SKILLS:
            link_skill(name, skills_dir)

    link_skill("staff-graph", home / ".codex" / "skills")

    sticky_targets = (
        home / ".grok" / "rules" / "staff.md",
        home / ".claude" / "rules" / "staff.md",
    )
    for target in sticky_targets:
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.is_symlink() or target.exists():
            target.unlink()
        target.symlink_to(ROOT / "hosts" / "sticky.md")

    claude_md = home / ".claude" / "CLAUDE.md"
    claude_text = claude_md.read_text() if claude_md.exists() else ""
    write_text(claude_md, splice(claude_text, STICKY))
    codex_agents = home / ".codex" / "AGENTS.md"
    codex_text = codex_agents.read_text() if codex_agents.exists() else ""
    write_text(codex_agents, splice(codex_text, STICKY))

    hooks_path = home / ".codex" / "hooks.json"
    if hooks_path.exists():
        existing = json.loads(hooks_path.read_text())
        hooks_path.write_text(json.dumps(remove_staff_hooks(existing), indent=2) + "\n")

    agent_dir = home / ".codex" / "agents"
    agent_dir.mkdir(parents=True, exist_ok=True)
    for name, body in agentic_staff.codex_agent_files().items():
        (agent_dir / f"{name}.toml").write_text(body)

    pi = shutil.which("pi")
    if pi and home == Path.home():
        subprocess.run([pi, "install", str(ROOT)], check=False)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--home", type=Path)
    args = parser.parse_args()
    apply(args.home or Path.home())


if __name__ == "__main__":
    main()
