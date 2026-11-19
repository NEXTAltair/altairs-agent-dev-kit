# altairs-agent-dev-kit

AI エージェント向けの開発標準 (skills / rules / hooks / agents) を、プロジェクト固有値を含まない汎用コアとして配布する kit。
「事故 → 原則 → 機械的強制」の運用知見を、任意のリポジトリへ導入・追従できる。

## 対応ハーネスと構成

| ハーネス | rules | agents | skills | hooks |
|---|:---:|:---:|:---:|:---:|
| Claude Code | ✅ | ✅ | ✅ | ✅ |
| Codex CLI | ✅ (`AGENTS.md` 索引) | ✅ | ✅ | ✅ |
| Antigravity | ✅ | ✅ | ✅ | — |
| OpenClaw | ✅ (`AGENTS.md` 索引) | — | ✅ | — |

- `AGENTS.md` と `.agents/skills/` を共通の土台とし、形式差は導入 CLI (`scripts/agent_kit.py`) が自動吸収する。配置先の詳細は [docs/harness-matrix.md](docs/harness-matrix.md) を参照。
- 部品は `kit.json` で **profile** (`core` / `python` / `typescript` / `qt` / `sql`) と **scope** (`global` / `project`) に分類されている。`core` は言語非依存。

## クイックスタート

**前提**: Python 3.10+ (標準ライブラリのみで動作)。skills も導入する場合は Node.js (`npx`)、hooks 導入は Git、`python` profile の rules / hooks は [uv](https://docs.astral.sh/uv/) を前提とする。

### 1. kit を取得する (最新リリースタグ)

**Windows (PowerShell)**:

```powershell
git clone --branch v0.7.0 --depth 1 https://github.com/NEXTAltair/altairs-agent-dev-kit.git
cd altairs-agent-dev-kit
```

**macOS / Linux**:

```bash
git clone --branch v0.7.0 --depth 1 https://github.com/NEXTAltair/altairs-agent-dev-kit.git
cd altairs-agent-dev-kit
```

### 2. 導入する

まずは共通部品 (`global`) を自分の環境へ入れ、続いてプロジェクト固有の部品 (`project`) を対象リポジトリへ入れる。

**Windows (PowerShell)**:

```powershell
# 共通部品 (全プロジェクト共通の rules / agents / skills) を自分の環境へ
python scripts/agent_kit.py install --scope global

# プロジェクト部品 (スタック依存の rules / agents / skills) をリポジトリへ
python scripts/agent_kit.py install --scope project --target C:\path\to\your-repo

# hooks (Claude Code / Codex) もまとめて入れる場合
python scripts/agent_kit.py install --scope project --target C:\path\to\your-repo --components all
```

**macOS / Linux**:

```bash
python3 scripts/agent_kit.py install --scope global
python3 scripts/agent_kit.py install --scope project --target /path/to/your-repo

# hooks (Claude Code / Codex) もまとめて入れる場合
python3 scripts/agent_kit.py install --scope project --target /path/to/your-repo --components all
```

> **Windows での補足**:
> - `install.sh` (Bash) や `-X utf8` は不要。`python scripts/agent_kit.py` がそのまま PowerShell で動く。
> - symlink 作成権限が無い環境でも、skills は自動的にコピーへフォールバックする。

### 3. hooks を導入した場合の仕上げ

- **Claude Code**: 標準出力に表示された JSON を `<repo>/.claude/settings.json` の `hooks` キーへマージする。
- **Codex**: `<repo>/.codex/hooks.json` が自動生成される。起動後に `/hooks` で内容を確認・信頼する。
- **`.gitignore`**: `.agent-kit/runtimes/` と `.agent-kit/.pin-update` を追加し、`.agent-kit/hooks.lock.json` は Git 管理する。

### よく使うオプション・サブコマンド

| オプション | 既定 | 内容 |
|---|---|---|
| `--harness` | `auto` | `claude,codex,antigravity,openclaw` を指定 (`auto` は環境から自動検出) |
| `--profile` | `auto` | `python,typescript,qt,sql` を指定 (`auto` は `pyproject.toml` / `package.json` から自動検出、`all` で全部) |
| `--components` | `rules,agents,skills` | 導入対象を選択 (`hooks` 追加、`all` で全部) |
| `--standalone` | off | `global` 向けの部品も対象リポジトリへ同梱する (CI / クラウド agent / global 未導入環境向け) |
| `--dry-run` | off | 書き込まずに予定だけ表示 |
| `--force` | off | 利用者が変更したファイルや既存 skill も上書き更新 |
| `--skill-source` | checkout 中のタグ | タグの無い開発 checkout から skills を入れるときに kit のローカルパスを指定 |

```bash
# 部品の一覧と分類を確認
python scripts/agent_kit.py list

# 導入状態・変更・欠落を確認
python scripts/agent_kit.py status --scope project --target /path/to/your-repo

# kit が置いた未変更ファイルと AGENTS.md 管理区画を削除
python scripts/agent_kit.py uninstall --scope project --target /path/to/your-repo
```

その他の導入経路 (Claude Code プラグイン、`npx skills add` 単体導入、従来の `install.sh` / `install_harness.py`) は [docs/adoption.md](docs/adoption.md) を参照。

## 収録物

具体的な一覧と分類は `python scripts/agent_kit.py list` または [kit.json](kit.json) を参照。

| 種別 | 場所 | 概要 |
|---|---|---|
| skills | `skills/` | 開発フロー・レビュー・文書保守などの skill 群 (`skills.sh` 互換) |
| rules | `rules/` | コーディング規約・git 運用・テスト・セキュリティ・問題解決などの汎用原則 |
| hooks | `hooks/` | 破壊的コマンド・worktree 外編集・応答品質を検査する共通 hook runtime とデフォルト設定 |
| agents | `agents/` | サブエージェント定義原本 (`codex/agents/`・`antigravity/agents/` はここから自動生成) |
| CLI / lint | `scripts/` | `agent_kit.py` (導入 CLI)、`check_config_consistency.py` (設定整合 lint)、`lint_skills.py` (skill lint) |

## 導入後の最小設定 (hook override)

kit 同梱の hook デフォルトは安全最小セット (多くのゲートが無効) になっている。有効化したい項目だけ `<repo>/.claude/hooks/rules/*.json` に override を置く:

`.claude/hooks/rules/consistency.json`:

```json
{
  "required_env": ["UV_PROJECT_ENVIRONMENT"]
}
```

`.claude/hooks/rules/response_monitor.json`:

```json
{
  "ng_words": [
    {"keyword": "重要なのは", "message": "予告・総括の定型。中身を直接書け"}
  ]
}
```

override の詳細 (`pre_commands.json` の uv ガード有効化、保護ディレクトリ追加、CI での設定整合チェック) は [docs/adoption.md](docs/adoption.md) を参照。

## 設計原則

0. **共通の土台 + ハーネス別の生成**: 原本は 1 つ (`rules/`、`agents/`、`skills/`)。`AGENTS.md` と `.agents/skills/` を共通項にし、形式差は導入時・生成時に吸収する
1. **事故 → 原則 → 機械的強制**: ルールは実際の事故を発端とし、注意力ではなく hook で機械的にブロックする
2. **更新頻度で文書層を分ける**: 指針層 / 詳細層 (`rules/`) / 実装層 (hook コード) を分離し、頻度の違う情報を混ぜない
3. **frontmatter = SSoT、索引は生成物**: メタデータは frontmatter に一本化し、索引の手編集を禁止する
4. **コマンド形状を変えず環境で設定する**: CLI 承認摩擦を避けるため、env prefix を毎回付けず設定ファイルに常設する
5. **設定と文書の整合を lint する**: rules が前提とする env / hook 配線が実在するかを検査する
6. **unknowns を分類する**: 未確定の前提を inspect / test / ask / assume / defer で扱い、未検証の仮定を成果報告に残す

## ドキュメント

- [docs/adoption.md](docs/adoption.md) — 導入ガイド (Windows / macOS / Linux 手順、hook override、CI 組み込み、その他の導入経路)
- [docs/harness-matrix.md](docs/harness-matrix.md) — ハーネス別の配置先 (出典つき) と対応状況
- [docs/hook-runtime.md](docs/hook-runtime.md) — hook runtime の固定・復元・失敗時の契約
- [docs/portable-hooks.md](docs/portable-hooks.md) — hook 配布モデルと Claude / Codex 向け配線
- [docs/skill-install-runbook.md](docs/skill-install-runbook.md) — skill 導入・更新 runbook と footgun 対策
- [docs/third-party-skills.md](docs/third-party-skills.md) — 同梱しないサードパーティ skill の推奨リスト
- [docs/index.md](docs/index.md) — 全ドキュメント・ADR・歴史記録の索引 (自動生成)
