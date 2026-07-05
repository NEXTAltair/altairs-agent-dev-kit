---
type: Guide
title: 導入ガイド
description: skills / rules / hooks / agents / Codex 設定を任意リポジトリへ導入する3経路と設定上書き方法
timestamp: 2026-07-02
---
# 導入ガイド

`altairs-agent-dev-kit` は skills / rules / hooks / agents / Codex 設定を任意のリポジトリへ導入するための
汎用コア kit。3 つの導入経路と、導入後にプロジェクト固有の値を上書きする方法をまとめる。

## 1. 導入経路

まず経路C (`install.sh --all`) を使えばよい。経路A/B は以下のような個別ニーズがある場合の
選択肢: 経路A は Claude Code のプラグイン機構による hook 自動配線が欲しい場合、経路B は
skill を 1 本だけ他 kit と混在導入したい場合に向く。

### 経路A: Claude Code プラグイン (skills + agents + hooks を一括)

本リポジトリは `.claude-plugin/marketplace.json` により self-marketplace 化されているため、
このリポジトリ自身を marketplace として登録できる。

```bash
claude plugin marketplace add NEXTAltair/altairs-agent-dev-kit
claude plugin install altairs-agent-dev-kit@altairs-agent-dev-kit
```

これで `skills/`, `agents/`, `hooks/hooks.json` が自動検出され、Claude Code から利用可能になる
(`.claude-plugin/plugin.json` の auto-discovery。`skills` / `agents` / `hooks` フィールドを
明示していないのはデフォルト検出パスと完全一致するため二重指定を避けた設計)。

### 経路B: skills.sh (`npx skills add`) — skill 単体導入

skill を 1 本ずつ選んで導入したい場合:

```bash
npx skills add github:NEXTAltair/altairs-agent-dev-kit --skill check-existing
npx skills add github:NEXTAltair/altairs-agent-dev-kit --skill pr-maintainer
npx skills add github:NEXTAltair/altairs-agent-dev-kit --skill okf-bundle
```

`skills/<name>/SKILL.md` が skills.sh の標準配置と一致しているため、任意の skill 名を
`--skill` に指定できる。同梱 skill 一覧は `skills/` 配下のディレクトリ名 (13 本) を参照。

### 経路C: install.sh — kit 全体を repo に導入する推奨経路

Claude Code プラグイン機構を使わない環境、または Codex 環境向け。`--all` を指定すれば
skills / rules / agents / hooks / Codex 設定をこれ 1 本で導入できる。

```bash
git clone https://github.com/NEXTAltair/altairs-agent-dev-kit.git
cd altairs-agent-dev-kit
./install.sh --target /path/to/your-repo --all
```

個別フラグでの選択導入も可能 (`install.sh` の実引数):

```bash
./install.sh --target /path/to/your-repo --skills           # skills 13本 → <repo>/.claude/skills/ (要 Node.js/npx)
./install.sh --target /path/to/your-repo --rules            # rules/*.md → <repo>/.claude/rules/
./install.sh --target /path/to/your-repo --agents           # agents/*.md → <repo>/.claude/agents/
./install.sh --target /path/to/your-repo --hooks            # hooks/scripts + rules/*.default.json → <repo>/.claude/hooks/
./install.sh --target /path/to/your-repo --codex            # .codex/config.toml + agents/*.toml
./install.sh --target /path/to/your-repo --all --force      # 既存ファイルも上書き (--force なしは SKIP)
```

`--skills` は skills.sh CLI (`npx skills add`) に委譲する非対話実行で、kit checkout
(`$KIT_DIR`) をソースに全 skill を `<repo>/.claude/skills/` へコピーする
(`--copy` 指定、node_modules へのシンボリックリンクにはしない)。npx は初回実行時に CLI
本体を自動取得するため事前の `npm install -g` は不要だが、**Node.js (npx コマンド) 自体は
必須**。npx が見つからない環境では `--skills` は何もコピーせず、エラーメッセージ付きで
exit 1 する (黙ったフォールバックはしない)。導入後に `npx skills update` を実行すれば
skills.sh の通常運用と同じ手順で追従アップデートできる。

`--codex` が配布する `codex/agents/*.toml` は `agents/*.md` からの**生成物**であり、手編集
しない。`agents/*.md` を変更したら `uv run python scripts/generate_codex_agents.py` で再生成
する (CI が `--check` で drift を検出する)。語彙置換はハーネス名フレーズ `Claude Code` →
`Codex` のみで、裸の `Claude` / `Anthropic` (製品・API への言及) は置換しない。
`library-research` は WebFetch/WebSearch 前提のため Codex 版を生成しない。

`--hooks` はコピー後に `settings.json` へ配線すべき hook 設定を標準出力に表示するのみで、
`<repo>/.claude/settings.json` への自動書き込みはしない。表示される JSON は `hooks/hooks.json`
(Claude Code プラグイン経路が使う `${CLAUDE_PLUGIN_ROOT}/hooks/scripts/...` 形式) をそのまま
出すのではなく、install.sh のフラット配置 (`<repo>/.claude/hooks/hook_*.py`、`scripts/` サブ
ディレクトリなし) に合わせて実パスへ書き換えたものを表示する。表示された JSON を手動で
`.claude/settings.json` の `hooks` キーへマージすること。

## 2. プロジェクト層 override の書き方

kit が同梱する `hooks/rules/*.default.json` は言語非依存の安全最小セットで、多くのゲートは
デフォルト無効 (空リスト)。`hook_common.load_hook_rules()` が
`hooks/rules/<name>.default.json` (kit 側) と `<project_root>/.claude/hooks/rules/<name>.json`
(導入先 override) を深いマージ (list は連結、dict は再帰マージ) で合成する。
override ファイルを置くだけで有効化でき、kit 側のデフォルトファイルは編集不要。
override の list は default の list に **連結** される (置換ではない)。default 側の
個別エントリを無効化したい場合は override だけでは実現できず、kit の default JSON 自体を
編集した fork を使う必要がある。

### `.claude/hooks/rules/pre_commands.json` — uv ガード等の有効化例

`uv sync`/`uv run --active` の並列実行事故のような、言語依存のガードを有効化したい場合の例:

```json
{
  "description": "このプロジェクト固有の pre_commands override",
  "blocked_commands": [
    {"pattern": "uv\\s+run.*--active", "reason": "venv 破損の原因になる", "suggestion": "uv run のみ使う (--active を外す)"}
  ],
  "worktree_uv_guard": true
}
```

- `blocked_commands` は kit デフォルトの配列に **連結** される (git 破壊系コマンドのブロックはそのまま有効)
- `worktree_uv_guard: true` で「worktree 内の `uv` 実行は共有 venv (`UV_PROJECT_ENVIRONMENT=...`) を明示しないとブロック」が有効化される

### `.claude/hooks/rules/response_monitor.json` — NG ワード例

kit デフォルトは `ng_words: []` (無効)。NG ワードはプロジェクト文化依存のため、
自分のプロジェクトで実際に運用している応答品質ルールを override に書く。
以下は実例 (`keyword` / `keywords`+`threshold` の両形式):

```json
{
  "ng_words": [
    {"keyword": "だろう", "message": "推測は禁止。確認した？テストした？"},
    {"keyword": "おそらく", "message": "推測は禁止。確認した？テストした？"},
    {"keyword": "ついでに", "message": "指示外の追加作業は禁止"},
    {"keyword": "重要なのは", "message": "予告・総括の定型。中身を直接書け"},
    {"keyword": "不可欠", "message": "空虚な形容。強調ではなく主張の中身を説明しろ"},
    {"keywords": ["さらに", "また", "加えて"], "threshold": 3, "message": "接続詞の連打。情報を足さずに繋ぐな"}
  ]
}
```

`keyword` (単数) と `keywords` (複数、`threshold` と組み合わせて出現回数の合計で判定) の
どちらも使える。引用符 (`「」` / `""` / `` ` ` ``) 内の文字列はキーワード判定から除外される
(引用・言及・例示を誤検知しない)。

### `.claude/hooks/rules/consistency.json` — required_env 宣言

`scripts/check_config_consistency.py` が読む設定。rules が前提とする環境変数を宣言し、
`.claude/settings.json` の `env` に実在するかを検査する:

```json
{
  "required_env": ["UV_PROJECT_ENVIRONMENT"]
}
```

## 3. rules の追記ポイント

`rules/*.md` (9 本) は汎用原則のみを記載しており、具体パス・具体コマンド・Issue 番号などの
プロジェクト固有値は意図的に含めていない。導入後は各 rule 内の「プロジェクト固有」に関する
記述箇所 (共有 venv の絶対パス、CI filter 表、submodule 運用、ブランチ命名規則など) に、
自分のリポジトリの具体値を追記すること。rules 本文の原則・判断フロー自体は変更不要。

## 4. プロジェクト固有スキルの実例

汎用化できないドメイン固有 skill は kit に同梱せず、各プロジェクトの `.agents/skills/` /
`.claude/skills/` に個別に置く。実例として `NEXTAltair/LoRAIro` の以下の skill を参照:

- [lorairo-qt-widget](https://github.com/NEXTAltair/LoRAIro/tree/main/.agents/skills/lorairo-qt-widget) — PySide6 ウィジェット実装パターン
- [lorairo-repository-pattern](https://github.com/NEXTAltair/LoRAIro/tree/main/.agents/skills/lorairo-repository-pattern) — SQLAlchemy repository パターン
- [lorairo-test-generator](https://github.com/NEXTAltair/LoRAIro/tree/main/.agents/skills/lorairo-test-generator) — pytest/pytest-qt テスト生成
- [lorairo-mem](https://github.com/NEXTAltair/LoRAIro/tree/main/.agents/skills/lorairo-mem) — 長期記憶 (OpenClaw LTM) 連携
- [lorairo-design-capture](https://github.com/NEXTAltair/LoRAIro/tree/main/.agents/skills/lorairo-design-capture) — デザインプロトタイプのキャプチャ手順

自分のプロジェクトでも、ドメイン固有の知識・ワークフローは同様に `<project>-<domain>` 形式の
skill として個別に育てるとよい。

## 5. `scripts/check_config_consistency.py` を CI / hook に組み込む

設定の巻き戻り事故 (`settings.json` から env や hook 配線が消えたのに rules は
「設定済み」と書いたままになる drift) を検出する lint。導入先リポジトリに対して実行する:

```bash
python3 scripts/check_config_consistency.py --root /path/to/your-repo
```

- exit 0: 整合 (`OK: 設定整合に問題なし`)
- exit 1: 違反あり (`VIOLATION: ...` を 1 行 1 件で標準出力に列挙)

検査内容:
1. `<root>/.claude/hooks/rules/consistency.json` の `required_env` の各キーが
   `<root>/.claude/settings.json` の `env` に存在するか
2. `settings.json` の hook 配線が参照するスクリプトが実在するか
3. `<root>/.claude/hooks/*.py` のうち `settings.json` に未配線のもの (死んだ hook) を警告

CI に組み込む場合の例 (GitHub Actions):

```yaml
- name: 設定整合 lint
  run: python3 path/to/altairs-agent-dev-kit/scripts/check_config_consistency.py --root .
```

pre-commit 相当で使う場合は PreToolUse hook から呼び出してもよい (kit 自体はこの lint を
hook として配線していない — CI かローカルの明示実行を想定した独立 CLI)。

## OKF バンドル運用について

`docs/` は [Open Knowledge Format (OKF)](https://github.com/GoogleCloudPlatform/knowledge-catalog/blob/main/okf/SPEC.md)
バンドル。frontmatter が唯一の SSoT で、`docs/index.md` は frontmatter から生成される派生物のため
手編集しない。更新は `skills/okf-bundle` スキル (`okf_validate.py` / `okf_index.py`) で行う。
