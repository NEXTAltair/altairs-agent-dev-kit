#!/usr/bin/env python3
"""
Claude Code Hooks - WorktreeCreate (provider hook)

Agent tool の `isolation: "worktree"` 起動時に harness が呼ぶ **provider**。
worktree を作成し、そのパスを stdout に echo して返す (契約: 失敗時は非ゼロ exit)。

harness が渡す payload (tool_input.path は無い — このフックが作成する側):
  {session_id, transcript_path, cwd, hook_event_name: "WorktreeCreate", name}

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
from hook_common import find_project_root  # noqa: E402

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

    repo = data.get("cwd") or str(find_project_root())
    worktree_base = Path(repo) / WORKTREE_SUBDIR
    worktree_path = worktree_base / _sanitize(data.get("name") or "agent")

    try:
        worktree_base.mkdir(parents=True, exist_ok=True)

        # 既存 worktree は再利用 (セッション再開耐性)。無ければ detached で作成。
        if not (worktree_path / ".git").exists():
            result = subprocess.run(
                ["git", "worktree", "add", "--detach", str(worktree_path), "HEAD"],
                cwd=repo,
                capture_output=True,
                text=True,
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
            text=True,
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
