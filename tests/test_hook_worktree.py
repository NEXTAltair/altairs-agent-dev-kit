import json
import subprocess
import sys
from pathlib import Path

EDIT_HOOK = Path(__file__).parent.parent / "hooks" / "scripts" / "hook_pre_edit_worktree.py"


def run_edit_hook(file_path: str, cwd: Path) -> subprocess.CompletedProcess:
    payload = json.dumps({"tool_name": "Edit", "tool_input": {"file_path": file_path}})
    return subprocess.run(
        [sys.executable, str(EDIT_HOOK)], input=payload,
        capture_output=True, text=True, cwd=cwd, timeout=10,
        env={"CLAUDE_PROJECT_DIR": str(cwd), "PATH": "/usr/bin:/bin"},
    )


def test_shared_checkout_src_edit_blocked(tmp_path):
    (tmp_path / "src").mkdir()
    result = run_edit_hook(str(tmp_path / "src" / "app.py"), tmp_path)
    assert result.returncode == 2


def test_worktree_src_edit_allowed(tmp_path):
    wt = tmp_path / ".agents" / "worktree" / "fix-1" / "src"
    wt.mkdir(parents=True)
    result = run_edit_hook(str(wt / "app.py"), tmp_path)
    assert result.returncode == 0


def test_non_protected_edit_allowed(tmp_path):
    result = run_edit_hook(str(tmp_path / "docs" / "note.md"), tmp_path)
    assert result.returncode == 0


def test_protected_dirs_override_blocks_custom_dir(tmp_path):
    rules_dir = tmp_path / ".claude" / "hooks" / "rules"
    rules_dir.mkdir(parents=True)
    (rules_dir / "pre_edit_worktree.json").write_text(
        json.dumps({"protected_dirs": ["lib"]}), encoding="utf-8"
    )
    (tmp_path / "lib").mkdir()
    result = run_edit_hook(str(tmp_path / "lib" / "core.py"), tmp_path)
    assert result.returncode == 2

    # override 追加後は元の default "src" はブロックされない (list は連結でなく override 側)
    # merge 挙動確認: deep_merge は list を連結するため、default["src","tests"] +
    # override["lib"] = ["src","tests","lib"] となり src も引き続きブロックされる。
    (tmp_path / "src").mkdir()
    result_src = run_edit_hook(str(tmp_path / "src" / "app.py"), tmp_path)
    assert result_src.returncode == 2
