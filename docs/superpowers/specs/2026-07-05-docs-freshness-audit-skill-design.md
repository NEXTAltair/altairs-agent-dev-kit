---
type: Plan
title: docs-freshness-audit skill 設計
status: Approved
timestamp: 2026-07-05
tags: [documentation-maintenance, audit, skill]
---
# docs-freshness-audit skill 設計

## 背景 / 目的

LoRAIro の 2026-07-05 docs 棚卸しで、以下の陳腐化パターンが実証的に確認された:

- Superseded / DEPRECATED バナー付きのまま残置された仕様書 (バナーがあっても混乱源)
- 実在しないモジュール・旧アルゴリズムを記述し続ける spec (AutoCrop 旧検出ロジック等)
- 「確認事項 (未解決)」が実装で解決済みなのに放置
- git 追跡外 (gitignored) で `git status` に出ない残骸 (生成物 `_ui.py` 等)
- merge 済みなのに残っている実装計画ファイル

この監査ワークフローをテンプレート化し、任意リポジトリで定期実行できる汎用 skill
`docs-freshness-audit` として dev-kit に収録する。

## 全体構成: 3 フェーズ

### Phase 1: 機械スキャン (安価・毎回実行)

1. **死んだソースパス参照**: docs 中のソースパス風文字列 (`src/...` 等、パターンは
   導入先設定) を抽出し、ファイル存在をチェック
2. **死んだ内部リンク**: markdown 相対リンクの参照先存在チェック
3. **自己申告バナー検出**: `DEPRECATED` / `Superseded` / `要確認` / `TBD` / `未解決` 等の
   残置 grep
4. **鮮度ギャップ**: doc の最終 commit 日 vs 記述対象コードの churn (`git log`) を比較し、
   「コードだけ動いて doc が止まっている」ものを容疑化
5. **git から見えない残骸**: docs 配下 (および導入先が指定する監査対象ツリー) の
   ignored / untracked ファイルを `git status --ignored` で列挙
6. **消し忘れ計画ファイル**: 計画・設計出力ディレクトリの各ファイルから Issue/PR 番号を
   抽出し `gh` で状態照会。全て closed/merged なら「完了済み計画の残置」として削除候補。
   番号参照の無い計画は経過日数で容疑化して Phase 2 送り

出力: 容疑ファイル一覧 (根拠つき)。

### Phase 2: 意味監査 (容疑ファイルのみ・並列 agent)

Phase 1 の容疑ファイルに対し、read-only agent を並列 dispatch して spec vs 実装を照合。
skill にプロンプトテンプレートを同梱する:

- 入力: 対象 doc、比較先の実装パス候補、同領域をカバーしうる live docs 候補
- 出力: 乖離項目の箇条書き (doc 行番号 + 実装 file:line) + 判定4値
  - **概ね正確** / **部分修正で足りる** / **全面書き直しが必要** / **削除可 (live docs がカバー)**

### Phase 3: 処遇と実行 (ユーザー承認ゲート必須)

判定マトリクス:

| 状態 | 処遇 |
|---|---|
| live docs / 実装が同領域をカバー済み・固有価値なし | 削除 (git 履歴が保存する) |
| 現行機能の仕様だが記述が古い | 更新 (実装照合結果を反映) |
| 設計判断の記録としてのみ価値がある | ADR へ移送して原本削除 |
| 実装と一致 | 監査確認注記 (日付つき) を追記して維持 |
| 完了済み計画ファイル | 削除 |

- 候補一覧をユーザーに提示し、**承認を得てから**実行する (勝手に消さない)
- 実行後は導入先の検証コマンドを実行し、ドキュメント保守履歴に監査記録を追記する

## 汎用 / プロジェクト固有の分離 (dev-kit 2 層構造)

skill 本体は手順・プロンプト・判定マトリクスのみを持つ。以下は導入先の
CLAUDE.md / rules から拾う (skill 冒頭に「導入先設定の確認」ステップを置く):

| 項目 | LoRAIro での値 (例) |
|---|---|
| 検証コマンド | `make docs-okf`, `uv run python scripts/validate_docs.py` |
| 監査除外 | `docs/decisions/` `docs/design/` (バンドル)、生成物 |
| 計画出力ディレクトリ | `docs/plans/`, `docs/superpowers/plans|specs/` |
| 保守履歴の追記先 | `docs/documentation-maintenance.md` |
| 削除の運用 | docs chore は main 直 push 可 (git-workflow.md) |

## 定期化

skill 自体はトリガーを持たない。導入先の運用に委ねる:

- LoRAIro: 月次 dependency review と同枠で起動 (月次 = Phase 1 のみの軽監査、
  四半期 = Phase 1+2 の深監査)。`docs/documentation-maintenance.md` の
  四半期レビュー節にこの運用と skill 名を明記する

## 導入配線 (実装スコープ)

1. **dev-kit**: `skills/docs-freshness-audit/SKILL.md` 追加、README 収録数表を 15 本に更新、
   `scripts/lint_skills.py` pass を確認、docs/index.md 再生成 (OKF バンドル)
2. **dev-kit release**: v0.2.0 タグを切る (skills-lock の ref 参照先)
3. **LoRAIro**: `skills-lock.json` に `ref: v0.2.0` でエントリ追加 → `make skills-install` で
   復元確認、`docs/documentation-maintenance.md` に月次/四半期監査運用を追記
   (docs/tooling chore なので main 直 push)

## 非スコープ

- スケジューラによる自動起動 (cloud routine 化) — 環境依存のため見送り
- 機械スキャンの CI 常時実行化 — 必要になったら導入先で validate 系 script に取り込む
- ADR / design バンドルの内容監査 — バンドルは各々の管理規約 (ADR 0069 等) に委ねる
