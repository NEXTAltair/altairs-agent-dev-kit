#!/usr/bin/env python3
"""hook 共通基盤: プロジェクトルート検出とルールのマージ読込。

kit の hook はプロジェクト固有パスをハードコードしない。
具体値は環境変数と導入先の override JSON から解決する。
"""

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any, NoReturn

def _default_rules_dir() -> Path:
    """default rules ディレクトリを配置形態に応じて解決する。

    repo/plugin 配置 (hooks/scripts/ → hooks/rules/) を優先し、
    install.sh のフラット配置 (.claude/hooks/ → .claude/hooks/rules/) に
    フォールバックする。
    """
    for candidate in (Path(__file__).parent.parent / "rules", Path(__file__).parent / "rules"):
        if candidate.is_dir():
            return candidate
    return Path(__file__).parent.parent / "rules"


DEFAULT_RULES_DIR = _default_rules_dir()


def find_project_root() -> Path:
    env = os.environ.get("CLAUDE_PROJECT_DIR")
    if env:
        return Path(env)
    try:
        out = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            capture_output=True, text=True, check=True, timeout=5,
        )
        return Path(out.stdout.strip()).resolve()
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired, FileNotFoundError):
        return Path.cwd()


def get_log_dir(root: Path) -> Path:
    return root / ".claude" / "logs"


def deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    merged: dict[str, Any] = dict(base)
    for key, value in override.items():
        if key in merged and isinstance(merged[key], dict) and isinstance(value, dict):
            merged[key] = deep_merge(merged[key], value)
        elif key in merged and isinstance(merged[key], list) and isinstance(value, list):
            merged[key] = merged[key] + value
        else:
            merged[key] = value
    return merged


def _read_json(path: Path) -> dict[str, Any]:
    try:
        with path.open(encoding="utf-8") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return {}


def load_hook_rules(hook_name: str, project_root: Path) -> dict[str, Any]:
    default = _read_json(DEFAULT_RULES_DIR / f"{hook_name}.default.json")
    override = _read_json(project_root / ".claude" / "hooks" / "rules" / f"{hook_name}.json")
    if not default:
        return override
    if not override:
        return default
    return deep_merge(default, override)


def emit_pretooluse_deny(reason: str) -> NoReturn:
    """PreToolUse hook でツール呼び出しを拒否する (Claude Code 現行スキーマ)。

    exit 0 + stdout JSON が正規の契約。exit 2 では stdout が読まれず
    reason が構造化情報として届かないため使わない。
    """
    print(
        json.dumps(
            {
                "hookSpecificOutput": {
                    "hookEventName": "PreToolUse",
                    "permissionDecision": "deny",
                    "permissionDecisionReason": reason,
                }
            },
            ensure_ascii=False,
        )
    )
    sys.exit(0)


def emit_stop_block(reason: str) -> NoReturn:
    """Stop hook で停止をブロックし、reason を Claude に返す (現行スキーマ)。"""
    print(json.dumps({"decision": "block", "reason": reason}, ensure_ascii=False))
    sys.exit(0)
