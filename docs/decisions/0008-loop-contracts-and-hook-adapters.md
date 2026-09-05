---
type: Decision
title: "ADR-0008: PR autoloop は bounded time-based loop として扱い hook は adapter 分離する"
description: PR 保守 loop の観測可能な停止条件と、provider 別の起動設定・共有 policy・branch 固定 runtime の責務を定義する
timestamp: 2026-07-07
status: Accepted
---
# ADR-0008: PR autoloop は bounded time-based loop として扱い hook は adapter 分離する

## Context

Claude Code の loop 解説では、agentic loop を trigger / stop criteria / primitive / task type で
分類し、短い作業は turn-based、検証可能な完了条件がある作業は goal-based、外部状態を定期確認する
作業は time-based、継続的な定型作業は proactive loop として扱う。

本 kit の `pr-autoloop` は、PR 作成後に GitHub の CI・bot review・inline comment・mergeability を
数分おきに確認し、必要なら修正 commit を積み、merge / escalation / timeout で停止する。
これは汎用の自律コーディング loop ではなく、外部システムである GitHub PR 状態を観測する
bounded time-based loop であり、停止条件は goal-based な state predicates で定義される。

また、provider ごとの hook 設定・入力フィールド・対応イベント・信頼確認は、各 client の契約に
合わせる必要がある。2026-09-05 の実装では PreToolUse の structured deny と Stop の block 出力を
両 provider で共有できる。単純に「Codex は簡易 payload、Claude は structured output」とは分類しない。

## Decision

- `pr-autoloop` を **bounded time-based loop with goal-based stop conditions** と明記する。
- PR 保守 loop の停止条件は自然言語の印象ではなく、`gh` で観測できる state predicates として扱う。
- Codex では Claude Code の `ScheduleWakeup` / `/schedule` 前提にせず、同一セッション内の
  inline polling で terminal state を報告する。
- hook は「共通 policy core」と「client-specific adapter」を分ける方針にする。
- Python から起動する登録コマンドを生成し、script 自体の実行ビットや GNU timeout に依存しない。
- runtime は作業 checkout の lock で固定し、実装・共通モジュール・defaults を一式で検証する。
  override は作業 checkout、共有 venv は共有 checkout から取得する。

## Rationale

PR 保守は、CI やレビュー結果のような外部状態が変化するまで待つ作業であり、turn-based な通常実装や
proactive な常駐 routine とは異なる。loop 種別を明記すると、poll interval、timeout、repair limit、
merge gate を設計要素として扱える。

hook は判定ロジックを共有できるが、起動方法や入力を同一と仮定すると client 間で破綻する。
実行ビットの無い script の直接起動や、rules だけの worktree を runtime とみなす判定を避け、
共通起動入口から検証済み runtime へ到達する。詳細は [runtime 契約](../hook-runtime.md) に集約する。

## Consequences

- `pr-autoloop` は PR 保守専用 loop として位置づけ、汎用自律実装 loop として拡張しない。
- `goal-prompt-crafter` は、Codex や外部 orchestrator 向けには `/goal` 文字列ではなく
  state predicates / Definition of Done を生成する用途も担う。
- 現行実装は `hooks/bootstrap.py` と provider 別登録設定、共有 policy の組み合わせでこの責務を表す。
  固定のディレクトリ名を要求するためだけに再配置しない。

## References

- [Claude Code hooks](https://code.claude.com/docs/en/hooks)
- [Codex hooks](https://learn.chatgpt.com/ja-JP/docs/hooks)
