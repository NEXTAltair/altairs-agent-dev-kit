---
type: Decision
title: "ADR-0007: unknowns discovery を汎用ルールとして追加する"
description: AI エージェントがプロンプト・計画・ルールに書かれていない前提を推測で埋める問題を、Fable 固有の skill ではなく作業横断の unknowns discovery ルールとして扱う
timestamp: 2026-07-07
status: Accepted
---
# ADR-0007: unknowns discovery を汎用ルールとして追加する

## Context

AI エージェントの失敗は、モデル能力不足だけでなく、ユーザーが渡したプロンプト・skill・rules・
context と、実際の作業対象であるコードベース・ユーザー意図・運用制約との間にある差分を、
エージェントが推測で埋めることで起きる。

この差分は特定モデルや特定ツールだけの問題ではない。Claude Code、Codex、IDE 統合型エージェント、
外部オーケストレータのいずれでも、複雑な実装・調査・レビューでは同じ形で発生する。

既存の kit には以下がある:

- `planning-memory.md`: 過去判断・教訓を事前確認する
- `check-existing`: 要件ヒアリングと既存解調査を行う
- `goal-prompt-crafter`: 測定可能な完了条件・仮定・検証方法を定義する
- `testing.md` / `pr-maintainer`: 検証と PR 後の修正ループを扱う

一方で、「何をまだ知らないか」「それを inspect / test / ask / assume / defer のどれで扱うか」
を通常の作業全体に横断適用するルールはなかった。

## Decision

Fable など特定モデル向けの skill ではなく、`rules/unknowns-discovery.md` を追加する。

このルールは以下を定める:

- 作業前に `Known Facts` / `Unknowns` / `Assumptions` / `Resolution Plan` をリスクに応じて整理する
- unknown を `inspect` / `test` / `ask` / `assume` / `defer` に分類する
- 実装中に前提崩れやスコープ拡大を見つけた場合は手を止めて再計画する
- 成果報告や PR description に `Verified` / `Assumptions` / `Not Verified` / `Follow-up` を残す
- 小さな作業では軽量に適用し、typo や単純 read-only タスクではスキップ可能にする

## Rationale

skill にすると、ユーザーやエージェントが明示的に起動した時だけ効く。unknowns の扱いは
実装・調査・レビュー・PR 保守のすべてに関わるため、導入先で常時読まれる rules 層に置く方が
適切である。

また、すべての unknown をユーザー質問に変換すると作業が止まりすぎる。反対に、すべてを推測で
進めると意図違いの変更になる。分類ルールを置くことで、ローカル調査で解消できるものは自力で確認し、
価値判断やスコープ判断だけをユーザーに戻す運用にできる。

## Consequences

- rules は 9 本から 10 本になる。
- 導入先は必要に応じて `response_monitor` hook の NG ワードに推測表現を追加し、このルールを
  機械的に補助できる。
- 今後、agent 定義や skill が通常作業の入口・途中・出口を記述する場合は、
  `unknowns-discovery.md` の分類語彙 (`inspect` / `test` / `ask` / `assume` / `defer`) を
  参照できる。
