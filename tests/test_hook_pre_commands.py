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


def test_recursive_rm_blocked_only_for_irreversible_targets(tmp_path):
    """rm -rf は日常の生成物掃除に使うので全面ブロックしない。
    巻き戻し不能な対象 (/, ~, $HOME, 上位ディレクトリ, 裸の *, .git, .venv) だけ deny する。"""
    for command in [
        "rm -rf /", "rm -rf /*", "rm -rf ~", "rm -rf $HOME/", "rm -rf ..", "rm -rf ../sibling",
        "rm -rf *", "rm -rf ./*", "rm -rf .git", "rm -rf .venv", "rm -fr .git", "rm -r --force .venv",
        "sudo rm -rf /", "cd x && rm -rf ../y", "rm -rf build ..",
    ]:
        reason = pretooluse_deny_reason(run_hook(command, tmp_path))
        assert reason and "巻き戻し不能" in reason, command


def test_recursive_rm_allowed_for_project_artifacts(tmp_path):
    for command in [
        "rm -rf build", "rm -rf node_modules dist", "rm -rf .agents/worktree/x", "rm -rf /tmp/claude-1000/foo",
        "rm -rf ./build", "rm -f file.txt", "rm -rf src/.venv", "rm -rf .git/index.lock", "rm -rf ~/src/proj/build",
        "rm -rf $HOME/.cache/uv", "rm -rf dist/*", "rm -rf .venv-old",
    ]:
        result = run_hook(command, tmp_path)
        assert result.returncode == 0 and pretooluse_deny_reason(result) is None, command


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


def test_uv_transform_denies_with_converted_command(tmp_path):
    """uv_transforms override が有効な場合、素の python 実行は変換提案付きで deny される"""
    rules_dir = tmp_path / ".claude" / "hooks" / "rules"
    rules_dir.mkdir(parents=True)
    (rules_dir / "pre_commands.json").write_text(json.dumps({
        "uv_transforms": [
            {"pattern": "^python ", "transform": "s/^python /uv run python /"}
        ]
    }), encoding="utf-8")
    result = run_hook("python script.py", tmp_path)
    reason = pretooluse_deny_reason(result)
    assert reason and "uv run python script.py" in reason


def _init_repo(path):
    def git(*args):
        subprocess.run(["git", *args], cwd=path, check=True, capture_output=True)
    git("init", "-q")
    git("config", "user.email", "test@example.com")
    git("config", "user.name", "Test")
    git("checkout", "-q", "-b", "main")
    (path / "README.md").write_text("init\n", encoding="utf-8")
    git("add", "README.md")
    git("commit", "-q", "-m", "init")
    return git


def test_branch_force_delete_allows_integrated_branch(tmp_path):
    """base の祖先になっている (マージ済み) ブランチの -D は許可される"""
    git = _init_repo(tmp_path)
    git("branch", "merged-branch")  # main と同一コミット = ancestor
    result = run_hook("git branch -D merged-branch", tmp_path)
    assert result.returncode == 0
    assert pretooluse_deny_reason(result) is None


def test_branch_force_delete_blocks_unmerged_branch(tmp_path):
    """base へ未統合の固有コミットを持つブランチの -D はブロックされる"""
    git = _init_repo(tmp_path)
    git("checkout", "-q", "-b", "wip-branch")
    (tmp_path / "wip.txt").write_text("wip\n", encoding="utf-8")
    git("add", "wip.txt")
    git("commit", "-q", "-m", "wip")
    git("checkout", "-q", "main")
    result = run_hook("git branch -D wip-branch", tmp_path)
    reason = pretooluse_deny_reason(result)
    assert reason and "wip-branch" in reason


def test_branch_delete_mention_in_message_not_blocked(tmp_path):
    """commit message 内の 'git branch -D' 文字列には反応しない"""
    _init_repo(tmp_path)
    result = run_hook('git commit -m "docs: explain git branch -D usage"', tmp_path)
    assert result.returncode == 0
    assert pretooluse_deny_reason(result) is None


def _load_hook_module():
    sys.path.insert(0, str(HOOK.parent))
    import hook_pre_commands
    return hook_pre_commands


def test_branch_force_delete_denies_when_integration_check_runs_out_of_time(tmp_path, monkeypatch):
    """起動処理で時間を使い、gh も応答しなくても、登録 timeout 前に判定を打ち切って拒否する (fail-open させない)"""
    import os
    import time
    hook = _load_hook_module()
    repo = tmp_path / "repo"
    repo.mkdir()
    git = _init_repo(repo)
    git("checkout", "-q", "-b", "squashed-elsewhere")
    (repo / "x.txt").write_text("x\n", encoding="utf-8")
    git("add", "x.txt")
    git("commit", "-q", "-m", "x")
    git("checkout", "-q", "main")
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    fake_gh = bin_dir / "gh"
    fake_gh.write_text("#!/bin/sh\nexec sleep 30\n", encoding="utf-8")
    fake_gh.chmod(0o755)
    monkeypatch.setenv("PATH", f"{bin_dir}{os.pathsep}{os.environ['PATH']}")
    monkeypatch.chdir(repo)
    monkeypatch.setattr(hook, "LOG_DIR", tmp_path / "logs")
    # 起動入口の git 呼び出しなどで、締め切りまで残り 1 秒になったところから判定が始まる。
    spent = hook.REGISTERED_TIMEOUT_SECONDS - hook.TIMEOUT_MARGIN_SECONDS - 1
    monkeypatch.setenv("AGENT_KIT_STARTED", repr(time.monotonic() - spent))
    started = time.monotonic()
    reason = hook.check_branch_force_delete("git branch -D squashed-elsewhere")
    assert time.monotonic() - started < 3
    assert reason and "squashed-elsewhere" in reason
    assert "制限時間" in reason


def test_integration_deadline_counts_from_process_start(monkeypatch):
    """締め切りは起動入口が記録した起動時刻から数え、記録が無い・不正なら module の読み込み時刻から数える"""
    import time
    hook = _load_hook_module()
    window = hook.REGISTERED_TIMEOUT_SECONDS - hook.TIMEOUT_MARGIN_SECONDS
    now = time.monotonic()
    monkeypatch.setattr(hook, "IMPORTED_AT", now)
    monkeypatch.setenv("AGENT_KIT_STARTED", repr(now - 4))
    assert abs(hook._integration_deadline() - (now - 4 + window)) < 0.01
    for invalid in ("broken", repr(now + 60), repr(now - 3600)):
        monkeypatch.setenv("AGENT_KIT_STARTED", invalid)
        assert abs(hook._integration_deadline() - (now + window)) < 0.01, invalid
    monkeypatch.delenv("AGENT_KIT_STARTED")
    assert abs(hook._integration_deadline() - (now + window)) < 0.01


def test_registered_timeout_matches_both_clients():
    """hook が想定する登録 timeout は、Claude と Codex の実際の登録値と一致する"""
    hook = _load_hook_module()
    sys.path.insert(0, str(HOOK.parents[2] / "scripts"))
    from install_harness import CODEX_HOOKS
    plugin = json.loads((HOOK.parents[1] / "hooks.json").read_text(encoding="utf-8"))
    claude_timeout = next(handler["timeout"] for group in plugin["hooks"]["PreToolUse"]
                          for handler in group["hooks"] if "hook_pre_commands.py" in handler["args"])
    codex_timeout = next(timeout for _, _, script, timeout in CODEX_HOOKS if script == "hook_pre_commands.py")
    assert claude_timeout == codex_timeout == hook.REGISTERED_TIMEOUT_SECONDS
    assert 0 < hook.TIMEOUT_MARGIN_SECONDS < hook.REGISTERED_TIMEOUT_SECONDS
