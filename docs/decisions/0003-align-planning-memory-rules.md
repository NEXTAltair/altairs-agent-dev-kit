---
type: Decision
title: "ADR-0003: planning-memory を documentation-maintenance / git-workflow に整合させる"
description: ADR 索引の手編集指示を生成方式に統一し、具体パスをプロジェクト固有注記でゲートし、Proposed ADR の worktree 隔離を相互参照する
timestamp: 2026-07-05
status: Accepted
---
# ADR-0003: planning-memory を documentation-maintenance / git-workflow に整合させる

## Context

rules 同士が矛盾していた (監査 issue #8):

1. `planning-memory.md` は「`docs/decisions/README.md` のインデックスを更新」(手編集) を指示する一方、
   `documentation-maintenance.md` は「索引ファイルへの手編集は禁止、frontmatter を SSoT に生成する」を核心ルールとしていた。
2. `documentation-maintenance.md` は「汎用原則を記述する文書に具体パスを書き込まない」と定めるが、
   `planning-memory.md` 自身が `docs/decisions/` 等を無警告のまま普遍パスとして記載していた。
3. `git-workflow.md` は Proposed ADR の worktree 隔離を要求するが、`planning-memory.md` の
   「計画完了後に ADR を追加」手順は隔離に言及せず、従うと main 直下 draft ADR が発生し得た。
4. agents 4 本が Write 権限なしで `Write docs/decisions/` を指示されていた (これは issue #2 の
   書き直しで「親エージェントへ報告し起票を委譲」に解消済み)。

## Decision

`planning-memory.md` を次の通り改訂する:

- ADR 索引は**手編集しない**。documentation-maintenance の生成方式 (okf-bundle) への
  ポインタに置き換える。
- 具体パス (`docs/decisions/` 等) は「代表的な既定パスの例」とし、冒頭の
  `> プロジェクト固有:` 注記で導入先が実パスを追記する形にゲートする (他ルールと同形式)。
- ADR 保存手順に git-workflow の「Proposed ADR は worktree 隔離、Accepted まで main へ push しない」
  への相互参照を追加する。
- 旧「長期記憶ストア併用時の追記」注記は削除 (ADR-0002 の LTM 全削除決定に従う)。

agents の ADR 起票は「親エージェントへ委譲」を正とする (issue #1 決定コメント B3。
調査系サブエージェントに書き込み権限を持たせない原則を維持)。

## Rationale

代替案は documentation-maintenance 側を緩めて手編集を許すことだったが、索引 drift を
構造的に防ぐという生成方式の利点を失うため退けた。ルール間の優先順位を暗黙に読者へ
委ねるのではなく、矛盾する記述自体を除去する。

## Consequences

- ADR を追加する作業者は索引再生成 (okf-bundle) を実行する。このリポジトリの `docs/index.md` も同様。
- rules に新たな具体パスを書く場合は `> プロジェクト固有:` 注記でゲートする規約を維持する。
- 残る frontmatter/lint の統一は issue #9、papercut 類は issue #11 で扱う。
