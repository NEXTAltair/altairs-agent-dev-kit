import json
import subprocess
import sys
from pathlib import Path

HOOK = Path(__file__).parent.parent / "hooks" / "scripts" / "hook_pre_commands.py"


def run_hook(command: str, cwd: Path) -> subprocess.CompletedProcess:
    payload = json.dumps({"tool_name": "Bash", "tool_input": {"command": command}})
    return subprocess.run(
        [sys.executable, str(HOOK)], input=payload,
        capture_output=True, text=True, cwd=cwd, timeout=10,
        env={"CLAUDE_PROJECT_DIR": str(cwd), "PATH": "/usr/bin:/bin"},
    )


def test_git_reset_hard_blocked(tmp_path):
    result = run_hook("git reset --hard HEAD~1", tmp_path)
    assert result.returncode == 2
    assert "危険" in result.stderr


def test_normal_command_allowed(tmp_path):
    result = run_hook("ls -la", tmp_path)
    assert result.returncode == 0


def test_project_override_adds_block(tmp_path):
    rules_dir = tmp_path / ".claude" / "hooks" / "rules"
    rules_dir.mkdir(parents=True)
    (rules_dir / "pre_commands.json").write_text(
        json.dumps({"blocked_commands": [
            {"pattern": "^pip ", "reason": "pip 禁止", "suggestion": "uv add"}
        ]}), encoding="utf-8")
    result = run_hook("pip install requests", tmp_path)
    assert result.returncode == 2
    assert "pip" in result.stderr
