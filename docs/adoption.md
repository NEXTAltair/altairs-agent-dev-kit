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

hook を使うプロジェクトは Git repository が前提で、利用する kit 版の branch lock を事前に作成する。
別途 clone した kit で `git checkout v0.3.0` を実行し、次を実行する (Linux は `python3`):

```text
python -X utf8 scripts/install_harness.py --target <project-directory> --runtime-only
```

`.agent-kit/hooks.lock.json` を Git 管理し、runtime ディレクトリは ignore する。
plugin の `python_command` は Linux では既定の `python3`、Windows では `python` または
Python executable の絶対パスを設定する。hook は作業中 Git checkout 内で起動する。
plugin 更新でソースが変わっても branch pin は維持される。版更新・復元手順は
[runtime 契約](hook-runtime.md) を参照。plugin とプロジェクト設定で同じ hook を二重登録しない。

### 経路B: skills.sh (`npx skills add`) — skill 単体導入

skill を 1 本ずつ選んで導入したい場合:

```bash
npx skills add "github:NEXTAltair/altairs-agent-dev-kit#v0.3.0" --skill check-existing
npx skills add "github:NEXTAltair/altairs-agent-dev-kit#v0.3.0" --skill pr-maintainer
npx skills add "github:NEXTAltair/altairs-agent-dev-kit#v0.3.0" --skill okf-bundle
```

`skills/<name>/SKILL.md` が skills.sh の標準配置と一致しているため、任意の skill 名を
`--skill` に指定できる。同梱 skill 一覧は `skills/` 配下のディレクトリ名を参照。

### 経路C: install.sh — kit 全体を repo に導入する推奨経路

Claude Code プラグイン機構を使わない環境、または Codex 環境向け。`--all` を指定すれば
skills / rules / agents / hooks / Codex 設定をこれ 1 本で導入できる。

```bash
git clone https://github.com/NEXTAltair/altairs-agent-dev-kit.git
cd altairs-agent-dev-kit
git checkout v0.3.0
./install.sh --target /path/to/your-repo --all
```

個別フラグでの選択導入も可能 (`install.sh` の実引数):

```bash
./install.sh --target /path/to/your-repo --skills           # canonical 実体 + Claude symlink (要 Node.js/npx)
./install.sh --target /path/to/your-repo --rules            # rules/*.md → <repo>/.claude/rules/
./install.sh --target /path/to/your-repo --agents           # agents/*.md → <repo>/.claude/agents/
./install.sh --target /path/to/your-repo --hooks            # .agent-kit/runtimes/ + branch lock + 起動設定
./install.sh --target /path/to/your-repo --codex            # .codex/config.toml + agents/*.toml
./install.sh --target /path/to/your-repo --all --force      # kit 所有物を意図的に更新
```

`--skills` は skills.sh CLI (`npx skills@1 add`) に委譲する。既定の導入元は GitHub origin と
checkout 中の公開タグであり、`skills-lock.json` に GitHub source/ref を記録する。
実体は `.agents/skills/`、Claude 用の参照は `.claude/skills/` の相対 symlink。
symlink 非対応環境では Claude 側をコピーする。
既存の canonical または Claude 側 skill は `--force` なしでは保持する。kit 外の skill は更新しない。
ディレクトリが無く lock だけ残る場合も、固定版と異なる source への置換は拒否する。

**Node.js / npx が必要**で、npx は CLI 本体を初回に取得する。タグのない開発 checkout を試す場合だけ
`--skill-source /absolute/path/to/kit` を指定する。ローカル source の lock は配布用にコミットしない。
公開版の更新は新タグを checkout して `--skills --force` を実行し、lock 差分をレビューする。
詳しくは [skill 導入・更新 runbook](skill-install-runbook.md) を参照。

`--codex` が配布する `codex/agents/*.toml` は `agents/*.md` からの**生成物**であり、手編集
しない。`agents/*.md` を変更したら `uv run python scripts/generate_codex_agents.py` で再生成
する (CI が `--check` で drift を検出する)。語彙置換はハーネス名フレーズ `Claude Code` →
`Codex` のみで、裸の `Claude` / `Anthropic` (製品・API への言及) は置換しない。
`library-research` は WebFetch/WebSearch 前提のため Codex 版を生成しない。

`--hooks` は内容ハッシュで固定した runtime と `.agent-kit/hooks.lock.json` を作成し、
Claude の起動設定を標準出力へ表示する。`.claude/settings.json` には自動で書き込まないため、
表示された JSON を `hooks` キーへマージする。Codex の設定は `.codex/hooks.json` に生成する。
既存設定は `.new` へ提案し、consumer 固有 override は保持する。
lock と起動設定を Git 管理し、runtime 配置先は gitignore に追加する。
plugin 経路も事前に固定 kit から `--runtime-only` で branch lock を作成する。
旧フラット配置からの移行、固有 hook の接続、復元手順は [Hook runtime 契約](hook-runtime.md) を参照。

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

### `.claude/hooks/rules/pre_edit_worktree.json` — 保護ディレクトリの上書き

編集ゲート (`hook_pre_edit_worktree.py`) は共有 checkout 直下の保護ディレクトリ
(デフォルト: `src`, `tests`) への編集をブロックし、`.agents/worktree/` 配下での編集のみ
許可する。保護対象は override で **連結** 追加できる:

```json
{
  "protected_dirs": ["lib", "app"]
}
```

一時的にゲートを回避したい場合 (レビュー済みの hotfix 等) は環境変数
`ALLOW_MAIN_EDIT=1` を付けてツールを実行すると編集が許可される (恒常運用はしない)。
なお worktree の配置先 `.agents/worktree/` は kit の規約として固定
(git-workflow ルール・worktree provider・編集ゲートが同じパスを前提に連携する)。

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
    {"keywords": ["さらに", "また", "加えて"], "threshold": 3, "message": "接続詞の連打。情報を足さずに繋ぐな"},
    {"keywords": ["かもしれ"], "message": "推測は禁止",
     "exclude_patterns": ["かもしれない(が|けど)", "かもしれません(が|けど)"]}
  ]
}
```

`keyword` (単数) と `keywords` (複数、`threshold` と組み合わせて出現回数の合計で判定) の
どちらも使える。引用符 (`「」` / `""` / `` ` ` ``) 内の文字列はキーワード判定から除外される
(引用・言及・例示を誤検知しない)。`exclude_patterns` (正規表現リスト) に一致する部分は
**そのルールの判定対象からのみ**除去される — 譲歩構文やルール名の自己言及を許容しつつ
素の出現だけを検出したい場合に使う (不正な正規表現は無視される)。

### `.claude/hooks/rules/consistency.json` — required_env 宣言

`scripts/check_config_consistency.py` が読む設定。rules が前提とする環境変数を宣言し、
`.claude/settings.json` の `env` に実在するかを検査する:

```json
{
  "required_env": ["UV_PROJECT_ENVIRONMENT"]
}
```

## 3. rules の追記ポイント

`rules/*.md` は汎用原則のみを記載しており、具体パス・具体コマンド・Issue 番号などの
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
