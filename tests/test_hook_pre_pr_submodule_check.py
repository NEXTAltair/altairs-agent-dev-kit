import json
import subprocess
import sys
from pathlib import Path

from conftest import pretooluse_deny_reason

HOOK = Path(__file__).parent.parent / "hooks" / "scripts" / "hook_pre_pr_submodule_check.py"


def run_hook(command: str, cwd: Path) -> subprocess.CompletedProcess:
    payload = json.dumps({"tool_name": "Bash", "tool_input": {"command": command}})
    return subprocess.run(
        [sys.executable, str(HOOK)], input=payload,
        capture_output=True, text=True, cwd=cwd, timeout=10,
        env={"CLAUDE_PROJECT_DIR": str(cwd), "PATH": "/usr/bin:/bin"},
    )


def _init_repo_with_submodule_change(tmp_path: Path) -> None:
    """origin/main へ到達可能な、submodule 風パス変更を含むミニ git repo を作る。

    実際の remote は使わず、origin/main の ref だけを HEAD~1 に向けて作る
    (ci-equiv-check は `git diff --name-only origin/main...HEAD` しか見ないため十分)。
    """
    def run(*args: str) -> None:
        subprocess.run(["git", *args], cwd=tmp_path, check=True, capture_output=True)

    run("init", "-q")
    run("config", "user.email", "test@example.com")
    run("config", "user.name", "Test")
    run("checkout", "-q", "-b", "main")
    (tmp_path / "README.md").write_text("init\n", encoding="utf-8")
    run("add", "README.md")
    run("commit", "-q", "-m", "init")
    run("update-ref", "refs/remotes/origin/main", "HEAD")

    pkg_dir = tmp_path / "local_packages" / "foo"
    pkg_dir.mkdir(parents=True)
    (pkg_dir / "bar.py").write_text("x = 1\n", encoding="utf-8")
    run("add", "local_packages/foo/bar.py")
    run("commit", "-q", "-m", "change submodule")


def test_no_globs_allows_by_default(tmp_path):
    """submodule_globs が空 (default) なら git repo すら不要で即 exit 0"""
    result = run_hook("gh pr create --title x", tmp_path)
    assert result.returncode == 0


def test_non_gh_pr_create_command_allowed(tmp_path):
    result = run_hook("git status", tmp_path)
    assert result.returncode == 0


def test_override_globs_blocks_submodule_change(tmp_path):
    rules_dir = tmp_path / ".claude" / "hooks" / "rules"
    rules_dir.mkdir(parents=True)
    (rules_dir / "pre_pr_submodule_check.json").write_text(json.dumps({
        "submodule_globs": ["local_packages/*"]
    }), encoding="utf-8")
    _init_repo_with_submodule_change(tmp_path)

    result = run_hook('gh pr create --title "x" --body "y"', tmp_path)
    reason = pretooluse_deny_reason(result)
    assert reason and "local_packages/foo" in reason


def test_bypass_marker_allows_submodule_change(tmp_path):
    rules_dir = tmp_path / ".claude" / "hooks" / "rules"
    rules_dir.mkdir(parents=True)
    (rules_dir / "pre_pr_submodule_check.json").write_text(json.dumps({
        "submodule_globs": ["local_packages/*"]
    }), encoding="utf-8")
    _init_repo_with_submodule_change(tmp_path)

    result = run_hook(
        'gh pr create --title "CI-EQUIV-TESTED: ran pytest -> 3 passed" --body "y"', tmp_path
    )
    assert result.returncode == 0


def test_override_globs_allows_unrelated_change(tmp_path):
    rules_dir = tmp_path / ".claude" / "hooks" / "rules"
    rules_dir.mkdir(parents=True)
    (rules_dir / "pre_pr_submodule_check.json").write_text(json.dumps({
        "submodule_globs": ["local_packages/*"]
    }), encoding="utf-8")

    def run(*args: str) -> None:
        subprocess.run(["git", *args], cwd=tmp_path, check=True, capture_output=True)

    run("init", "-q")
    run("config", "user.email", "test@example.com")
    run("config", "user.name", "Test")
    run("checkout", "-q", "-b", "main")
    (tmp_path / "README.md").write_text("init\n", encoding="utf-8")
    run("add", "README.md")
    run("commit", "-q", "-m", "init")
    run("update-ref", "refs/remotes/origin/main", "HEAD")
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "note.md").write_text("note\n", encoding="utf-8")
    run("add", "docs/note.md")
    run("commit", "-q", "-m", "docs change")

    result = run_hook('gh pr create --title "x" --body "y"', tmp_path)
    assert result.returncode == 0
