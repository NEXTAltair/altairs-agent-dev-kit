import json
import subprocess
import sys
from pathlib import Path

from conftest import pretooluse_deny_reason

EDIT_HOOK = Path(__file__).parent.parent / "hooks" / "scripts" / "hook_pre_edit_worktree.py"


def run_edit_hook(file_path: str, cwd: Path, tool_name: str = "Edit") -> subprocess.CompletedProcess:
    key = "notebook_path" if tool_name == "NotebookEdit" else "file_path"
    payload = json.dumps({"tool_name": tool_name, "tool_input": {key: file_path}})
    return subprocess.run(
        [sys.executable, str(EDIT_HOOK)], input=payload,
        capture_output=True, text=True, cwd=cwd, timeout=10,
        env={"CLAUDE_PROJECT_DIR": str(cwd), "PATH": "/usr/bin:/bin"},
    )


def test_shared_checkout_src_edit_blocked(tmp_path):
    (tmp_path / "src").mkdir()
    result = run_edit_hook(str(tmp_path / "src" / "app.py"), tmp_path)
    assert pretooluse_deny_reason(result) is not None


def test_shared_checkout_notebook_edit_blocked(tmp_path):
    # NotebookEdit は file_path ではなく notebook_path で対象を渡す。
    (tmp_path / "src").mkdir()
    result = run_edit_hook(str(tmp_path / "src" / "analysis.ipynb"), tmp_path, "NotebookEdit")
    assert pretooluse_deny_reason(result) is not None
    wt = tmp_path / ".agents" / "worktree" / "fix-1" / "src"
    wt.mkdir(parents=True)
    result = run_edit_hook(str(wt / "analysis.ipynb"), tmp_path, "NotebookEdit")
    assert result.returncode == 0
    assert pretooluse_deny_reason(result) is None


def test_worktree_src_edit_allowed(tmp_path):
    wt = tmp_path / ".agents" / "worktree" / "fix-1" / "src"
    wt.mkdir(parents=True)
    result = run_edit_hook(str(wt / "app.py"), tmp_path)
    assert result.returncode == 0
    assert pretooluse_deny_reason(result) is None


def test_non_protected_edit_allowed(tmp_path):
    result = run_edit_hook(str(tmp_path / "docs" / "note.md"), tmp_path)
    assert result.returncode == 0
    assert pretooluse_deny_reason(result) is None


def test_protected_dirs_override_blocks_custom_dir(tmp_path):
    rules_dir = tmp_path / ".claude" / "hooks" / "rules"
    rules_dir.mkdir(parents=True)
    (rules_dir / "pre_edit_worktree.json").write_text(
        json.dumps({"protected_dirs": ["lib"]}), encoding="utf-8"
    )
    (tmp_path / "lib").mkdir()
    result = run_edit_hook(str(tmp_path / "lib" / "core.py"), tmp_path)
    assert pretooluse_deny_reason(result) is not None

    # merge 挙動確認: deep_merge は list を連結するため、default["src","tests"] +
    # override["lib"] = ["src","tests","lib"] となり src も引き続きブロックされる。
    (tmp_path / "src").mkdir()
    result_src = run_edit_hook(str(tmp_path / "src" / "app.py"), tmp_path)
    assert pretooluse_deny_reason(result_src) is not None


def run_apply_patch_hook(patch: str, cwd: Path, payload_cwd: Path | None = None) -> subprocess.CompletedProcess:
    # Codex は apply_patch を tool_name "apply_patch"、パッチ本文を tool_input.command で渡す。
    payload = json.dumps({
        "tool_name": "apply_patch", "cwd": str(payload_cwd or cwd), "tool_input": {"command": patch},
    })
    return subprocess.run(
        [sys.executable, str(EDIT_HOOK)], input=payload,
        capture_output=True, text=True, cwd=cwd, timeout=10,
        env={"CLAUDE_PROJECT_DIR": str(cwd), "PATH": "/usr/bin:/bin"},
    )


def patch_of(*headers: str) -> str:
    return "*** Begin Patch\n" + "\n".join(headers) + "\n+x\n*** End Patch\n"


def test_codex_apply_patch_into_protected_dir_blocked(tmp_path):
    (tmp_path / "src").mkdir()
    for headers in (
        ("*** Add File: src/new.py",),
        ("*** Update File: docs/a.md", "@@", "*** Update File: src/app.py"),
        ("*** Delete File: tests/test_a.py",),
        ("*** Update File: docs/a.md", "*** Move to: src/moved.py"),
        (f"*** Update File: {tmp_path / 'src' / 'abs.py'}",),
        ("  *** Add File: src/indented.py  ",),
    ):
        result = run_apply_patch_hook(patch_of(*headers), tmp_path)
        assert pretooluse_deny_reason(result) is not None, headers


def test_codex_apply_patch_allowed_outside_protected_dirs_and_in_worktree(tmp_path):
    result = run_apply_patch_hook(patch_of("*** Add File: docs/note.md"), tmp_path)
    assert result.returncode == 0
    assert pretooluse_deny_reason(result) is None
    # 追加行の中身はパス指定ではない。
    result = run_apply_patch_hook(patch_of("*** Add File: docs/note.md", "+*** Add File: src/x.py"), tmp_path)
    assert pretooluse_deny_reason(result) is None
    # Update hunk 内の行頭空白付きの行は context 行。見出しと同じ文字列でもパスではない (Codex のパーサと同じ)。
    for context in (" *** Update File: src/x.py", " *** Move to: src/x.py", "-*** Delete File: tests/a.py"):
        patch = patch_of("*** Update File: docs/a.md", "@@", context)
        result = run_apply_patch_hook(patch, tmp_path)
        assert pretooluse_deny_reason(result) is None, context
    # 相対パスは Codex の作業ディレクトリ (payload の cwd) 基準: worktree 内なら許可。
    wt = tmp_path / ".agents" / "worktree" / "fix-1"
    (wt / "src").mkdir(parents=True)
    result = run_apply_patch_hook(patch_of("*** Update File: src/app.py"), tmp_path, payload_cwd=wt)
    assert result.returncode == 0
    assert pretooluse_deny_reason(result) is None


def test_command_of_other_tools_is_not_parsed_as_patch(tmp_path):
    payload = json.dumps({"tool_name": "Bash", "tool_input": {"command": patch_of("*** Add File: src/x.py")}})
    result = subprocess.run(
        [sys.executable, str(EDIT_HOOK)], input=payload, capture_output=True, text=True, cwd=tmp_path,
        timeout=10, env={"CLAUDE_PROJECT_DIR": str(tmp_path), "PATH": "/usr/bin:/bin"},
    )
    assert result.returncode == 0
    assert pretooluse_deny_reason(result) is None


def test_denies_when_shared_checkout_cannot_be_identified_from_a_worktree(tmp_path):
    # 共有 checkout の特定に失敗したとき作業中の worktree を代わりに使うと、
    # worktree から共有 checkout の src/ を指す編集が「範囲外」として素通りする。
    import shutil
    main = tmp_path / "main"
    main.mkdir()

    def git(*args, cwd=main):
        subprocess.run(["git", "-c", "user.name=T", "-c", "user.email=t@e", *args], cwd=cwd,
                       check=True, capture_output=True)

    git("init", "-q")
    git("commit", "-q", "--allow-empty", "-m", "init")
    worktree = main / ".agents" / "worktree" / "wt"
    git("worktree", "add", "-q", "--detach", str(worktree))
    (main / "src").mkdir()
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    wrapper = bin_dir / "git"
    wrapper.write_text(
        "#!/bin/sh\n"
        'case " $* " in *" --git-common-dir "*) echo "fatal: simulated failure" >&2; exit 128;; esac\n'
        f'exec "{shutil.which("git")}" "$@"\n',
        encoding="utf-8",
    )
    wrapper.chmod(0o755)
    env = {"CLAUDE_PROJECT_DIR": str(worktree), "PATH": f"{bin_dir}:/usr/bin:/bin"}
    for payload in (
        {"tool_name": "apply_patch", "cwd": str(worktree),
         "tool_input": {"command": patch_of("*** Update File: ../../../src/app.py")}},
        {"tool_name": "Edit", "tool_input": {"file_path": str(main / "src" / "app.py")}},
    ):
        result = subprocess.run(
            [sys.executable, str(EDIT_HOOK)], input=json.dumps(payload), capture_output=True,
            text=True, cwd=worktree, timeout=10, env=env,
        )
        assert pretooluse_deny_reason(result) is not None, payload["tool_name"]
    # git が正常なら、worktree 内の編集は従来どおり許可される。
    result = subprocess.run(
        [sys.executable, str(EDIT_HOOK)], capture_output=True, text=True, cwd=worktree, timeout=10,
        input=json.dumps({"tool_name": "Edit", "tool_input": {"file_path": str(worktree / "src" / "app.py")}}),
        env={**env, "PATH": "/usr/bin:/bin"},
    )
    assert pretooluse_deny_reason(result) is None
