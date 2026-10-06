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
- `git worktree remove` を `--force` なしで実行する。未コミット・未追跡ファイルを含む
  worktree、lock された worktree、submodule を init 済みの worktree は Git 自身が拒否し、
  そのまま残る (submodule 側の未 push commit を巻き込んで消さないため)。
"""

import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from hook_common import find_project_root, find_shared_root

# hook_worktree_create.py の WORKTREE_SUBDIR と一致させる。
WORKTREE_SUBDIR = ".agents/worktree"
# 内部の git 呼び出しの合計を登録 timeout (hooks.json の 60 秒) より短く保ち、途中で kill されないようにする。
LIST_TIMEOUT = 10
REMOVE_TIMEOUT = 40


def _fail(message: str) -> None:
    sys.stderr.write(f"WorktreeRemove hook: {message}")
    sys.exit(1)


def _registered_worktrees(shared_root: Path) -> set[Path]:
    result = subprocess.run(
        ["git", "worktree", "list", "--porcelain"],
        cwd=shared_root, capture_output=True, text=True, encoding="utf-8", errors="replace",
        timeout=LIST_TIMEOUT,
    )
    if result.returncode != 0:
        return set()
    return {
        Path(line[len("worktree "):]).resolve()
        for line in result.stdout.splitlines()
        if line.startswith("worktree ")
    }


def main() -> None:
    if sys.stdin.isatty():
        sys.exit(0)

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

    if not target.exists():
        # 既に消えている: 登録だけ残っていても Git の prune 対象なので成功扱い。
        print(f"already removed: {target}", file=sys.stderr)
        sys.exit(0)

    try:
        if target not in _registered_worktrees(shared_root):
            _fail(f"{target} はこの repository の linked worktree として登録されていません")
        result = subprocess.run(
            ["git", "worktree", "remove", "--", str(target)],
            cwd=shared_root, capture_output=True, text=True, encoding="utf-8", errors="replace",
            timeout=REMOVE_TIMEOUT,
        )
    except (OSError, subprocess.SubprocessError) as e:
        _fail(f"git worktree remove 実行失敗: {e}")

    if result.returncode != 0:
        _fail(
            f"git worktree remove が拒否したため {target} を残します: {result.stderr.strip()[-500:]}\n"
            "変更・submodule の内容を確認し、不要な場合だけ手動で削除してください。"
        )
    sys.exit(0)


if __name__ == "__main__":
    main()
