"""hook テスト共通ヘルパー。

hook のブロック契約 (Claude Code 現行スキーマ):
- PreToolUse: exit 0 + stdout JSON `hookSpecificOutput.permissionDecision == "deny"`
- Stop:       exit 0 + stdout JSON `decision == "block"`
許可時は exit 0 で stdout に何も出さない。
"""

import json
import subprocess


def pretooluse_deny_reason(result: subprocess.CompletedProcess) -> str | None:
    """PreToolUse hook の出力から deny 理由を取り出す。deny でなければ None。"""
    if result.returncode != 0 or not result.stdout.strip():
        return None
    data = json.loads(result.stdout)
    out = data.get("hookSpecificOutput", {})
    if out.get("permissionDecision") == "deny":
        return out.get("permissionDecisionReason", "")
    return None


def stop_block_reason(result: subprocess.CompletedProcess) -> str | None:
    """Stop hook の出力から block 理由を取り出す。block でなければ None。"""
    if result.returncode != 0 or not result.stdout.strip():
        return None
    data = json.loads(result.stdout)
    if data.get("decision") == "block":
        return data.get("reason", "")
    return None
