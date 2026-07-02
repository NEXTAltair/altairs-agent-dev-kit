# altairs-agent-dev-kit 設計書

- 日付: 2026-07-02
- ステータス: 承認待ち
- 発端: LoRAIro プロジェクトで育てた開発スキル・ルール・hook・agent 定義を汎用化し、どのリポジトリでも使い回せる独立リポジトリにする

## 目的

LoRAIro (`NEXTAltair/LoRAIro`) に蓄積された AI エージェント向け開発標準 (skills / rules / hooks / agents / Codex 設定) から、プロジェクト非依存の部分を抽出して単一リポジトリ `NEXTAltair/altairs-agent-dev-kit` として配布する。新規・既存を問わず任意のリポジトリへ導入でき、更新を追従できる形にする。

## 基本方針: 2層構造

本リポジトリには **プロジェクト名・絶対パス・Issue 番号・ADR 番号を一切含めない普遍的な内容だけ** を置く。

- **汎用層 (本リポジトリ)**: 原則・手順・hook の仕組み。例: 「並列で package manager の同期系操作を競合させない」「実装は worktree で行い PR を起票する」
- **プロジェクト層 (各導入先)**: 具体パス (`/workspaces/LoRAIro/.venv` 等)、CI filter 表、ADR 参照などを各自の `CLAUDE.md` / `.claude/rules/` / hook 設定 JSON で上書き補完

LoRAIro は最初の利用者となり、汎用化済みの内容を自リポジトリから削除して薄くする (二重管理による drift を防ぐ)。

## 配布方式: Claude Code プラグイン + skills.sh + install.sh

1 つのリポジトリで 3 つの導入経路をサポートする。

| 経路 | 対象 | 仕組み |
|---|---|---|
| Claude Code プラグイン | skills + agents + hooks 一括 | `.claude-plugin/plugin.json` (+ marketplace 登録) |
| skills.sh (`npx skills add`) | スキル単体 | ルート `skills/<name>/SKILL.md` 構造 (skills.sh が認識する標準配置) |
| `install.sh` | Codex (`.codex/`)・rules・非プラグイン環境 | 対象プロジェクトへ copy/symlink。`--codex` `--rules` `--agents` 等のフラグ選択式 |

`skills/` はプラグインと skills.sh の両方から参照される単一ソースとする。

## リポジトリ構成

```
altairs-agent-dev-kit/
├── .claude-plugin/
│   └── plugin.json                 # プラグインマニフェスト (name: altairs-agent-dev-kit)
├── skills/                         # skills.sh 互換 + プラグイン skills (単一ソース)
│   ├── check-existing/
│   ├── pr-maintainer/              # agent-pr-maintainer の汎用版
│   ├── pr-autoloop/                # agent-pr-autoloop の汎用版
│   ├── github-ops/
│   ├── okf-bundle/
│   ├── skill-creator/
│   ├── lazy-import-refactor/
│   ├── claude-md-progressive-disclosurer/
│   ├── prompt-optimizer/
│   ├── qa-expert/
│   ├── interface-design/
│   ├── sqlalchemy-query-patterns/
│   └── context7-openclaw-research/
├── agents/                         # Claude Code 用 agent 定義 (.md) 10 本
│   ├── investigation.md
│   ├── solutions.md
│   ├── code-formatter.md
│   ├── code-reviewer.md
│   ├── security-reviewer.md
│   ├── test-runner.md
│   ├── build-error-resolver.md
│   ├── db-schema-reviewer.md
│   ├── query-analyzer.md
│   └── library-research.md
├── hooks/
│   ├── hooks.json                  # プラグイン hook 設定
│   ├── scripts/                    # hook 本体 (Python)
│   │   ├── hook_pre_commands.py
│   │   ├── hook_pre_edit_worktree.py
│   │   ├── hook_pre_pr_submodule_check.py
│   │   ├── hook_response_monitor.py
│   │   └── hook_worktree_create.py
│   └── rules/
│       └── *.default.json          # 汎用デフォルトルール
├── rules/                          # 汎用ルール (Markdown) 8 本
│   ├── coding-style.md
│   ├── git-workflow.md
│   ├── testing.md
│   ├── logging.md
│   ├── security.md
│   ├── parallel-execution.md
│   ├── dependency-management.md
│   └── planning-memory.md
├── codex/                          # .codex/ 用テンプレート
│   ├── config.toml.template
│   ├── agents/*.toml               # Codex 用 agent 定義 (agents/*.md と対)
│   └── hooks/                      # Codex 用 hook (Claude 用と共通実装を参照)
├── install.sh
├── README.md
└── docs/
    ├── adoption.md                 # 導入手順 + プロジェクト層 override の書き方
    └── third-party-skills.md       # 推奨サードパーティスキルのインストールリスト
```

## 含めるもの / 含めないもの

### 含める (LoRAIro からの抽出元)

| 種別 | 内容 | 汎用化の要点 |
|---|---|---|
| skills 13 本 | 上記 `skills/` 一覧 | SKILL.md 本文の LoRAIro 固有記述 (プロジェクト名・`local_packages` パス・CI filter 表・ADR 番号) をプレースホルダまたは「プロジェクト層で定義」への参照に置換 |
| rules 8 本 | `.claude/rules/*.md` | 具体パス・具体コマンド・Issue 事例を除去し原則と判断フローを残す。事例は「導入先で追記する」ことを明記 |
| hooks 5 本 | `.claude/hooks/*.py` + rules JSON | 後述「hook の汎用化」 |
| agents 10 本 | `.claude/agents/*.md` / `.codex/agents/*.toml` | 本文中のリポジトリルール参照 (`../../AGENTS.md` 等) を「導入先の AGENTS.md / rules を読む」という相対的な記述に変更 |
| Codex 設定 | `.codex/config.toml` | 共有 venv パス等をテンプレート変数化 (`{{PROJECT_ROOT}}` 等) |

### 含めない

- **`lorairo-*` skills 5 本** (qt-widget, repository-pattern, test-generator, mem, design-capture) — LoRAIro 固有のため LoRAIro に残す。`docs/adoption.md` に「プロジェクト固有スキルの実例」としてリンクを 1 行ずつ記載
- **サードパーティ skills 12 本** (`wshobson/agents`, `vercel-labs/agent-skills` 由来: python-*, sql-optimization-patterns, database-migration, vercel-*, web-design-guidelines, deploy-to-vercel) — ライセンスと更新追従の観点から再配布せず、`docs/third-party-skills.md` に `npx skills add` コマンド一覧として記載
- **LoRAIro の CLAUDE.md 本文・ADR・lessons-learned** — プロジェクト層の資産

## hook の汎用化

現状の hook は `/workspaces/LoRAIro/...` をハードコードしている (例: `hook_pre_commands.py` の `LOG_DIR` / `WORKTREE_ROOT` / `SHARED_UV_ENV_VALUE`)。以下の方式で汎用化する。

1. **プロジェクトルート検出**: `CLAUDE_PROJECT_DIR` 環境変数 → なければ `git rev-parse --show-toplevel` にフォールバック
2. **ルールのマージ読込**: `hooks/rules/*.default.json` (汎用デフォルト) に、導入先の `.claude/hooks/rules/*.json` (project override) が存在すればマージ。uv/venv 前提の worktree ガードのような言語依存ルールは override 側でのみ有効化
3. **汎用デフォルトの範囲**: 言語非依存で安全な最小セットに限定 — git 破壊系コマンドのブロック、PR draft 作成ブロック等
4. **ログ出力先**: `<project root>/.claude/logs/` を導出

## LoRAIro 側の移行 (別フェーズ)

本リポジトリの初版完成後、別 PR 群として実施する。

1. LoRAIro にプラグイン (または install.sh) 経由で本 kit を導入
2. 重複する汎用記述を LoRAIro の rules/skills/hooks から削除
3. LoRAIro 固有値 (venv パス、CI filter 表、submodule 運用等) を `CLAUDE.md` と project override JSON に残す
4. `skills-lock.json` の local 参照を本 kit の GitHub 参照へ切替

## テスト・検証

- **hook**: pytest でユニットテスト (ルート検出・ルールマージ・ブロック判定)。LoRAIro の既存 hook 挙動と同等であることを fixture で確認
- **install.sh**: 一時ディレクトリの空 git repo に対して導入 → 期待ファイル配置を assert する smoke テスト (bash または pytest)
- **skills**: SKILL.md frontmatter の必須フィールド (name / description) を検証する lint スクリプト
- **CI**: GitHub Actions で上記を実行

## 決定事項

| 論点 | 決定 |
|---|---|
| リポジトリ名 | `NEXTAltair/altairs-agent-dev-kit` (ユーザー作成済み) |
| 対象範囲 | skills / rules / hooks / agents / `.codex` / `.agents` 構成 |
| 配布方式 | Claude Code プラグイン + skills.sh + install.sh の 3 経路 |
| 汎用化方針 | 汎用コア + プロジェクト層の 2 層構造 |
| サードパーティ skills | 再配布せずインストールリストとして文書化 |
