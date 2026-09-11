---
name: okf-bundle
description: "Record every agent-facing development document as part of an Open Knowledge Format (OKF) bundle: design docs, plans, investigation notes, runbooks, specs, lessons-learned, ADRs, glossaries, knowledge bases. Ensure each markdown file has OKF frontmatter (required type, plus title/description/tags/timestamp/status), keep frontmatter the single source of truth, and regenerate the derived index.md (and optional table) from it. Use whenever creating or editing any markdown under docs/ (or the project's doc root) that an agent will read later, when asked to 「ドキュメント書いて」「設計書」「調査メモ」「runbook」「ADR」, or when an index looks stale. Do NOT use for: README / CLAUDE.md / AGENTS.md (guidance layer), generated files, or code comments."
metadata:
  short-description: 任意プロジェクトの md 群を OKF バンドルとして保守（frontmatter=SSoT → index/表を生成・検証）。
---

# OKF Bundle Maintenance

Markdown ファイルのディレクトリを [Open Knowledge Format (OKF)](https://github.com/GoogleCloudPlatform/knowledge-catalog/blob/main/okf/SPEC.md)
バンドルとして保守する汎用スキル。**frontmatter を唯一の正準ソース (SSoT)** とし、
`index.md` や人間向けテーブルは frontmatter から生成する派生物として扱う。

プロジェクト非依存・stdlib only。`--bundle-root` で対象ディレクトリを受け取るので、
ADR・知識ベース・用語集など任意の OKF バンドルに使える。

## 対象: エージェントが読む開発ドキュメントすべて

ADR や用語集に限らない。**エージェントが後で読む前提で書く開発中ドキュメントは、種類を問わず
この方式で記録する。** 対象の例:

| 種類 | `type` の例 | 典型的な置き場 |
|---|---|---|
| 設計判断 | `ADR` | `docs/decisions/` |
| 設計書・仕様 | `Design`, `Spec` | `docs/design/`, `docs/specs/` |
| 実装計画・タスク分解 | `Plan` | `docs/plans/` |
| 調査メモ・検証記録 | `Investigation`, `Experiment` | `docs/investigations/` |
| 手順書 | `Runbook`, `Guide` | `docs/` |
| 参照資料・一覧 | `Reference` | `docs/` |
| 教訓・バグパターン | `Lesson` | `docs/lessons-learned/` |
| 用語集・概念 | `Concept`, `Glossary` | `docs/knowledge/` |

`type` の語彙はプロジェクトで固定してよいが、**新しい文書に frontmatter を付けない選択肢は無い**。
対象外は README (人間向け入口)、`CLAUDE.md` / `AGENTS.md` (指針層)、生成物 (`index.md` 等)、コードコメント。

frontmatter に置く推奨キー:

```yaml
---
type: Investigation
title: 短い題名
description: 一文の要約 (索引にそのまま出る)
timestamp: 2026-01-01        # ISO 8601。最終更新日
status: draft | active | superseded   # 状態はここ。本文の散文に書かない
tags: [hooks, uv]
---
```

新しい文書を作るときは、本文より先に frontmatter を書く。既存文書を大きく編集したら `timestamp` を更新する。

## OKF の必須ルール (SPEC v0.1)

- frontmatter の必須キーは **`type` のみ**。`title` / `description` / `tags` / `timestamp` は任意。
- スカラー値メタデータ (status / timestamp 等) は **frontmatter に置く**。本文の散文に書かない。
- `index.md` / `log.md` は予約ファイル名。概念ドキュメントには使わない。`log.md` の日付は ISO 8601。
- `index.md` / 生成テーブルは**生成物**。手編集しない。

## スクリプト (scripts/)

すべて `python3` 単体 (依存なし) で動く。

| スクリプト | 役割 |
|---|---|
| `okf_validate.py --bundle-root DIR` | frontmatter 検証 (必須 `type` / ISO `timestamp` / `--require`・`--exclude`・`--skip-missing` 可) |
| `okf_index.py --bundle-root DIR --index` | OKF `index.md` (箇条書き) を生成 |
| `okf_index.py --bundle-root DIR --table --columns ... --link-column ...` | 列を frontmatter キーで指定する Markdown テーブルを生成 |

`okf_index.py` の `--check` は書き込まず「生成物が最新か」だけ検証する (drift 検出)。
`--table-output` 先に `<!-- OKF-TABLE:START -->` / `<!-- OKF-TABLE:END -->` マーカーがあれば、
その間だけ置換するのでテーブル前後の散文を保持できる。

`okf_validate.py --skip-missing` は frontmatter が無いファイルを違反にせず除外する
(段階的移行 / lazy migration 用)。frontmatter 未付与の既存ドキュメントを許容しつつ、
付与済みのものだけ `type` 必須 / ISO `timestamp` を強制したいバンドルで使う。
全件 frontmatter 必須のバンドル (例: ADR) には付けない。

## Workflow (Agent が判断で起動)

対象ドキュメントを追加・編集・改番したら:

1. **検証**: `python3 <skill>/scripts/okf_validate.py --bundle-root <DIR> [--exclude README.md]`
   — frontmatter 欠落や必須キー漏れを補う。
2. **再生成**: `python3 <skill>/scripts/okf_index.py --bundle-root <DIR> --index ...`
   (必要なら `--table ...` も) で派生ビューを更新する。
3. **コミット**: 生成物を含めてコミットする (docs chore は main 直 push 可なプロジェクトもある)。

CI 自走に頼らず Agent の判断で回す。許容するのは「実行漏れ (索引が一時的に古い)」だけで、
生成は決定論なので内容ドリフトは発生しない。**索引やテーブルを手で書き起こさない**
(書式ブレ・転記ミスの温床)。

## プロジェクト固有の責務 (スキル外)

「その概念を参照しているコードが概念より新しい」式の drift 検出 (REFERENCE-DRIFT) は
各プロジェクトの enactment surface に依存するため、本スキルには含めない。プロジェクト側の
専用ツール (例: ADR とソースの整合を見る drift チェッカー) が担う。

## 使用例

```bash
# ADR バンドル検証 (全件 frontmatter 必須)
python3 <skill-dir>/scripts/okf_validate.py --bundle-root docs/decisions --exclude README.md
# index.md + README テーブルを再生成
make adr-index   # 内部で okf_index.py を呼ぶ (Makefile target がある場合)

# 通常ドキュメント検証 (lazy migration: 未付与は skip、付与済みのみ検証)
python3 <skill-dir>/scripts/okf_validate.py --bundle-root docs --skip-missing
```
