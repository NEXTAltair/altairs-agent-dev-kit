"""hook_worktree_remove.py (WorktreeRemove) のテスト。

契約: 成功 = exit 0。失敗 = 非ゼロ exit で、Claude Code は worktree を残す。
削除は WorktreeCreate の配置先にある、この repository の linked worktree に限り、
Git が --force なしで消せるものだけを消す。
"""

import json
import subprocess
import sys
from pathlib import Path

HOOKS = Path(__file__).parent.parent / "hooks" / "scripts"


def git(cwd: Path, *args: str) -> None:
    subprocess.run(
        ["git", "-c", "user.name=Test", "-c", "user.email=test@example.com",
         "-c", "protocol.file.allow=always", *args],
        cwd=cwd, check=True, capture_output=True,
    )


def init_repo(path: Path) -> None:
    path.mkdir(exist_ok=True)
    git(path, "init", "-q")
    (path / "README.md").write_text("init\n", encoding="utf-8")
    git(path, "add", "README.md")
    git(path, "commit", "-q", "-m", "init")


def run_hook(name: str, payload: dict, cwd: Path, path: str = "/usr/bin:/bin",
             extra_env: dict | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(HOOKS / f"{name}.py")], input=json.dumps(payload),
        capture_output=True, text=True, encoding="utf-8", cwd=cwd, timeout=60,
        # WorktreeCreate の submodule init がローカル (file://) の submodule を取得できるようにする。
        env={"CLAUDE_PROJECT_DIR": str(cwd), "PATH": path, "GIT_CONFIG_COUNT": "1",
             "GIT_CONFIG_KEY_0": "protocol.file.allow", "GIT_CONFIG_VALUE_0": "always", **(extra_env or {})},
    )


def create(repo: Path, name: str) -> Path:
    result = run_hook("hook_worktree_create", {"cwd": str(repo), "name": name}, repo)
    assert result.returncode == 0, result.stderr
    return Path(result.stdout.strip())


def remove(repo: Path, worktree: Path | str, path: str = "/usr/bin:/bin",
           extra_env: dict | None = None) -> subprocess.CompletedProcess:
    return run_hook(
        "hook_worktree_remove",
        {"cwd": str(repo), "hook_event_name": "WorktreeRemove", "worktree_path": str(worktree)},
        repo, path, extra_env,
    )


def test_removes_clean_worktree_created_by_pair_hook(tmp_path):
    init_repo(tmp_path)
    worktree = create(tmp_path, "agent-a1")
    result = remove(tmp_path, worktree)
    assert result.returncode == 0, result.stderr
    assert not worktree.exists()
    listed = subprocess.run(["git", "worktree", "list"], cwd=tmp_path, capture_output=True, text=True)
    assert str(worktree) not in listed.stdout


def test_clears_registration_of_already_deleted_directory(tmp_path):
    # 登録が残ったままだと、同名の WorktreeCreate が "missing but already registered" で失敗する。
    import shutil
    init_repo(tmp_path)
    worktree = create(tmp_path, "deleted-by-hand")
    shutil.rmtree(worktree)
    result = remove(tmp_path, worktree)
    assert result.returncode == 0, result.stderr
    listed = subprocess.run(["git", "worktree", "list"], cwd=tmp_path, capture_output=True, text=True)
    assert str(worktree) not in listed.stdout
    assert create(tmp_path, "deleted-by-hand") == worktree


def test_removes_worktree_of_repository_whose_path_contains_a_newline(tmp_path):
    # porcelain の行区切りではパスが途中で切れ、未登録と誤判定して残してしまう。
    repo = tmp_path / "line\nbreak repo"
    init_repo(repo)
    worktree = create(repo, "agent-nl")
    result = remove(repo, worktree)
    assert result.returncode == 0, result.stderr
    assert not worktree.exists()


def test_falls_back_to_line_records_on_git_without_nul_output(tmp_path):
    # `git worktree list -z` は Git 2.36+。古い Git でも行区切りで判定して削除できる。
    import shutil
    real_git = shutil.which("git")
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    wrapper = bin_dir / "git"
    wrapper.write_text(
        "#!/bin/sh\n"
        'case " $* " in *" worktree list "*" -z "*) echo "error: unknown switch \\`z\\x27" >&2; exit 129;; esac\n'
        f'exec "{real_git}" "$@"\n',
        encoding="utf-8",
    )
    wrapper.chmod(0o755)
    repo = tmp_path / "repo"
    init_repo(repo)
    worktree = create(repo, "old-git")
    old_git = subprocess.run([str(wrapper), "worktree", "list", "--porcelain", "-z"], cwd=repo, capture_output=True)
    assert old_git.returncode == 129
    result = remove(repo, worktree, path=f"{bin_dir}:/usr/bin:/bin")
    assert result.returncode == 0, result.stderr
    assert not worktree.exists()


def test_keeps_detached_commits_until_a_ref_holds_them(tmp_path):
    # WorktreeCreate は detached HEAD で作る。ブランチを切らずに commit した worktree は clean でも、
    # 消すとその commit はどこからも参照されなくなるので残す。
    init_repo(tmp_path)
    worktree = create(tmp_path, "detached-work")
    (worktree / "feature.txt").write_text("work\n", encoding="utf-8")
    git(worktree, "add", "feature.txt")
    git(worktree, "commit", "-q", "-m", "work on detached HEAD")
    result = remove(tmp_path, worktree)
    assert result.returncode != 0
    assert "到達できない" in result.stderr
    assert (worktree / "feature.txt").exists()
    # ブランチで commit を保持すれば削除でき、commit はブランチに残る。
    git(worktree, "branch", "keep-work")
    result = remove(tmp_path, worktree)
    assert result.returncode == 0, result.stderr
    assert not worktree.exists()
    shown = subprocess.run(["git", "show", "keep-work:feature.txt"], cwd=tmp_path, capture_output=True, text=True)
    assert shown.stdout == "work\n"


def test_keeps_registration_of_deleted_directory_holding_detached_commits(tmp_path):
    # ディレクトリが消えていても、登録の HEAD だけが commit を参照している間は登録を消さない。
    import shutil
    init_repo(tmp_path)
    worktree = create(tmp_path, "deleted-with-work")
    (worktree / "feature.txt").write_text("work\n", encoding="utf-8")
    git(worktree, "add", "feature.txt")
    git(worktree, "commit", "-q", "-m", "work on detached HEAD")
    shutil.rmtree(worktree)
    result = remove(tmp_path, worktree)
    assert result.returncode != 0
    listed = subprocess.run(["git", "worktree", "list"], cwd=tmp_path, capture_output=True, text=True)
    assert str(worktree) in listed.stdout


def test_keeps_worktree_with_uncommitted_or_untracked_files(tmp_path):
    init_repo(tmp_path)
    worktree = create(tmp_path, "dirty")
    (worktree / "notes.txt").write_text("unsaved work\n", encoding="utf-8")
    result = remove(tmp_path, worktree)
    assert result.returncode != 0
    assert (worktree / "notes.txt").read_text(encoding="utf-8") == "unsaved work\n"
    (worktree / "notes.txt").unlink()
    (worktree / "README.md").write_text("modified\n", encoding="utf-8")
    result = remove(tmp_path, worktree)
    assert result.returncode != 0
    assert (worktree / "README.md").read_text(encoding="utf-8") == "modified\n"


def test_keeps_locked_worktree(tmp_path):
    init_repo(tmp_path)
    worktree = create(tmp_path, "locked")
    git(tmp_path, "worktree", "lock", str(worktree))
    result = remove(tmp_path, worktree)
    assert result.returncode != 0
    assert worktree.is_dir()


def test_keeps_worktree_with_initialized_submodule(tmp_path):
    # WorktreeCreate は submodule を init する。submodule 側の未 push commit を巻き込まないよう
    # --force を使わず、Git の拒否をそのまま失敗として返す。
    library = tmp_path / "library"
    init_repo(library)
    repo = tmp_path / "repo"
    init_repo(repo)
    git(repo, "submodule", "add", "-q", library.as_uri(), "pkgs/library")
    git(repo, "commit", "-q", "-m", "add submodule")
    worktree = create(repo, "with-submodule")
    assert (worktree / "pkgs/library/README.md").exists()
    result = remove(repo, worktree)
    assert result.returncode != 0
    assert worktree.is_dir()


def test_refuses_paths_outside_the_worktree_base(tmp_path):
    init_repo(tmp_path)
    elsewhere = tmp_path / "elsewhere"
    git(tmp_path, "worktree", "add", "-q", "--detach", str(elsewhere))
    nested = create(tmp_path, "parent") / "child"
    nested.mkdir()
    for target in (tmp_path, elsewhere, nested, tmp_path / ".agents/worktree"):
        result = remove(tmp_path, target)
        assert result.returncode != 0, target
        assert "直下ではない" in result.stderr or "登録されていません" in result.stderr, result.stderr
        assert Path(target).exists(), target


def test_refuses_unregistered_directory_and_foreign_repository(tmp_path):
    init_repo(tmp_path)
    plain = tmp_path / ".agents/worktree/plain"
    plain.mkdir(parents=True)
    (plain / "keep.txt").write_text("not a worktree\n", encoding="utf-8")
    result = remove(tmp_path, plain)
    assert result.returncode != 0
    assert (plain / "keep.txt").exists()
    assert "登録されていません" in result.stderr
    # 配置先の直下にあっても、別 repository の worktree は削除しない。
    other = tmp_path / "other"
    init_repo(other)
    foreign = tmp_path / ".agents/worktree/foreign"
    git(other, "worktree", "add", "-q", "--detach", str(foreign))
    result = remove(tmp_path, foreign)
    assert result.returncode != 0
    assert "登録されていません" in result.stderr
    assert foreign.is_dir()


def test_missing_payload_fails_and_already_removed_succeeds(tmp_path):
    init_repo(tmp_path)
    result = run_hook("hook_worktree_remove", {"cwd": str(tmp_path)}, tmp_path)
    assert result.returncode != 0
    result = run_hook("hook_worktree_remove", {"worktree_path": ["not", "a", "path"]}, tmp_path)
    assert result.returncode != 0
    result = remove(tmp_path, tmp_path / ".agents/worktree/never-created")
    assert result.returncode == 0, result.stderr


def init_repo_ignoring(path: Path, patterns: str) -> None:
    init_repo(path)
    (path / ".gitignore").write_text(patterns, encoding="utf-8")
    git(path, "add", ".gitignore")
    git(path, "commit", "-q", "-m", "ignore")


def test_keeps_worktree_with_ignored_files_that_cannot_be_regenerated(tmp_path):
    # git worktree remove は --force なしでも ignore 対象を確認なしで消す。
    init_repo_ignoring(tmp_path, "*.secret\n.claude/\n")
    for name, content in (("x.secret", "token"), (".claude/settings.local.json", "{}")):
        worktree = create(tmp_path, "ignored-" + Path(name).stem.strip("."))
        file = worktree / name
        file.parent.mkdir(parents=True, exist_ok=True)
        file.write_text(content, encoding="utf-8")
        result = remove(tmp_path, worktree)
        assert result.returncode != 0, name
        assert name in result.stderr
        assert file.read_text(encoding="utf-8") == content


def test_removes_worktree_whose_ignored_files_are_only_caches_and_kit_logs(tmp_path):
    init_repo_ignoring(tmp_path, "__pycache__/\n*.pyc\n.pytest_cache/\n.coverage\n.claude/\n")
    worktree = create(tmp_path, "caches-only")
    for name in ("src/__pycache__/a.cpython-313.pyc", "b.pyc", ".pytest_cache/v/cache/nodeids",
                 ".coverage", ".claude/logs/hook_pre_commands_debug.log"):
        file = worktree / name
        file.parent.mkdir(parents=True, exist_ok=True)
        file.write_text("x", encoding="utf-8")
    result = remove(tmp_path, worktree)
    assert result.returncode == 0, result.stderr
    assert not worktree.exists()


def test_does_not_start_removal_without_time_to_finish(tmp_path):
    # 起動入口の記録から締め切りが近いと分かれば、途中で打ち切られる削除を始めない。
    import time
    hook_module = HOOKS / "hook_worktree_remove.py"
    namespace: dict = {}
    for line in hook_module.read_text(encoding="utf-8").splitlines():
        if line.startswith(("REGISTERED_TIMEOUT_SECONDS =", "TIMEOUT_MARGIN_SECONDS =")):
            exec(line.split("#")[0], namespace)
    init_repo(tmp_path)
    worktree = create(tmp_path, "late")
    spent = namespace["REGISTERED_TIMEOUT_SECONDS"] - namespace["TIMEOUT_MARGIN_SECONDS"] - 3
    result = remove(tmp_path, worktree, extra_env={"AGENT_KIT_STARTED": repr(time.monotonic() - spent)})
    assert result.returncode != 0
    assert "登録 timeout" in result.stderr
    assert worktree.is_dir()


def test_registered_timeout_matches_plugin_registration():
    plugin = json.loads((HOOKS.parent / "hooks.json").read_text(encoding="utf-8"))
    registered = plugin["hooks"]["WorktreeRemove"][0]["hooks"][0]["timeout"]
    source = (HOOKS / "hook_worktree_remove.py").read_text(encoding="utf-8")
    assert f"REGISTERED_TIMEOUT_SECONDS = {registered}\n" in source


def test_keeps_ignored_directory_with_a_name_that_is_not_utf8(tmp_path):
    # 名前を置換して読むと実在しないパスを走査し、中身を確かめずに消してしまう。
    import os
    init_repo_ignoring(tmp_path, "bad*/\n")
    worktree = create(tmp_path, "non-utf8")
    directory = os.fsencode(worktree) + b"/bad\xff"
    os.mkdir(directory)
    with open(directory + b"/secret", "wb") as stream:
        stream.write(b"token")
    result = remove(tmp_path, worktree)
    assert result.returncode != 0
    assert os.path.exists(directory + b"/secret")


def test_keeps_ignored_directory_symlinks(tmp_path):
    # os.walk は symlink のディレクトリを辿らない。中身を確かめられないので残す。
    import os
    init_repo_ignoring(tmp_path, "local/\n")
    data = tmp_path / "data"
    data.mkdir()
    (data / "notes.txt").write_text("keep", encoding="utf-8")
    worktree = create(tmp_path, "symlinked")
    (worktree / "local").mkdir()
    os.symlink(data, worktree / "local/link", target_is_directory=True)
    result = remove(tmp_path, worktree)
    assert result.returncode != 0
    assert "local/link" in result.stderr
    assert (worktree / "local/link").is_symlink()


def test_fails_when_worktree_list_fails_even_if_directory_is_gone(tmp_path):
    # 一覧を取れないときに「登録なし」とみなすと、残った登録を消さずに成功扱いしてしまう。
    import shutil
    real_git = shutil.which("git")
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    wrapper = bin_dir / "git"
    wrapper.write_text(
        "#!/bin/sh\n"
        'case " $* " in *" worktree list "*) echo "fatal: simulated failure" >&2; exit 128;; esac\n'
        f'exec "{real_git}" "$@"\n',
        encoding="utf-8",
    )
    wrapper.chmod(0o755)
    repo = tmp_path / "repo"
    init_repo(repo)
    worktree = create(repo, "listing-fails")
    shutil.rmtree(worktree)
    result = remove(repo, worktree, path=f"{bin_dir}:/usr/bin:/bin")
    assert result.returncode != 0
    assert "worktree list" in result.stderr
    listed = subprocess.run(["git", "worktree", "list"], cwd=repo, capture_output=True, text=True)
    assert str(worktree) in listed.stdout
