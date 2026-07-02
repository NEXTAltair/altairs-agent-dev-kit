# altairs-agent-dev-kit

AI エージェント (Claude Code / Codex) 向けの開発標準一式 — skills / rules / hooks / agents / Codex 設定 —
を、プロジェクト固有の値を含まない汎用コアとして切り出し、任意のリポジトリへ導入・追従できる形で配布する kit。

「事故 → 原則 → 機械的強制」というサイクルで育った運用知見 (破壊的コマンドのブロック、
worktree 分離、設定と文書の整合チェックなど) を、新規・既存を問わずどのリポジトリでも
再利用できるようにすることが目的。汎用コア (本リポジトリ) とプロジェクト層 (導入先の
`CLAUDE.md` / `.claude/rules/` / hook override JSON) を分離し、導入先は自分の具体値だけを
上書きすればよい。

## 収録物

| 種別 | 数 | 場所 |
|---|---|---|
| skills | 13 本 | `skills/` (skills.sh 互換構造、プラグインからも参照) |
| rules | 9 本 | `rules/*.md` (コーディング規約・git 運用・テスト・ログ・セキュリティ・ドキュメント保守等) |
| hooks | 5 本 + 共通基盤 | `hooks/scripts/*.py` (+ `hook_common.py`)、設定は `hooks/rules/*.default.json` |
| agents | 10 本 | `agents/*.md` (Claude Code サブエージェント定義) |
| Codex 設定 | 一式 | `codex/config.toml.template`, `codex/agents/*.toml` |
| 設定整合 lint | 1本 | `scripts/check_config_consistency.py` |
| skill lint | 1本 | `scripts/lint_skills.py` |

## クイックスタート

```bash
git clone https://github.com/NEXTAltair/altairs-agent-dev-kit.git
cd altairs-agent-dev-kit
./install.sh --target /path/to/your-repo --all
```

| フラグ | 導入内容 |
|---|---|
| `--skills` | skills 13 本 → `<repo>/.claude/skills/` (skills.sh CLI 経由、**要 Node.js/npx**) |
| `--rules` | `rules/*.md` → `<repo>/.claude/rules/` |
| `--agents` | `agents/*.md` → `<repo>/.claude/agents/` |
| `--hooks` | hooks スクリプト + default rules → `<repo>/.claude/hooks/` |
| `--codex` | `.codex/config.toml` + `agents/*.toml` |
| `--all` | 上記すべて |
| `--force` | 既存ファイルも上書き (`--force` なしは `SKIP (exists)`) |

`--hooks` はコピー後に `settings.json` へ配線すべき hook 設定を標準出力に表示するだけなので、
表示された JSON を `<repo>/.claude/settings.json` の `hooks` キーへ手動で貼り付けること。

その他の導入経路 (Claude Code プラグイン / skills.sh 単体) は
[docs/adoption.md](docs/adoption.md) を参照。

## 導入後の最小 override

kit 同梱の hook デフォルトはほとんどのゲートが無効 (空リスト) になっている。
有効化したいものだけ `<repo>/.claude/hooks/rules/*.json` に override を置く:

```json
// .claude/hooks/rules/consistency.json
{
  "required_env": ["UV_PROJECT_ENVIRONMENT"]
}
```

```json
// .claude/hooks/rules/response_monitor.json
{
  "ng_words": [
    {"keyword": "だろう", "message": "推測は禁止。確認した？テストした？"}
  ]
}
```

override の詳しい書き方 (`pre_commands.json` の uv ガード有効化例、`response_monitor.json` の
NG ワード例、rules の追記ポイント、`check_config_consistency.py` の CI 組み込み) は
[docs/adoption.md](docs/adoption.md) を参照。同梱しないサードパーティ skill の推奨インストール
リストは [docs/third-party-skills.md](docs/third-party-skills.md) を参照。

## 設計原則

1. **事故 → 原則 → 機械的強制**: ルールは実際の事故を発端とし、人間やエージェントの注意力ではなく hook で機械的にブロックする
2. **更新頻度で文書層を分ける**: 指針層 / 詳細層 (rules) / 実装層 (hook コード) を分離し、頻度の違う情報を混ぜない
3. **frontmatter = SSoT、索引は生成物**: メタデータは frontmatter に一本化し、索引の手編集を禁止する
4. **コマンド形状を変えず環境で設定する**: CLI の承認摩擦を避けるため、env prefix を毎回付けず設定ファイルに1回常設する
5. **設定と文書の整合を lint する**: 「rules が約束する env/hook 配線が settings に実在するか」を検証するチェックを提供する

## ドキュメント

- [docs/adoption.md](docs/adoption.md) — 導入手順の詳細とプロジェクト層 override の書き方
- [docs/third-party-skills.md](docs/third-party-skills.md) — 同梱しないサードパーティ skill の推奨インストールリスト
- [docs/superpowers/specs/2026-07-02-altairs-agent-dev-kit-design.md](docs/superpowers/specs/2026-07-02-altairs-agent-dev-kit-design.md) — 設計書 (原則・構成・決定事項の全体)
- [docs/superpowers/plans/2026-07-02-altairs-agent-dev-kit.md](docs/superpowers/plans/2026-07-02-altairs-agent-dev-kit.md) — 実装計画 (タスク分解)
