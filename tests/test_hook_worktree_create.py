"""hook_worktree_create.py (WorktreeCreate provider) のテスト。

契約: 成功 = exit 0 + stdout に作成した worktree のパス。失敗 = 非ゼロ exit。
"""

import json
import subprocess
import sys
from pathlib import Path

HOOK = Path(__file__).parent.parent / "hooks" / "scripts" / "hook_worktree_create.py"


def init_repo(path: Path) -> None:
    def run(*args: str) -> None:
        subprocess.run(["git", *args], cwd=path, check=True, capture_output=True)
    run("init", "-q")
    run("config", "user.email", "test@example.com")
    run("config", "user.name", "Test")
    (path / "README.md").write_text("init\n", encoding="utf-8")
    run("add", "README.md")
    run("commit", "-q", "-m", "init")


def run_hook(payload: dict, cwd: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(HOOK)], input=json.dumps(payload),
        capture_output=True, text=True, cwd=cwd, timeout=30,
        env={"CLAUDE_PROJECT_DIR": str(cwd), "PATH": "/usr/bin:/bin"},
    )


def test_creates_worktree_and_echoes_path(tmp_path):
    init_repo(tmp_path)
    result = run_hook(
        {"cwd": str(tmp_path), "worktree_name": "issue-42", "source_ref": "HEAD",
         "hook_event_name": "WorktreeCreate", "session_id": "s"},
        tmp_path,
    )
    assert result.returncode == 0, result.stderr
    out_path = Path(result.stdout.strip())
    assert out_path == tmp_path / ".agents" / "worktree" / "issue-42"
    assert (out_path / ".git").exists()
    assert (out_path / "README.md").exists()


def test_reuses_existing_worktree(tmp_path):
    init_repo(tmp_path)
    payload = {"cwd": str(tmp_path), "worktree_name": "reuse-me",
               "hook_event_name": "WorktreeCreate", "session_id": "s"}
    first = run_hook(payload, tmp_path)
    second = run_hook(payload, tmp_path)
    assert first.returncode == 0 and second.returncode == 0
    assert first.stdout.strip() == second.stdout.strip()


def test_legacy_name_field_fallback(tmp_path):
    init_repo(tmp_path)
    result = run_hook(
        {"cwd": str(tmp_path), "name": "old-shape", "hook_event_name": "WorktreeCreate"},
        tmp_path,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip().endswith(".agents/worktree/old-shape")


def test_name_is_sanitized(tmp_path):
    init_repo(tmp_path)
    result = run_hook(
        {"cwd": str(tmp_path), "worktree_name": "feat/x y", "hook_event_name": "WorktreeCreate"},
        tmp_path,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip().endswith(".agents/worktree/feat-x-y")


def test_non_git_dir_fails_nonzero(tmp_path):
    result = run_hook(
        {"cwd": str(tmp_path), "worktree_name": "nope", "hook_event_name": "WorktreeCreate"},
        tmp_path,
    )
    assert result.returncode != 0
    assert result.stdout.strip() == ""
