#!/usr/bin/env python3
"""
Claude Code Hooks - WorktreeCreate (provider hook)

`claude --worktree <name>` およびサブエージェントの `isolation: "worktree"` 起動時に
Claude Code が呼ぶ **provider**。worktree を作成し、そのパスを stdout に echo して返す。

契約 (公式 hooks リファレンス準拠): 成功 = exit 0 + stdout にパス。
失敗 = 非ゼロ exit (この hook は exit 2 に限らず非ゼロ全てが失敗扱いで、
セッション/サブエージェント起動が中断される。デフォルト作成へのフォールバックはない)。

Claude Code が渡す payload:
  {session_id, cwd, hook_event_name: "WorktreeCreate",
   worktree_name, worktree_path (提案パス), source_ref}

重要: ここで `uv sync` (や同等の依存インストール) は実行しない。
  共有の実行環境 (project_root/.venv 等) は main checkout から既に sync 済みで、
  worktree はこれを共有する想定。worktree の cwd でパッケージマネージャの sync を
  走らせると、workspace member の editable install が worktree 側のパスへ貼り替わり、
  共有環境の editable ピンが壊れる (main checkout と他の全 worktree の
  ローカルパッケージ import が同時に狂う) 上に容量も肥大する。

代わりに submodule のソースだけ init する。worktree は submodule が未 checkout だと
サブモジュールに依存するテストが偽陽性/偽陰性になり得るため、ソースだけ materialize
しておく (共有の実行環境には一切触れない)。

worktree は detached HEAD で作る。実装 agent は中で専用ブランチを切る想定。
"""

import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from hook_common import find_project_root, find_shared_root

# isolation worktree の配置先: リポジトリ内 .agents/worktree/。
WORKTREE_SUBDIR = ".agents/worktree"


def _sanitize(name: str) -> str:
    """agent 名を path 安全なディレクトリ名へ正規化する。"""
    return "".join(c if (c.isalnum() or c in "-_") else "-" for c in name) or "agent"


def main() -> None:
    if sys.stdin.isatty():
        sys.exit(0)

    try:
        data: dict = json.loads(sys.stdin.read())
    except (json.JSONDecodeError, OSError) as e:
        sys.stderr.write(f"WorktreeCreate hook: payload 解析失敗: {e}")
        sys.exit(1)

    repo = find_shared_root(Path(data.get("cwd") or find_project_root()))
    worktree_base = Path(repo) / WORKTREE_SUBDIR
    # 現行スキーマは worktree_name。旧 payload 形状 (name) にもフォールバックする。
    worktree_path = worktree_base / _sanitize(data.get("worktree_name") or data.get("name") or "agent")
    source_ref = data.get("source_ref") or "HEAD"

    try:
        worktree_base.mkdir(parents=True, exist_ok=True)

        # 既存 worktree は再利用 (セッション再開耐性)。無ければ detached で作成。
        if not (worktree_path / ".git").exists():
            result = subprocess.run(
                ["git", "worktree", "add", "--detach", str(worktree_path), source_ref],
                cwd=repo,
                capture_output=True,
                text=True, encoding="utf-8", errors="replace",
            )
            if result.returncode != 0:
                sys.stderr.write(f"git worktree add 失敗: {result.stderr[-500:]}")
                sys.exit(1)

        # submodule のソースのみ init する (共有の実行環境は触らない)。
        # 失敗しても worktree 自体は使えるので致命扱いにしない (warning のみ)。
        sub = subprocess.run(
            ["git", "submodule", "update", "--init", "--recursive"],
            cwd=worktree_path,
            capture_output=True,
            text=True, encoding="utf-8", errors="replace",
        )
        if sub.returncode != 0:
            sys.stderr.write(f"⚠️ git submodule update --init 失敗: {sub.stderr[-300:]}")

    except OSError as e:
        sys.stderr.write(f"WorktreeCreate hook: worktree 作成失敗: {e}")
        sys.exit(1)

    # 契約: 作成した worktree のパスを stdout に echo する。
    print(str(worktree_path))
    sys.exit(0)


if __name__ == "__main__":
    main()
