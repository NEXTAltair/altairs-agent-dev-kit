---
type: Guide
title: 導入ガイド
description: agent_kit.py を使った Windows / macOS / Linux での導入手順、hook override 設定、CI 組み込み、その他の導入経路
timestamp: 2026-11-19
---
# 導入ガイド

`altairs-agent-dev-kit` を任意のリポジトリ・環境へ導入し、プロジェクト固有の設定を上書きする手順をまとめる。

## 1. 推奨: `scripts/agent_kit.py` による導入

Claude Code / Codex / Antigravity / OpenClaw のどれを使う場合も、OS を問わず `scripts/agent_kit.py` (Python 3.10+、標準ライブラリのみ) を使う。
部品は `global` (全プロジェクト共通の core 部品) と `project` (スタック依存の部品) に分かれる。配置先の一覧は [harness-matrix.md](harness-matrix.md)、設計判断は [ADR-0011](decisions/0011-multi-harness-framework.md) を参照。

### 前提ツール

| ツール | 必須条件 |
|---|---|
| Python 3.10+ | 必須 (Windows は `python`、macOS / Linux は `python3`) |
| Git | リポジトリ取得と `--components hooks` 使用時に必須 |
| Node.js (`npx`) | `skills` を導入する場合のみ必須 (`--components rules,agents` なら不要) |
| [uv](https://docs.astral.sh/uv/) | `python` profile の rules / hooks を使う場合に推奨 (未導入時は警告が出る) |

### 導入コマンド

**Windows (PowerShell)**:

```powershell
git clone --branch v0.7.0 --depth 1 https://github.com/NEXTAltair/altairs-agent-dev-kit.git
cd altairs-agent-dev-kit

python scripts/agent_kit.py list                                                      # 部品の分類を確認
python scripts/agent_kit.py install --scope global --dry-run                          # 予定を確認
python scripts/agent_kit.py install --scope global
python scripts/agent_kit.py install --scope project --target C:\path\to\your-repo
python scripts/agent_kit.py install --scope project --target C:\path\to\your-repo --components all  # hooks も含める
python scripts/agent_kit.py status --scope project --target C:\path\to\your-repo
```

**macOS / Linux**:

```bash
git clone --branch v0.7.0 --depth 1 https://github.com/NEXTAltair/altairs-agent-dev-kit.git
cd altairs-agent-dev-kit

python3 scripts/agent_kit.py install --scope global
python3 scripts/agent_kit.py install --scope project --target /path/to/your-repo
python3 scripts/agent_kit.py install --scope project --target /path/to/your-repo --components all
```

### Windows での注意点

- `install.sh` (Git Bash / WSL) や `python -X utf8` の指定は不要。PowerShell からそのまま `python scripts/agent_kit.py` を実行できる。
- `npx` (`npx.cmd`) は自動で解決される。
- symlink 作成権限 (開発者モード / 管理者権限) が無い環境では、`.claude/skills/` 等へのリンク作成時に自動的にコピーへフォールバックする。
- `--components all` (hooks 導入) で生成される Claude Code / Codex 向け起動設定は OS に合わせて `python` / `commandWindows` を出力する。

### 導入の仕組みと更新・削除

- **rules**: 原本は `rules/*.md`。Claude Code には `.claude/rules/`、Antigravity には `trigger:` frontmatter を付けて `.agents/rules/` へ配置する。Codex / OpenClaw には `AGENTS.md` の `<!-- agent-kit:begin -->` 〜 `<!-- agent-kit:end -->` に索引を書き込む (区画外の本文と `CLAUDE.md` には触れない)。
- **agents**: Claude Code は `agents/*.md`、Codex は `codex/agents/*.toml`、Antigravity は `antigravity/agents/*.md`。後二者は生成物であり、原本を変えたら `scripts/generate_codex_agents.py` / `scripts/generate_antigravity_agents.py` で再生成する。
- **skills**: `skills.sh` CLI (`npx skills@1 add`) に委譲し、実体を `.agents/skills/` (global は `~/.agents/skills/`) に置く。既存のハーネス側 skill は `--force` なしでは置き換えない。詳細は [skill-install-runbook.md](skill-install-runbook.md) を参照。
- **hooks**: project scope 専用 (Git repository root が前提)。内容ハッシュで固定した runtime と `.agent-kit/hooks.lock.json` を作成し、Codex 用 `.codex/hooks.json` を生成、Claude Code 用 JSON を標準出力へ表示する。`.claude/settings.json` には自動書き込みしないため、表示された JSON を `hooks` キーへマージする。`.agent-kit/runtimes/` と `.agent-kit/.pin-update` は `.gitignore` に追加し、lock と起動設定を Git 管理する。詳細は [hook-runtime.md](hook-runtime.md) を参照。
- **更新と削除**: 導入記録 (`.agent-kit/install.json`、global は `~/.agents/agent-kit/install.json`) に内容ハッシュを保存する。kit が配置して未変更のファイルだけを更新・削除 (`uninstall`) し、利用者が編集したファイルは `--force` を付けるまで保持する。

## 2. プロジェクト層 override の書き方 (hooks)

kit 同梱の `hooks/rules/*.default.json` は安全最小セットで、多くのゲートはデフォルト無効 (空リスト)。`hook_common.load_hook_rules()` が kit の default JSON と `<project_root>/.claude/hooks/rules/<name>.json` (override) を深いマージ (list は**連結**、dict は再帰マージ) で合成する。

> **注意**: list は置換ではなく連結される。default 側の個別エントリを無効化したい場合は、kit を fork して default JSON を編集する必要がある。

### `.claude/hooks/rules/pre_commands.json` — uv ガード等の有効化

```json
{
  "description": "このプロジェクト固有の pre_commands override",
  "blocked_commands": [
    {"pattern": "uv\\s+run.*--active", "reason": "venv 破損の原因になる", "suggestion": "uv run のみ使う (--active を外す)"}
  ],
  "worktree_uv_guard": true
}
```

- `blocked_commands` は kit デフォルト (git 破壊系コマンドのブロック) に連結される。
- `worktree_uv_guard: true` で、worktree 内の `uv` 実行に共有 venv (`UV_PROJECT_ENVIRONMENT`) を必須化する。

### `.claude/hooks/rules/pre_edit_worktree.json` — 保護ディレクトリの追加

共有 checkout 直下の保護ディレクトリ (既定: `src`, `tests`) への編集をブロックし、`.agents/worktree/` 配下での編集のみ許可する。保護対象は連結追加できる:

```json
{
  "protected_dirs": ["lib", "app"]
}
```

レビュー済み hotfix 等で一時的に回避したい場合は環境変数 `ALLOW_MAIN_EDIT=1` を付ける (恒常運用はしない)。

### `.claude/hooks/rules/response_monitor.json` — 応答品質 NG ワード

文体・スコープ規律のように lint でもモデル既定でも決まらないものに絞って設定する:

```json
{
  "ng_words": [
    {"keyword": "ついでに", "message": "指示外の追加作業は禁止"},
    {"keyword": "重要なのは", "message": "予告・総括の定型。中身を直接書け"},
    {"keyword": "不可欠", "message": "空虚な形容。強調ではなく主張の中身を説明しろ"},
    {"keywords": ["さらに", "また", "加えて"], "threshold": 3, "message": "接続詞の連打。情報を足さずに繋ぐな"}
  ]
}
```

- `keyword` (単数) と `keywords` + `threshold` (複数キーワードの合計回数) の両形式に対応。
- 引用符 (`「」` / `""` / `` ` ` ``) 内は判定から除外される。
- `exclude_patterns` (正規表現リスト) で特定表現だけをそのルールの判定対象から除外できる。

### `.claude/hooks/rules/consistency.json` — `required_env` 宣言

`scripts/check_config_consistency.py` が参照する。rules が前提とする環境変数が `.claude/settings.json` の `env` に実在するかを検査する:

```json
{
  "required_env": ["UV_PROJECT_ENVIRONMENT"]
}
```

## 3. 導入後の仕上げ

### rules のプロジェクト固有値を追記する

`rules/*.md` は汎用原則のみを含む。導入後、各 rule 内の「プロジェクト固有」注記 (共有 venv パス、CI filter 表、submodule 運用、ブランチ命名規則など) に自リポジトリの具体値を追記する。

### 設定整合 lint を CI に組み込む

`scripts/check_config_consistency.py` は、`settings.json` の `env` や hook 配線が rules の前提から外れていないかを検査する (exit 0: 整合 / exit 1: 違反あり):

```bash
python scripts/check_config_consistency.py --root /path/to/your-repo
```

GitHub Actions 組み込み例:

```yaml
- name: 設定整合 lint
  run: python3 path/to/altairs-agent-dev-kit/scripts/check_config_consistency.py --root .
```

検査内容:
1. `.claude/hooks/rules/consistency.json` の `required_env` が `.claude/settings.json` の `env` に存在するか
2. `settings.json` の hook 配線が参照するスクリプトが実在するか
3. `.claude/hooks/*.py` のうち未配線のもの (死んだ hook) が無いか

### プロジェクト固有スキルの育て方

ドメイン固有 skill は kit に同梱せず、各プロジェクトの `.agents/skills/` 配下に `<project>-<domain>` 形式で置く。実例として `NEXTAltair/LoRAIro` の以下を参照:

- [lorairo-qt-widget](https://github.com/NEXTAltair/LoRAIro/tree/main/.agents/skills/lorairo-qt-widget) — PySide6 ウィジェット実装パターン
- [lorairo-repository-pattern](https://github.com/NEXTAltair/LoRAIro/tree/main/.agents/skills/lorairo-repository-pattern) — SQLAlchemy repository パターン
- [lorairo-test-generator](https://github.com/NEXTAltair/LoRAIro/tree/main/.agents/skills/lorairo-test-generator) — pytest/pytest-qt テスト生成
- [lorairo-design-capture](https://github.com/NEXTAltair/LoRAIro/tree/main/.agents/skills/lorairo-design-capture) — デザインプロトタイプのキャプチャ手順

## 4. その他の導入経路 (個別ニーズ / 従来方式)

通常の導入は 1 章の `scripts/agent_kit.py` を推奨する。個別ニーズがある場合のみ以下を使う。

### Claude Code プラグイン (skills + agents + hooks をプラグイン機構で管理)

```bash
claude plugin marketplace add NEXTAltair/altairs-agent-dev-kit
claude plugin install altairs-agent-dev-kit@altairs-agent-dev-kit
```

hook を使うリポジトリでは、事前に固定タグの kit から runtime lock を作成しておく:

```bash
python scripts/install_harness.py --target /path/to/your-repo --runtime-only
```

plugin の `python_command` は Linux が既定の `python3`、Windows では `python` または Python 実行ファイルの絶対パスを設定する。plugin とプロジェクト設定で同じ hook を二重登録しないこと。詳細は [hook-runtime.md](hook-runtime.md) を参照。

### `skills.sh` 単体導入 (skill を 1 本ずつ選ぶ)

```bash
npx skills add "github:NEXTAltair/altairs-agent-dev-kit#v0.7.0" --skill check-existing
npx skills add "github:NEXTAltair/altairs-agent-dev-kit#v0.7.0" --skill pr-maintainer
```

同梱 skill 名は `skills/` 配下を参照。更新手順と footgun 対策は [skill-install-runbook.md](skill-install-runbook.md) を参照。

### 従来の `install.sh` / `install_harness.py` (Claude Code + Codex のみ)

v0.6 以前からの互換として残している。新規導入は `scripts/agent_kit.py` を使うこと。

- **Bash (`install.sh`)**: `./install.sh --target /path/to/your-repo --all` (個別フラグ: `--skills` / `--rules` / `--agents` / `--hooks` / `--codex` / `--force` / `--skill-source`。グローバル `uv` 必須)
- **hooks / Codex 単体 (`install_harness.py`)**: `python scripts/install_harness.py --target /path/to/your-repo --codex` (runtime 復元のみは `--runtime-only`)

## OKF バンドル運用について

`docs/` は [Open Knowledge Format (OKF)](https://github.com/GoogleCloudPlatform/knowledge-catalog/blob/main/okf/SPEC.md) バンドル。frontmatter が唯一の SSoT で、`docs/index.md` は生成物のため手編集しない。更新時は `skills/okf-bundle` (`okf_validate.py` / `okf_index.py`) で検証・再生成する。
