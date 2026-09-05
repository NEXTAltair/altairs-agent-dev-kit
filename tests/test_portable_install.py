"""Exercise installed hooks on Windows and Linux, including nested working directories."""

import json
import os
import subprocess
import sys
from pathlib import Path

KIT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(KIT / "scripts"))
from install_harness import install  # noqa: E402


def test_installed_launchers_and_overrides(tmp_path):
    target = tmp_path / "project space 日本語"
    target.mkdir()
    subprocess.run(["git", "init", str(target)], check=True, capture_output=True)
    rules = target / ".claude/hooks/rules/pre_commands.json"
    rules.parent.mkdir(parents=True)
    rules.write_text(
        '{"blocked_commands": [{"pattern": "^forbidden", "reason": "project policy"}]}', encoding="utf-8"
    )
    wiring = install(target, force=True, codex=True)
    assert "project policy" in rules.read_text(encoding="utf-8")
    assert target.as_posix() in (target / ".codex/config.toml").read_text(encoding="utf-8")
    nested = target / "nested"
    nested.mkdir()
    subprocess.run(
        [
            "git",
            "-C",
            str(target),
            "-c",
            "user.name=Test",
            "-c",
            "user.email=test@example.com",
            "commit",
            "--allow-empty",
            "-m",
            "init",
        ],
        check=True,
        capture_output=True,
    )
    worktree = target / ".agents/worktree/fresh"
    subprocess.run(
        ["git", "-C", str(target), "worktree", "add", "--detach", str(worktree)],
        check=True,
        capture_output=True,
    )
    assert not (worktree / ".claude/hooks/hook_common.py").exists()
    worktree_rules = worktree / ".claude/hooks/rules/pre_commands.json"
    worktree_rules.parent.mkdir(parents=True)
    worktree_rules.write_text(rules.read_text(encoding="utf-8"), encoding="utf-8")
    codex = json.loads((target / ".codex/hooks.json").read_text(encoding="utf-8"))
    assert "WorktreeCreate" not in codex["hooks"]
    for provider, config, cwd in (
        (p, c, d) for p, c in (("claude", wiring), ("codex", codex)) for d in (nested, worktree)
    ):
        for event in ("PreToolUse", "Stop"):
            handler = config["hooks"][event][0]["hooks"][0]
            if provider == "claude":
                command = [
                    handler["command"],
                    *[arg.replace("${CLAUDE_PROJECT_DIR}", str(target)) for arg in handler["args"]],
                ]
            elif os.name == "nt":
                command = ["powershell", "-NoProfile", "-Command", handler["commandWindows"]]
            else:
                command = ["sh", "-c", handler["command"]]
            payload = {
                "cwd": str(cwd),
                "hook_event_name": event,
                "tool_name": "Bash",
                "tool_input": {"command": "forbidden"},
                "last_assistant_message": "確認しました",
                "stop_hook_active": True,
            }
            result = subprocess.run(
                command,
                input=json.dumps(payload),
                cwd=cwd,
                env=dict(os.environ, CLAUDE_PROJECT_DIR=str(target)),
                text=True,
                encoding="utf-8",
                capture_output=True,
                timeout=20,
            )
            assert result.returncode == 0, result.stderr
            if event == "PreToolUse":
                assert json.loads(result.stdout)["hookSpecificOutput"]["permissionDecision"] == "deny"


def test_reinstall_keeps_existing_config(tmp_path):
    install(tmp_path)
    config = tmp_path / ".codex/hooks.json"
    config.write_text('{"custom": true}', encoding="utf-8")
    install(tmp_path)
    assert json.loads(config.read_text(encoding="utf-8")) == {"custom": True}
    assert (tmp_path / ".codex/hooks.json.new").exists()
