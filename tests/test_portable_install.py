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
    (nested / "json.py").write_text("raise RuntimeError('cwd must not shadow stdlib')", encoding="utf-8")
    subprocess.run(["git", "-C", str(target), "add", ".agent-kit/hooks.lock.json"], check=True)
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


def test_runtime_failures_and_consumer_startup(tmp_path):
    from install_harness import hook_bootstrap, install_runtime
    target = tmp_path / "日本語 project"
    target.mkdir()
    subprocess.run(["git", "init", str(target)], check=True, capture_output=True)
    install_runtime(target)
    consumer = target / ".claude/hooks/teammate.py"
    consumer.parent.mkdir(parents=True)
    consumer.write_text(
        "from hook_common import find_project_root\nprint(find_project_root())\n", encoding="utf-8"
    )

    def run(script="hook_pre_commands.py", event="PreToolUse", custom=False, cwd=target):
        return subprocess.run(
            [sys.executable, "-X", "utf8", "-c", hook_bootstrap(script, event=event, consumer=custom)],
            input='{"tool_input":{"command":"git reset --hard"}}', cwd=cwd,
            capture_output=True, text=True, encoding="utf-8", timeout=20,
        )

    result = run(".claude/hooks/teammate.py", "TeammateIdle", True)
    assert result.returncode == 0, result.stderr
    assert Path(result.stdout.strip()) == target.resolve()
    assert not list((target / ".agent-kit/runtimes").rglob("__pycache__"))
    lock_path = target / ".agent-kit/hooks.lock.json"
    original = lock_path.read_text(encoding="utf-8")
    for damaged in ("{}", "[]", '{"runtime":123}',
                    '{"schema":1,"runtime":"' + "0" * 64 + '"}', "broken"):
        lock_path.write_text(damaged, encoding="utf-8")
        for event in ("PreToolUse", "Stop", "TeammateIdle", "WorktreeCreate"):
            result = run(event=event)
            assert "agent-kit runtime unavailable" in result.stderr
            if event == "PreToolUse":
                assert json.loads(result.stdout)["hookSpecificOutput"]["permissionDecision"] == "deny"
            elif event == "Stop":
                assert json.loads(result.stdout)["decision"] == "block"
            else:
                assert result.returncode == 2
    lock_path.write_text(original, encoding="utf-8")
    lock = json.loads(original)
    runtime = target / ".agent-kit/runtimes" / lock["runtime"]
    import importlib.util
    import py_compile
    malicious = tmp_path / "cached.py"
    malicious.write_text("raise RuntimeError('unverified bytecode')", encoding="utf-8")
    cache = importlib.util.cache_from_source(str(runtime / "hooks/scripts/hook_common.py"))
    py_compile.compile(str(malicious), cfile=cache, doraise=True,
                       invalidation_mode=py_compile.PycInvalidationMode.UNCHECKED_HASH)
    assert json.loads(run().stdout)["hookSpecificOutput"]["permissionDecision"] == "deny"
    (runtime / "hooks/rules/pre_commands.default.json").unlink()
    assert "runtime unavailable" in run().stderr
    # Non-repository startup must not silently use cwd as a valid root.
    assert "runtime unavailable" in run(cwd=tmp_path).stderr


def test_atomic_restore_and_branch_versions(tmp_path, monkeypatch):
    import shutil
    import pytest
    import install_harness as installer

    target = tmp_path / "main"
    target.mkdir()
    def git(*args):
        return subprocess.run(["git", "-C", str(target), *args], check=True, capture_output=True)
    git("init")
    old = installer.install_runtime(target)
    git("add", ".agent-kit/hooks.lock.json")
    git("-c", "user.name=Test", "-c", "user.email=test@example.com", "commit", "-m", "pin")
    child = target / ".agents/worktree/日本語 branch"
    git("worktree", "add", "--detach", str(child))
    # A tracked adapter/rules directory must not shadow the selected shared runtime.
    adapter = child / ".codex/hooks/hook_pre_commands.py"
    adapter.parent.mkdir(parents=True)
    adapter.write_text("raise RuntimeError('stale adapter')", encoding="utf-8")
    rules = child / ".claude/hooks/rules/pre_edit_worktree.json"
    rules.parent.mkdir(parents=True)
    rules.write_text('{"protected_dirs":["branch-only"]}', encoding="utf-8")
    consumer = child / ".claude/hooks/teammate.py"
    consumer.write_text("import json,sys\nfrom hook_common import find_project_root\n"
                        "print(json.dumps([str(find_project_root()), json.load(sys.stdin)]))\n", encoding="utf-8")
    teammate = subprocess.run(
        [sys.executable, "-I", "-X", "utf8", "-c",
         installer.hook_bootstrap(".claude/hooks/teammate.py", event="TeammateIdle", consumer=True)],
        cwd=child, input='{"teammate_name":"worker"}', text=True, encoding="utf-8", capture_output=True,
    )
    assert teammate.returncode == 0, teammate.stderr
    assert json.loads(teammate.stdout) == [str(child.resolve()), {"teammate_name": "worker"}]
    new_source = tmp_path / "source"
    shutil.copytree(KIT / "hooks", new_source / "hooks")
    default = new_source / "hooks/rules/pre_commands.default.json"
    data = json.loads(default.read_text(encoding="utf-8"))
    data["blocked_commands"].append({"pattern": "^new-version-only$", "reason": "new runtime"})
    default.write_text(json.dumps(data), encoding="utf-8")
    monkeypatch.setattr(installer, "KIT", new_source)
    copy = installer.shutil.copyfile
    def interrupted(source, destination):
        copy(source, destination)
        raise OSError("simulated interrupted copy")
    with monkeypatch.context() as patch:
        patch.setattr(installer.shutil, "copyfile", interrupted)
        with pytest.raises(OSError, match="interrupted"):
            installer.install_runtime(target, force=True)
    assert json.loads((target / ".agent-kit/hooks.lock.json").read_text()) == old
    installer.validate(target / ".agent-kit/runtimes" / old["runtime"], old)
    new = installer.install_runtime(target, force=True)
    assert new["runtime"] != old["runtime"]
    for cwd, blocked in ((target, True), (child, False)):
        result = subprocess.run(
            [sys.executable, "-X", "utf8", "-c", installer.hook_bootstrap("hook_pre_commands.py")],
            cwd=cwd, input='{"tool_input":{"command":"new-version-only"}}',
            text=True, encoding="utf-8", capture_output=True, timeout=20,
        )
        assert result.returncode == 0, result.stderr
        assert bool(result.stdout.strip()) == blocked
    result = subprocess.run(
        [sys.executable, "-X", "utf8", "-c", installer.hook_bootstrap("hook_pre_edit_worktree.py")],
        cwd=child, input=json.dumps({"tool_input": {"file_path": str(target / "branch-only/file.py")}}),
        text=True, encoding="utf-8", capture_output=True, timeout=20,
    )
    assert json.loads(result.stdout)["hookSpecificOutput"]["permissionDecision"] == "deny"
    with pytest.raises(ValueError, match="source differs"):
        installer.install_runtime(child)


def test_reinstall_keeps_existing_config(tmp_path):
    install(tmp_path)
    config = tmp_path / ".codex/hooks.json"
    config.write_text('{"custom": true}', encoding="utf-8")
    install(tmp_path)
    assert json.loads(config.read_text(encoding="utf-8")) == {"custom": True}
    assert (tmp_path / ".codex/hooks.json.new").exists()


def test_plugin_and_all_registered_events(tmp_path):
    from install_harness import claude_wiring, install_runtime
    target = tmp_path / "plugin 日本語"
    target.mkdir()
    def git(*args):
        subprocess.run(["git", "-C", str(target), *args], check=True, capture_output=True)
    git("init")
    lock = install_runtime(target)
    git("add", ".agent-kit/hooks.lock.json")
    git("-c", "user.name=Test", "-c", "user.email=test@example.com", "commit", "-m", "pin")
    rules = target / ".claude/hooks/rules"
    rules.mkdir(parents=True)
    (rules / "response_monitor.json").write_text(
        '{"ng_words":[{"keyword":"forbiddenword","message":"project rule"}]}', encoding="utf-8"
    )
    plugin = json.loads((KIT / "hooks/hooks.json").read_text(encoding="utf-8"))
    # Make the restored runtime unavailable: plugin source must supply the exact lock.
    runtime = target / ".agent-kit/runtimes" / lock["runtime"]
    saved = runtime.with_name("saved")
    runtime.rename(saved)
    for config, prefix in ((plugin, "plugin"), (claude_wiring(), "restored")):
        if prefix == "restored":
            saved.rename(runtime)
        for event, groups in config["hooks"].items():
            for group in groups:
                for handler in group["hooks"]:
                    args = [arg.replace("${CLAUDE_PLUGIN_ROOT}", str(KIT)) for arg in handler["args"]]
                    payload = {"tool_input": {"command": "git reset --hard", "file_path": str(target / "src/a.py")},
                               "last_assistant_message": "forbiddenword", "worktree_name": prefix}
                    result = subprocess.run(
                        [sys.executable, *args], cwd=target, input=json.dumps(payload),
                        text=True, encoding="utf-8", capture_output=True, timeout=30,
                    )
                    assert result.returncode == 0, result.stderr
                    assert "runtime unavailable" not in result.stderr
                    if event == "Stop":
                        assert json.loads(result.stdout)["decision"] == "block"
                    elif event == "WorktreeCreate":
                        assert Path(result.stdout.strip()).is_dir()
                    elif group.get("matcher") == "Edit|Write|MultiEdit":
                        assert json.loads(result.stdout)["hookSpecificOutput"]["permissionDecision"] == "deny"


def test_concurrent_shared_restore(tmp_path):
    from concurrent.futures import ThreadPoolExecutor
    from install_harness import install_runtime, validate
    target = tmp_path / "main"
    target.mkdir()
    def git(*args):
        subprocess.run(["git", "-C", str(target), *args], check=True, capture_output=True)
    git("init")
    git("-c", "user.name=Test", "-c", "user.email=test@example.com", "commit", "--allow-empty", "-m", "init")
    child = target / ".agents/worktree/child"
    git("worktree", "add", "--detach", str(child))
    with ThreadPoolExecutor(max_workers=2) as pool:
        locks = list(pool.map(install_runtime, (target, child)))
    assert locks[0] == locks[1]
    validate(target / ".agent-kit/runtimes" / locks[0]["runtime"], locks[0])
    for checkout in (target, child):
        assert json.loads((checkout / ".agent-kit/hooks.lock.json").read_text()) == locks[0]


def test_tracked_adapter_and_consumer_use_branch_runtime(tmp_path):
    from install_harness import hook_bootstrap, install_runtime

    target = tmp_path / "main 日本語"
    target.mkdir()

    def git(*args):
        subprocess.run(["git", "-C", str(target), *args], check=True, capture_output=True)

    git("init")
    lock = install_runtime(target)
    consumer = target / ".claude/hooks/teammate.py"
    consumer.parent.mkdir(parents=True)
    consumer.write_text(
        "import sys\nfrom hook_common import find_project_root\n"
        "print(find_project_root())\nprint(sys.stdin.read())\n", encoding="utf-8"
    )
    adapter = target / ".codex/hooks/hook_pre_commands.py"
    adapter.parent.mkdir(parents=True)
    adapter.write_text("raise RuntimeError('legacy adapter must not run')\n", encoding="utf-8")
    git("add", ".agent-kit/hooks.lock.json", ".claude/hooks/teammate.py", ".codex/hooks")
    git("-c", "user.name=Test", "-c", "user.email=test@example.com", "commit", "-m", "pin")
    child = target / ".agents/worktree/child space"
    git("worktree", "add", "--detach", str(child))
    nested = child / "nested"
    nested.mkdir()

    def run(script, event="PreToolUse", custom=False):
        return subprocess.run(
            [sys.executable, "-I", "-X", "utf8", "-c",
             hook_bootstrap(script, provider="codex", event=event, consumer=custom)],
            cwd=nested, input="payload 日本語", capture_output=True, text=True,
            encoding="utf-8", timeout=20,
        )

    result = run(".claude/hooks/teammate.py", "TeammateIdle", True)
    assert result.returncode == 0, result.stderr
    assert result.stdout.splitlines() == [str(child.resolve()), "payload 日本語"]
    # A tracked adapter is not a runtime, and the parent's lock cannot replace a missing branch pin.
    branch_lock = child / ".agent-kit/hooks.lock.json"
    branch_lock.unlink()
    result = run("hook_pre_commands.py")
    assert "runtime unavailable" in result.stderr
    assert json.loads(result.stdout)["hookSpecificOutput"]["permissionDecision"] == "deny"
    branch_lock.write_text(json.dumps(lock), encoding="utf-8")
    runtime = target / ".agent-kit/runtimes" / lock["runtime"]
    runtime.rename(runtime.with_name("unavailable"))
    result = run(".claude/hooks/teammate.py", "TeammateIdle", True)
    assert result.returncode == 2
    assert "runtime unavailable" in result.stderr
    assert "payload" not in result.stdout
