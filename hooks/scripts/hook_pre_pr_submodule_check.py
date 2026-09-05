#!/usr/bin/env python3
"""
Hook - Pre-PR Submodule Check (PreToolUse Hook for `gh pr create`)

`gh pr create` 実行時に submodule (または任意の path glob) の変更を含む PR を検知し、
CI-equivalent test の実行確認を要求する gate。

検知条件:
- command が `gh pr create` を含む
- `git diff --name-only origin/main...HEAD` が `submodule_globs` のいずれかにマッチ

通過条件 (いずれか):
- command 文字列に `bypass_marker` を含む (テスト実行ログを兼ねる)
- 対象パスの変更を含まない PR (普通の PR)
- `submodule_globs` が空 (デフォルト無効。submodule を持つ導入先だけ override で有効化)
- git diff が失敗 (detached HEAD 等) → graceful degrade で allow

ルールは 2 層構造で解決する (`hook_common.load_hook_rules`):
- デフォルト層: `hooks/rules/pre_pr_submodule_check.default.json`
  (`submodule_globs: []` = デフォルト無効)
- 導入先 override 層: `<project_root>/.claude/hooks/rules/pre_pr_submodule_check.json`
  (`submodule_globs` に glob パターン、例: `["vendor/*"]` を追加して有効化する)

CI-equivalent test の具体的なコマンドは導入先の testing ルール文書を参照させる
(本 hook はどのテストコマンドを使うべきかまでは持たない)。
"""

import fnmatch
import json
import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).parent))
from hook_common import emit_pretooluse_deny, find_project_root, get_log_dir, load_hook_rules


def log_debug(log_dir: Path, message: str) -> None:
    """デバッグログ出力"""
    try:
        log_dir.mkdir(parents=True, exist_ok=True)
        log_file = log_dir / "hook_pre_pr_submodule_check_debug.log"
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with log_file.open("a", encoding="utf-8") as f:
            f.write(f"[{timestamp}] {message}\n")
    except OSError:
        pass


def is_gh_pr_create(command: str) -> bool:
    """command が `gh pr create` を呼び出しているか判定"""
    return bool(re.search(r"\bgh\s+pr\s+create\b", command))


def get_changed_paths(project_root: Path) -> list[str]:
    """現 branch と origin/main の差分パス一覧を返す"""
    try:
        result = subprocess.run(
            ["git", "diff", "--name-only", "origin/main...HEAD"],
            cwd=project_root,
            capture_output=True,
            text=True, encoding="utf-8", errors="replace",
            timeout=10,
        )
        if result.returncode != 0:
            return []
        return [line for line in result.stdout.strip().split("\n") if line]
    except (subprocess.TimeoutExpired, OSError):
        return []


def identify_affected_submodules(changes: list[str], submodule_globs: list[str]) -> set[str]:
    """変更パスのうち submodule_globs にマッチするものから、トップレベルの submodule
    ディレクトリを抽出する。

    submodule pin 更新は gitlink path (例: "vendor/foo") として単一 entry で記録され、
    package 内ファイル変更は "vendor/foo/bar.py" 形式になる。両ケースとも先頭 2
    セグメントに正規化して集約する。
    """
    affected: set[str] = set()
    for path in changes:
        if not any(fnmatch.fnmatch(path, pattern) for pattern in submodule_globs):
            continue
        parts = path.split("/")
        affected.add("/".join(parts[:2]) if len(parts) >= 2 else path)
    return affected


def build_reminder(affected: set[str], bypass_marker: str) -> str:
    """block 時の reminder メッセージを構築"""
    lines = [
        "🚫 submodule 変更を含む PR を作成しようとしていますが、",
        "    CI-equivalent test の実行確認 (marker) が command に含まれていません。",
        "",
        "影響を受ける submodule:",
    ]
    for path in sorted(affected):
        lines.append(f"  - {path}")
    lines.extend(
        [
            "",
            f"テスト pass を確認後、command 内に '{bypass_marker}' marker を含めて再実行してください。",
            "例:",
            "",
            f"  # {bypass_marker}: ran `<CI-equivalent test command>` -> N passed",
            '  gh pr create --title "..." --body "..."',
            "",
            "→ 具体的な CI-equivalent test コマンドは導入先の testing ルール文書を参照してください。",
        ]
    )
    return "\n".join(lines)


def emit_block(reason: str) -> None:
    """Deny the tool call with a structured reason (delegates to hook_common)."""
    emit_pretooluse_deny(reason)


def main() -> None:
    root = find_project_root()
    log_dir = get_log_dir(root)
    log_debug(log_dir, "=== Pre-PR Submodule Check Hook ===")

    try:
        input_data: dict[str, Any] = json.load(sys.stdin)
        tool_input = input_data.get("tool_input", {})
        command = tool_input.get("command") or tool_input.get("cmd", "")
        if not command or not is_gh_pr_create(command):
            sys.exit(0)

        log_debug(log_dir, f"gh pr create detected: {command[:200]}")

        rules = load_hook_rules("pre_pr_submodule_check", root)
        submodule_globs = rules.get("submodule_globs", [])
        if not submodule_globs:
            log_debug(log_dir, "submodule_globs empty, gate disabled")
            sys.exit(0)

        bypass_marker = rules.get("bypass_marker", "CI-EQUIV-TESTED")

        changes = get_changed_paths(root)
        if not changes:
            log_debug(log_dir, "no changes (or git diff failed), allow")
            sys.exit(0)

        affected = identify_affected_submodules(changes, submodule_globs)
        if not affected:
            log_debug(log_dir, f"changes outside submodule_globs: {changes}")
            sys.exit(0)

        if bypass_marker in command:
            log_debug(log_dir, f"bypass marker '{bypass_marker}' detected, allow")
            sys.exit(0)

        reminder = build_reminder(affected, bypass_marker)
        log_debug(log_dir, f"BLOCKING: affected submodules={sorted(affected)}")
        emit_block(reminder)

    except json.JSONDecodeError as e:
        log_debug(log_dir, f"JSON decode error: {e}")
        sys.exit(0)
    except Exception as e:
        # hook は fail-open: 予期しない例外で PR 作成そのものはブロックしない
        log_debug(log_dir, f"Error: {e}")
        sys.exit(0)


if __name__ == "__main__":
    main()
