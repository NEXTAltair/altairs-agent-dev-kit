#!/usr/bin/env python3
"""
Claude Code Hooks - Pre-Edit Worktree Gate (PreToolUse Hook)

プロジェクト本体のアプリコード (デフォルト `src/`, `tests/`) を共有 checkout
(project root) で直接 Edit/Write しようとしたらブロックする。

目的:
- ISSUE 解決・機能開発は「worktree 作成 → そこで実装」を機械的に強制する。
  ルールだけの guidance では Edit/Write を素通りさせてしまい、
  「修正してから後付けで worktree を作る」という崩れた順序が起きやすい。

ブロック対象 (共有 checkout 上、デフォルト): protected_dirs で設定可能
- <project_root>/src/**
- <project_root>/tests/**

ブロックしない (意図的に共有 checkout で作業してよいもの):
- <project_root>/.agents/worktree/** (worktree 内なら何でも可)
- protected_dirs に含まれないトップレベル dir (docs/ 等の chore は各プロジェクトの
  ルールドキュメントに従い、rules 側で protected_dirs から除外しておく)

ルールは 2 層構造で解決する (`hook_common.load_hook_rules`):
- デフォルト層: `hooks/rules/pre_edit_worktree.default.json` (kit 同梱)
- 導入先 override 層: `<project_root>/.claude/hooks/rules/pre_edit_worktree.json`

バイパス:
- 緊急時など共有 checkout 直編集が必要な場合は環境変数 ALLOW_MAIN_EDIT=1 を設定。
"""

import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from hook_common import (
    emit_pretooluse_deny,
    find_project_root,
    find_shared_root,
    load_hook_rules,
)

DEFAULT_PROTECTED_DIRS = ["src", "tests"]


def _resolve(file_path: str) -> Path | None:
    try:
        return Path(file_path).expanduser().resolve()
    except (OSError, ValueError, RuntimeError):
        return None


def _is_blocked(file_path: str, repo_root: Path, worktree_root: Path, protected_dirs: list[str]) -> bool:
    """共有 checkout 上の保護対象ディレクトリへの編集なら True。"""
    resolved = _resolve(file_path)
    if resolved is None:
        return False

    # worktree 内なら常に許可
    if resolved.is_relative_to(worktree_root):
        return False

    # repo root 配下でなければ対象外
    if not resolved.is_relative_to(repo_root):
        return False

    rel = resolved.relative_to(repo_root)
    if not rel.parts:
        return False

    return rel.parts[0] in protected_dirs


def _build_message(file_path: str, repo_root: Path, worktree_root: Path) -> str:
    resolved = _resolve(file_path)
    rel = resolved.relative_to(repo_root) if resolved else Path(file_path)
    return (
        "🚫 共有 checkout でのアプリコード編集はブロックされました。\n"
        f"   対象: {rel}\n"
        "→ ISSUE 解決・機能開発は worktree から開始してください。\n"
        "   git fetch origin\n"
        f"   git worktree add {worktree_root}/<branch> -b <type>/issue-<n> origin/main\n"
        "   # 以降の Edit/commit/push はこの worktree 内で行う\n"
        "→ 保護対象外のディレクトリ (docs 等の chore) は対象外。緊急で共有 checkout "
        "直編集が必要な場合のみ ALLOW_MAIN_EDIT=1 を設定。"
    )


def main() -> None:
    try:
        if sys.stdin.isatty():
            sys.exit(0)

        if os.environ.get("ALLOW_MAIN_EDIT") == "1":
            sys.exit(0)

        input_data: dict = json.load(sys.stdin)
        tool_input = input_data.get("tool_input", {})
        file_path = tool_input.get("file_path", "")
        if not file_path:
            sys.exit(0)

        active_root = find_project_root()
        repo_root = find_shared_root(active_root)
        worktree_root = repo_root / ".agents" / "worktree"
        rules = load_hook_rules("pre_edit_worktree", active_root)
        protected_dirs = rules.get("protected_dirs", DEFAULT_PROTECTED_DIRS)

        if _is_blocked(file_path, repo_root, worktree_root, protected_dirs):
            emit_pretooluse_deny(_build_message(file_path, repo_root, worktree_root))

        sys.exit(0)

    except (json.JSONDecodeError, OSError):
        sys.exit(0)


if __name__ == "__main__":
    main()
