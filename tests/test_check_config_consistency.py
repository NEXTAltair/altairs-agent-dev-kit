import json
import subprocess
import sys
from pathlib import Path

SCRIPT = Path(__file__).parent.parent / "scripts" / "check_config_consistency.py"


def make_project(tmp_path: Path, settings: dict, consistency: dict | None = None,
                 hook_files: list[str] = ()) -> Path:
    claude = tmp_path / ".claude"
    (claude / "hooks" / "rules").mkdir(parents=True)
    (claude / "settings.json").write_text(json.dumps(settings), encoding="utf-8")
    if consistency is not None:
        (claude / "hooks" / "rules" / "consistency.json").write_text(
            json.dumps(consistency), encoding="utf-8")
    for name in hook_files:
        (claude / "hooks" / name).write_text("#!/usr/bin/env python3\n", encoding="utf-8")
    return tmp_path


def run(root: Path) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, str(SCRIPT), "--root", str(root)],
                          capture_output=True, text=True, timeout=10)


def test_missing_required_env_fails(tmp_path):
    root = make_project(tmp_path, {"env": {}},
                        consistency={"required_env": ["UV_PROJECT_ENVIRONMENT"]})
    result = run(root)
    assert result.returncode == 1
    assert "UV_PROJECT_ENVIRONMENT" in result.stdout


def test_dead_hook_wiring_fails(tmp_path):
    settings = {"hooks": {"PreToolUse": [{"matcher": "Bash", "hooks": [
        {"type": "command", "command": "/usr/bin/timeout 5s .claude/hooks/missing.py"}]}]}}
    result = run(make_project(tmp_path, settings))
    assert result.returncode == 1
    assert "missing.py" in result.stdout


def test_unwired_hook_warns_but_passes(tmp_path):
    root = make_project(tmp_path, {"hooks": {}}, hook_files=["orphan.py"])
    result = run(root)
    assert result.returncode == 0
    assert "orphan.py" in result.stdout  # WARNING 行


def test_consistent_project_passes(tmp_path):
    settings = {
        "env": {"MY_ENV": "1"},
        "hooks": {"PreToolUse": [{"matcher": "Bash", "hooks": [
            {"type": "command", "command": "/usr/bin/timeout 5s .claude/hooks/guard.py"}]}]},
    }
    root = make_project(tmp_path, settings,
                        consistency={"required_env": ["MY_ENV"]}, hook_files=["guard.py"])
    result = run(root)
    assert result.returncode == 0
