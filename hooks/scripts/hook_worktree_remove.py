#!/usr/bin/env python3
"""
Claude Code Hooks - WorktreeRemove (WorktreeCreate の対)

WorktreeCreate hook を登録すると、Claude Code は hook が作った worktree を自分では
消さず、後始末を WorktreeRemove hook に委ねる。WorktreeRemove が無いとサブエージェントの
`isolation: "worktree"` が作った worktree は「kept hook-based worktree」として残り続ける。

契約 (公式 hooks リファレンス準拠): payload の `worktree_path` (WorktreeCreate が返した
絶対パス) を削除する。成功 = exit 0。非ゼロ exit は失敗で、Claude Code は worktree を残す。

Claude Code が渡す payload:
  {session_id, transcript_path, cwd, hook_event_name: "WorktreeRemove", worktree_path}

安全側の制約 (どれか 1 つでも満たさなければ削除せず失敗を返す):
- WorktreeCreate hook の配置先 (共有 checkout の `.agents/worktree/` 直下) にあること
- hook を起動した checkout と同じ repository に登録された linked worktree であること
- worktree の HEAD が、worktree を消しても残る ref (ブランチ・リモート追跡・タグ等) から到達できること。
  WorktreeCreate は detached HEAD で作るので、ブランチを切らずに commit した worktree を消すと
  その commit はどこからも参照されなくなる。`git worktree remove` はこれを止めない
- ignore 対象のファイルが、作り直せるキャッシュ (DISPOSABLE_*) と kit の hook ログだけであること。
  `git worktree remove` は `--force` なしでも ignore 対象のファイル (.env、ローカル DB、実験の出力等) を
  確認なしで消す
- `git worktree remove` を `--force` なしで実行する。未コミット・未追跡ファイルを含む
  worktree、lock された worktree、submodule を init 済みの worktree は Git 自身が拒否し、
  そのまま残る (submodule 側の未 push commit を巻き込んで消さないため)。
- 登録 timeout の締め切りまでに全ての確認と削除を終えられること。間に合わなければ削除を始めない。
"""

import fnmatch
import json
import os
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from hook_common import find_project_root, find_shared_root, hook_deadline, remaining_seconds

# hook_worktree_create.py の WORKTREE_SUBDIR と一致させる。
WORKTREE_SUBDIR = ".agents/worktree"
# この hook の登録 timeout (hooks/hooks.json)。プロセス起動から数えて、この時間内に応答を返す。
REGISTERED_TIMEOUT_SECONDS = 60
TIMEOUT_MARGIN_SECONDS = 5
# 個々の git 呼び出しの上限。締め切りまでの残り時間でさらに短くなる。
LIST_TIMEOUT = 5  # 古い Git では 2 回呼ぶ
CONTAINS_TIMEOUT = 10
STATUS_TIMEOUT = 10
REMOVE_TIMEOUT = 30
# 削除の途中で打ち切られないよう、残りがこれより短ければ git worktree remove を始めない。
MIN_REMOVE_SECONDS = 10

# 消しても作り直せる ignore 対象。これ以外の ignore 対象が 1 つでもあれば worktree を残す。
DISPOSABLE_DIRS = {"__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache", ".hypothesis"}
DISPOSABLE_FILES = ("*.pyc", "*.pyo", ".coverage", ".coverage.*")
# kit の hook が worktree 直下に書くデバッグログ (hook_common.get_log_dir)。
DISPOSABLE_ROOT_DIRS = (".claude/logs/", ".codex/logs/")


def _fail(message: str) -> None:
    sys.stderr.write(f"WorktreeRemove hook: {message}")
    sys.exit(1)


def _timeout(deadline: float, cap: float) -> float:
    timeout = remaining_seconds(deadline, cap)
    if timeout is None:
        _fail("登録 timeout までに確認を終えられないため残します")
    return timeout


def _registered_worktrees(shared_root: Path, deadline: float) -> dict[Path, str | None]:
    """登録された worktree のパスと HEAD のコミット。ディレクトリが消えた登録も含む。

    改行を含むパスでも壊れないよう NUL 区切り (`-z`、Git 2.36+) で読み、未対応の Git では行区切りに戻す。
    """
    for options, separator in ((["--porcelain", "-z"], "\0"), (["--porcelain"], "\n")):
        result = subprocess.run(
            ["git", "worktree", "list", *options],
            cwd=shared_root, capture_output=True, text=True, encoding="utf-8", errors="replace",
            timeout=_timeout(deadline, LIST_TIMEOUT),
        )
        if result.returncode == 0:
            break
    else:
        return {}
    worktrees: dict[Path, str | None] = {}
    current = None
    for line in result.stdout.split(separator):
        if line.startswith("worktree "):
            current = Path(line[len("worktree "):]).resolve()
            worktrees[current] = None
        elif line.startswith("HEAD ") and current is not None:
            worktrees[current] = line[len("HEAD "):].strip()
    return worktrees


def _kept_by_refs(shared_root: Path, commit: str, deadline: float) -> bool:
    """commit が、worktree を消しても残る ref から到達できるか。

    共有 checkout から見た ref (refs/heads, refs/remotes, refs/tags 等) だけを数える。
    削除対象の worktree 専用の ref と HEAD は worktree と一緒に消える。
    """
    result = subprocess.run(
        ["git", "for-each-ref", "--count=1", "--format=%(refname)", "--contains", commit],
        cwd=shared_root, capture_output=True, text=True, encoding="utf-8", errors="replace",
        timeout=_timeout(deadline, CONTAINS_TIMEOUT),
    )
    return result.returncode == 0 and bool(result.stdout.strip())


def _disposable(relative: str) -> bool:
    """worktree からの相対パス (区切りは /、ディレクトリは末尾 /) が、消しても作り直せるものか。"""
    if relative.startswith(DISPOSABLE_ROOT_DIRS):
        return True
    parts = relative.rstrip("/").split("/")
    directories = parts if relative.endswith("/") else parts[:-1]
    if any(part in DISPOSABLE_DIRS for part in directories):
        return True
    return not relative.endswith("/") and any(fnmatch.fnmatchcase(parts[-1], p) for p in DISPOSABLE_FILES)


def _first_kept_ignored(worktree: Path, deadline: float) -> str | None:
    """削除で失われる ignore 対象のうち、作り直せないものを 1 つ返す (無ければ None)。

    ignore 対象のディレクトリは Git がまとめて 1 件で返すので、中を走査して確かめる。
    作り直せないファイルが見つかった時点で止めるので、大きなディレクトリでも走査は短い。
    """
    result = subprocess.run(
        ["git", "status", "--porcelain=v1", "-z", "--ignored=matching", "--untracked-files=normal"],
        cwd=worktree, capture_output=True, text=True, encoding="utf-8", errors="replace",
        timeout=_timeout(deadline, STATUS_TIMEOUT),
    )
    if result.returncode != 0:
        return f"(git status に失敗: {result.stderr.strip()[-200:]})"
    for entry in result.stdout.split("\0"):
        if not entry.startswith("!! "):
            continue
        relative = entry[len("!! "):]
        if _disposable(relative):
            continue
        if not relative.endswith("/"):
            return relative
        for directory, subdirectories, files in os.walk(worktree / relative):
            _timeout(deadline, STATUS_TIMEOUT)
            base = Path(directory).relative_to(worktree).as_posix()
            subdirectories[:] = [d for d in subdirectories if not _disposable(f"{base}/{d}/")]
            for name in files:
                if not _disposable(f"{base}/{name}"):
                    return f"{base}/{name}"
    return None


def main() -> None:
    if sys.stdin.isatty():
        sys.exit(0)
    deadline = hook_deadline(REGISTERED_TIMEOUT_SECONDS, TIMEOUT_MARGIN_SECONDS)

    try:
        data: dict = json.loads(sys.stdin.read())
    except (json.JSONDecodeError, OSError) as e:
        _fail(f"payload 解析失敗: {e}")

    raw_path = data.get("worktree_path") if isinstance(data, dict) else None
    if not isinstance(raw_path, str) or not raw_path.strip():
        _fail("payload に worktree_path がありません")

    try:
        shared_root = find_shared_root(find_project_root()).resolve()
        worktree_base = (shared_root / WORKTREE_SUBDIR).resolve()
        target = Path(raw_path).expanduser().resolve()
    except (OSError, RuntimeError) as e:
        _fail(f"パス解決失敗: {e}")

    # WorktreeCreate hook が作る場所 (.agents/worktree/<name>) 以外は扱わない。
    if target.parent != worktree_base:
        _fail(f"{target} は {worktree_base} 直下ではないため削除しません")

    try:
        registered = _registered_worktrees(shared_root, deadline)
        if target not in registered:
            if not target.exists():
                print(f"already removed: {target}", file=sys.stderr)
                sys.exit(0)
            _fail(f"{target} はこの repository の linked worktree として登録されていません")
        head = registered[target]
        if not head or not _kept_by_refs(shared_root, head, deadline):
            _fail(
                f"{target} の HEAD ({head}) はどのブランチ・タグからも到達できないため残します。"
                "削除するとこの commit を失います。必要ならブランチを作成してから削除してください。"
            )
        if target.exists():
            kept = _first_kept_ignored(target, deadline)
            if kept is not None:
                _fail(
                    f"{target} に作り直せない ignore 対象のファイルがあるため残します: {kept}\n"
                    "git worktree remove はこれを確認なしで消します。内容を確認し、不要な場合だけ手動で削除してください。"
                )
        remove_timeout = remaining_seconds(deadline, REMOVE_TIMEOUT)
        if remove_timeout is None or remove_timeout < MIN_REMOVE_SECONDS:
            _fail("登録 timeout までに削除を終えられないため、削除を始めずに残します")
        # Windows はプロセスの cwd にあるディレクトリを削除できない。hook 自身が削除対象の中で
        # 起動されていても消せるよう、先に共有 checkout へ移る。ディレクトリが既に無い登録は
        # git worktree remove が登録だけを消す (残すと同名の WorktreeCreate が失敗する)。
        os.chdir(shared_root)
        result = subprocess.run(
            ["git", "worktree", "remove", "--", str(target)],
            cwd=shared_root, capture_output=True, text=True, encoding="utf-8", errors="replace",
            timeout=remove_timeout,
        )
    except (OSError, subprocess.SubprocessError) as e:
        _fail(f"git の実行に失敗したため残します: {e}")

    if result.returncode != 0:
        _fail(
            f"git worktree remove が拒否したため {target} を残します: {result.stderr.strip()[-500:]}\n"
            "変更・submodule の内容を確認し、不要な場合だけ手動で削除してください。"
        )
    sys.exit(0)


if __name__ == "__main__":
    main()
