---
type: Decision
title: "ADR-0004: 移植元ドメインの実例を中立化し、キットの対象スタックを明示する"
description: 画像アノテーション由来のスキーマ・モジュール名・パッケージ名を中立例に置換し、Python/uv (GUI 例は Qt) 前提を README で宣言する
timestamp: 2026-07-05
status: Accepted
---
# ADR-0004: 移植元ドメインの実例を中立化し、キットの対象スタックを明示する

## Context

`LoRAIro` という文字列は grep gate で除去済みだったが、移植元の**ドメイン実体**が
「汎用」の顔をして残っていた (監査 issue #6): query-analyzer の実スキーマ図
(Image/Tag/Caption/...) と実モジュール名 (`db_repository.py` 等)、db-schema-reviewer の
`images` テーブル例、security-reviewer の「image uploads」前提、
sqlalchemy-query-patterns の全コード例、interface-design の唯一の Domain Example
(AI 画像アノテーションツール)、lazy-import-refactor の私設パッケージ名
`image_annotator_lib`。導入先が非画像プロジェクトの場合そのまま誤誘導になる。

## Decision

親 issue #1 の決定 (A3「Python/uv キットと明示」) に従い:

- **中立例へ置換**: スキーマ・コード例は e-commerce 系の中立スキーマ
  (Order/OrderItem/Product/Category/Review 等) に統一。パッケージ名は `your_package`、
  interface-design の Domain Example はインシデント管理ダッシュボードに差し替え。
- **スタック宣言**: README 冒頭に「対象は Python/uv プロジェクト、GUI 例は PySide6/Qt
  スタック前提」を明示。`.venv` / `uv run` 前提の hooks はこの宣言により正当化される
  (設定可能化はしない)。
- **Qt 特化は汎用化しない**: build-error-resolver / code-reviewer / security-reviewer の
  PySide6/Qt 記述は残し、frontmatter description に「Python プロジェクト向け (GUI 例は
  PySide6/Qt スタック前提)」ラベルを付与。code-reviewer の規約例は「導入先規約を優先して
  読み替える」注記を追加。

## Rationale

完全な言語中立化 (uv 前提の設定可能化、Qt 記述の抽象化) は作業量に対して配布価値の
増分が小さく、キットの実利用者は Python/uv プロジェクトであるため。「何向けか」を
宣言する方が、暗黙に汎用を装うより誤誘導が少ない。

## Consequences

- 非 Python プロジェクトへの導入は公式サポート外 (rules の原則の流用は可)。
- 新しい例をドキュメントに書くときは中立スキーマ (Order/Product 系) を使う。
- issue #11 の「.venv/uv 設定可能化」チェックボックスは本 ADR を根拠にクローズする。
