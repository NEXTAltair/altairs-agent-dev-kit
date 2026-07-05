import json
import subprocess
import sys
from pathlib import Path

from conftest import pretooluse_deny_reason

HOOK = Path(__file__).parent.parent / "hooks" / "scripts" / "hook_pre_commands.py"


def run_hook(command: str, cwd: Path, extra_env: dict | None = None) -> subprocess.CompletedProcess:
    payload = json.dumps({"tool_name": "Bash", "tool_input": {"command": command}})
    env = {"CLAUDE_PROJECT_DIR": str(cwd), "PATH": "/usr/bin:/bin"}
    if extra_env:
        env.update(extra_env)
    return subprocess.run(
        [sys.executable, str(HOOK)], input=payload,
        capture_output=True, text=True, cwd=cwd, timeout=10,
        env=env,
    )


def test_git_reset_hard_blocked(tmp_path):
    result = run_hook("git reset --hard HEAD~1", tmp_path)
    reason = pretooluse_deny_reason(result)
    assert reason and "危険" in reason


def test_normal_command_allowed(tmp_path):
    result = run_hook("ls -la", tmp_path)
    assert result.returncode == 0
    assert pretooluse_deny_reason(result) is None


def test_project_override_adds_block(tmp_path):
    rules_dir = tmp_path / ".claude" / "hooks" / "rules"
    rules_dir.mkdir(parents=True)
    (rules_dir / "pre_commands.json").write_text(
        json.dumps({"blocked_commands": [
            {"pattern": "^pip ", "reason": "pip 禁止", "suggestion": "uv add"}
        ]}), encoding="utf-8")
    result = run_hook("pip install requests", tmp_path)
    reason = pretooluse_deny_reason(result)
    assert reason and "pip" in reason


def test_draft_pr_blocked_by_default(tmp_path):
    result = run_hook("gh pr create --draft --title x", tmp_path)
    reason = pretooluse_deny_reason(result)
    assert reason and "draft" in reason


def test_draft_pr_allowed_when_disabled(tmp_path):
    rules_dir = tmp_path / ".claude" / "hooks" / "rules"
    rules_dir.mkdir(parents=True)
    (rules_dir / "pre_commands.json").write_text(
        json.dumps({"block_draft_pr": False}), encoding="utf-8")
    result = run_hook("gh pr create --draft --title x", tmp_path)
    assert result.returncode == 0
    assert pretooluse_deny_reason(result) is None


def test_worktree_uv_guard_blocks_bare_uv(tmp_path):
    rules_dir = tmp_path / ".claude" / "hooks" / "rules"
    rules_dir.mkdir(parents=True)
    (rules_dir / "pre_commands.json").write_text(
        json.dumps({"worktree_uv_guard": True}), encoding="utf-8")
    worktree_dir = tmp_path / ".agents" / "worktree" / "wt1"
    worktree_dir.mkdir(parents=True)
    result = run_hook(
        "uv run pytest", worktree_dir,
        extra_env={"CLAUDE_PROJECT_DIR": str(tmp_path)},
    )
    reason = pretooluse_deny_reason(result)
    assert reason and "worktree" in reason
