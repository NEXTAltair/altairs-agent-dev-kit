"""Runtime contracts on native Windows and Linux, including linked worktrees."""

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "hooks/scripts"))
import hook_common
import hook_pre_commands
import hook_response_monitor

SCRIPTS = Path(__file__).resolve().parents[1] / "hooks/scripts"


def run_hook(name, payload, cwd):
    return subprocess.run(
        [sys.executable, "-X", "utf8", str(SCRIPTS / f"{name}.py")],
        input=json.dumps(payload), cwd=cwd, capture_output=True, text=True,
        encoding="utf-8", timeout=30,
        env={**os.environ, "AGENT_KIT_PROJECT_DIR": str(cwd), "PYTHONUTF8": "1"},
    )


def git(cwd, *arguments):
    return subprocess.run(
        ["git", *arguments], cwd=cwd, check=True, capture_output=True,
        text=True, encoding="utf-8", timeout=30,
    )


def init_repo(root):
    root.mkdir()
    git(root, "init", "-q")
    git(root, "-c", "user.name=Test", "-c", "user.email=test@example.com", "commit", "--allow-empty", "-m", "init")


def test_shared_root_from_unicode_linked_worktree(tmp_path):
    root = tmp_path / "日本語 repo"
    init_repo(root)
    worktree = root / ".agents/worktree/child"
    git(root, "worktree", "add", "--detach", str(worktree))
    assert hook_common.find_shared_root(worktree) == root.resolve()


def test_worktree_provider_uses_shared_root_from_nested_worktree(tmp_path):
    root = tmp_path / "日本語 repo"
    init_repo(root)
    child = root / ".agents/worktree/first"
    git(root, "worktree", "add", "--detach", str(child))
    result = run_hook("hook_worktree_create", {"cwd": str(child), "worktree_name": "second"}, child)
    assert result.returncode == 0, result.stderr
    assert Path(result.stdout.strip()) == root / ".agents/worktree/second"


def test_project_override_and_provider_log_directory(tmp_path, monkeypatch):
    monkeypatch.setenv("AGENT_KIT_PROJECT_DIR", str(tmp_path))
    monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(tmp_path / "wrong"))
    monkeypatch.setenv("AGENT_KIT_PROVIDER", "codex")
    assert hook_common.find_project_root() == tmp_path
    assert hook_common.get_log_dir(tmp_path) == tmp_path / ".codex/logs"


def test_codex_cmd_field_receives_unicode_permission_deny(tmp_path):
    result = run_hook("hook_pre_commands", {"tool_input": {"cmd": "git reset --hard"}}, tmp_path)
    assert result.returncode == 0, result.stderr
    decision = json.loads(result.stdout)["hookSpecificOutput"]
    assert decision["permissionDecision"] == "deny"
    assert "危険" in decision["permissionDecisionReason"]


def test_stop_direct_message_takes_precedence():
    assert hook_response_monitor.extract_response_content({"last_assistant_message": "日本語"}) == "日本語"


def test_stop_reentry_does_not_block_again(tmp_path):
    result = run_hook("hook_response_monitor", {"stop_hook_active": True, "last_assistant_message": "推測"}, tmp_path)
    assert result.returncode == 0, result.stderr
    assert result.stdout == ""


def test_shared_venv_normalizes_native_separators(tmp_path, monkeypatch):
    monkeypatch.setattr(hook_pre_commands, "SHARED_UV_ENV_VALUE", str(tmp_path / ".venv"))
    monkeypatch.setenv("UV_PROJECT_ENVIRONMENT", (tmp_path / ".venv").as_posix())
    assert hook_pre_commands._has_shared_uv_environment("uv run pytest")
    monkeypatch.setenv("UV_PROJECT_ENVIRONMENT", str(tmp_path / "wrong"))
    assert not hook_pre_commands._has_shared_uv_environment("uv run pytest")


@pytest.mark.skipif(os.name != "nt", reason="Windows command path escaping")
def test_windows_cd_preserves_backslashes(tmp_path, monkeypatch):
    root = tmp_path / "space repo" / ".agents/worktree"
    monkeypatch.setattr(hook_pre_commands, "WORKTREE_ROOT", root.resolve())
    assert hook_pre_commands._command_cd_worktree(f'cd "{root / "child"}"; uv run pytest')
