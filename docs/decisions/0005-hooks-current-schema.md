---
type: Decision
title: "ADR-0005: hooks を Claude Code 現行スキーマに更新し WorktreeCreate は公式契約準拠で維持する"
description: PreToolUse のブロックを permissionDecision=deny + exit 0 に統一し、監査時に「存在しない」とされた WorktreeCreate は公式ドキュメントで実在を確認して維持・契約準拠化した
timestamp: 2026-07-05
status: Accepted
---
# ADR-0005: hooks を Claude Code 現行スキーマに更新し WorktreeCreate は公式契約準拠で維持する

## Context

監査 issue #3 は 2 つの問題を指摘していた:

1. PreToolUse hook 3 本が stdout に旧形式 `{"decision": "block"}` を出してから `exit(2)` して
   おり、exit 2 のとき Claude Code は stderr を読むため stdout の JSON は誰にも読まれない
   死にコードだった (ブロック自体は exit 2 側で偶然機能)。
2. `WorktreeCreate` は「現行イベントに存在しない死に配線」とされ、削除が決定されていた。

しかし実装前に公式ドキュメント (code.claude.com/docs/en/hooks) を確認した結果、
**`WorktreeCreate` は正式な hook イベントである**ことが判明した (`claude --worktree <name>`
とサブエージェントの `isolation: "worktree"` で発火する provider。成功 = exit 0 + stdout に
パス、非ゼロ exit は全て失敗扱い)。監査時の指摘 (および親 issue #1 の削除決定の前提) が
誤りだったため、この点は決定を反転する。

## Decision

- **PreToolUse 3 本** (pre_commands / pre_edit_worktree / pre_pr_submodule_check):
  ブロックを `hookSpecificOutput.permissionDecision: "deny"` + `permissionDecisionReason` +
  **exit 0** に統一。共通ヘルパー `hook_common.emit_pretooluse_deny()` に集約。
- **Stop** (response_monitor): `{"decision": "block", "reason": ...}` + **exit 0** に統一
  (`hook_common.emit_stop_block()`)。`exit(2)` と stderr 出力は全 hook から廃止。
- **WorktreeCreate は維持**し、公式契約に準拠させる: payload の `worktree_name`
  (旧 `name` にフォールバック) と `source_ref` を尊重。hooks.json の配線は残す。
- hooks.json の `Stop` から不要な `"matcher": "*"` を除去 (matcher は tool 系イベント用)。

## Rationale

exit 2 + stderr でもブロック自体は機能するが、構造化された deny 理由が UI に届かず、
permission フローとの統合 (ask 等への拡張) もできない。現行スキーマの正規形に寄せる。
WorktreeCreate の削除回避は「一次情報で確認してから壊す」の実践結果であり、
監査結論であっても外部仕様への言及は公式ドキュメントで裏を取る教訓を残す。

## Consequences

- テストの契約が変わる: ブロック判定は returncode ではなく stdout JSON
  (`tests/conftest.py` の `pretooluse_deny_reason()` / `stop_block_reason()`) で行う。
- `hook_worktree_create.py` の実発火テストは issue #10 で追加する。
- 親 issue #1 の決定コメント A1 のうち「WorktreeCreate 削除」は本 ADR で上書きされる
  (issue #3 にも訂正コメントを残す)。
