---
type: Decision
title: "ADR-0002: OpenClaw/clawdbot 長期記憶インフラの残骸を除去する"
description: 移植元の私設メモリサービスへの参照を agents/skills から全削除し、長期記憶連携の抽象フックも残さない
timestamp: 2026-07-05
status: Accepted
---
# ADR-0002: OpenClaw/clawdbot 長期記憶インフラの残骸を除去する

## Context

移植元プロジェクトの私設メモリサービス (OpenClaw LTM / clawdbot) への参照 —
`http://host.docker.internal:18789/hooks/<project>-memory` への curl、
`~/.clawdbot/clawdbot.json` からのトークン取得、Notion DB 前提、存在しない
`ltm_search.py` / `ltm_latest.py` の呼び出し — が agents 4 本
(investigation / library-research / query-analyzer / solutions) と
`skills/context7-openclaw-research` に生きたまま残っていた (監査 issue #2)。
導入先には存在しないインフラをコピペ可能な形で教える状態だった。

## Decision

親 issue #1 の決定 (2026-07-05、A2「LTM 連携はまるごと削除」) に従い:

- agents 4 本の LTM 関連セクションを削除し、「プロジェクトの既存記録
  (`docs/decisions/` 等) を Read で参照し、永続化が必要なら親エージェントへ
  報告して起票を委ねる」という Records-First 記述に置換した。
- `skills/context7-openclaw-research` はスキルの中核が OpenClaw 前提のため
  ディレクトリごと削除した (skills 14 本 → 13 本)。
- `skills/check-existing` の `dependencies: [context7-openclaw-research]` と
  長期記憶スキル参照を除去し、一次ドキュメント取得は Context7 MCP / WebFetch に変更した。
- CI の汎用性 grep gate に `host.docker.internal|clawdbot|18789|HOOK_TOKEN|
  ltm_search|ltm_latest|OpenClaw` を追加して再発を防止する。

## Rationale

代替案は「抽象フックとして残す」(具体エンドポイントのみ削除) だったが、
ユーザー決定で全削除が選択された。抽象フックはこのキットが提供しない機能への
参照であり、導入先で実体を持たない指示は誤誘導になるため。将来メモリ基盤を
足す場合は専用スキルとして追加し、agents からはそのスキル名を参照する。

## Consequences

- agents の調査ワークフローはローカル記録 (docs/decisions 等) + WebSearch のみで完結する。
- ADR 起票の主体は親エージェント (agents 4 本は Write を持たない)。文言の全体統一は issue #8 で行う。
- 削除セクション内にあった sed 破損行はこの変更で消滅。残りの破損は issue #4 で修復する。
- skills 数のドキュメント記載は 13 に更新済み。今後の増減時は README / adoption.md を追従させる。
