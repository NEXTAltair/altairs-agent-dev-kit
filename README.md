# altairs-agent-dev-kit

AI エージェント向けの開発標準一式 - skills / rules / hooks / agents - を、プロジェクト固有の値を含まない
汎用コアとして切り出し、任意のリポジトリへ導入・追従できる形で配布する kit。

**対応ハーネスは Claude Code / Codex / Antigravity / OpenClaw**。4 つすべてが読む `AGENTS.md` と、
Claude Code 以外の 3 つが直接読む `.agents/skills/` を共通の土台にし、rules の frontmatter や agent 定義の形式のように
差がある部分だけをハーネス別に生成する。各ハーネスの配置先と対応状況は
[docs/harness-matrix.md](docs/harness-matrix.md) にある。hooks は Claude Code と Codex のみ対応。
OpenClaw 専用の skill / hook / plugin は OpenClaw 自身の SDK で定義するもので、kit には含めない。

部品は `kit.json` で **profile** (core / python / qt / sql) と **推奨 scope** (global / project) に分類してある。
core は言語・スタックに依存しない。python / qt / sql は Python + uv、PySide6/Qt、SQLAlchemy を前提にする
(共有 venv 運用・`uv run` 前提の hook / rules を含む)。他言語向けの profile はまだ無い。

「事故 → 原則 → 機械的強制」というサイクルで育った運用知見 (破壊的コマンドのブロック、
worktree 分離、設定と文書の整合チェックなど) を、新規・既存を問わずどのリポジトリでも
再利用できるようにすることが目的。汎用コア (本リポジトリ) とプロジェクト層 (導入先の
`CLAUDE.md` / `.claude/rules/` / hook override JSON) を分離し、導入先は自分の具体値だけを
上書きすればよい。

## 収録物

| 種別 | 数 | 場所 |
|---|---|---|
| skills | 14 本 | `skills/` (skills.sh 互換構造、プラグインからも参照) |
| rules | 11 本 | `rules/*.md` (コーディング規約・git 運用・テスト・ログ・セキュリティ・ドキュメント保守・問題解決の姿勢等) |
| hooks | 6 本 + 共通基盤 | `hooks/scripts/*.py` (+ `hook_common.py`)、設定は `hooks/rules/*.default.json` |
| agents | 8 本 | `agents/*.md` (Claude Code サブエージェント定義) |
| Codex 設定 | 一式 | `codex/config.toml.template`, `codex/agents/*.toml` (agents は生成物) |
| Antigravity agents | 8 本 | `antigravity/agents/*.md` (`agents/*.md` からの生成物) |
| 部品の分類 | 1本 | `kit.json` (profile・推奨 scope・rule の読み込み方) |
| 導入 CLI | 1本 | `scripts/agent_kit.py` (4 ハーネス、global / project) |
| 設定整合 lint | 1本 | `scripts/check_config_consistency.py` |
| skill lint | 1本 | `scripts/lint_skills.py` |

## クイックスタート

`scripts/agent_kit.py` (Python 3.10 以降、標準ライブラリのみ) で導入する。v0.6.0 より後のリリースタグに含まれる。

```bash
git clone https://github.com/NEXTAltair/altairs-agent-dev-kit.git
cd altairs-agent-dev-kit
git checkout <リリースタグ>

# どのプロジェクトでも使う部品 (core の skills / rules / agents) を自分の環境へ
python3 scripts/agent_kit.py install --scope global

# プロジェクトごとの部品 (スタック依存の rules / agents / skills、worktree 運用) を repository へ
python3 scripts/agent_kit.py install --scope project --target /path/to/your-repo
```

| オプション | 既定 | 内容 |
|---|---|---|
| `--harness` | `auto` | `claude,codex,antigravity,openclaw` から選ぶ。`auto` は PATH 上の CLI と設定ディレクトリから検出 |
| `--profile` | `auto` | `python,qt,sql` を選ぶ (core は常に含む)。`auto` は `pyproject.toml` から検出、`all` は全部 |
| `--components` | `rules,agents,skills` | `hooks` を足すと Claude Code / Codex の hook runtime も導入 (project のみ)。`all` で全部 |
| `--standalone` | off | project scope で global 向けの部品も repository へ入れる (global を導入していない人・CI・クラウド agent 向け) |
| `--dry-run` | off | 書き込まずに予定を表示 |
| `--force` | off | 利用者が変更したファイルと既存 skill も上書き |
| `--skill-source` | checkout 中のタグ | タグの無い開発 checkout から skills を入れるときに kit のローカルパスを指定 |

`status` で導入済みの版と変更・欠落したファイル、`uninstall` で kit が置いて未変更のファイルと `AGENTS.md` の管理区画を
取り除ける。`list` は部品の分類を表示する。skills の導入は skills.sh CLI に委ねるので **Node.js (npx) が必要**
(`--components rules,agents` なら不要)。python profile の rules / hooks は uv を前提にする。

### install.sh (Claude Code + Codex、従来の経路)

```bash
git checkout v0.6.0
./install.sh --target /path/to/your-repo --all
```

**uv がグローバルに導入されていることが前提** (hook の uv ガード、rules の共有 venv 運用が uv を前提とするため)。
uv が PATH に無い場合、install.sh / install_harness.py は Git repository でない場合と同様に、何も書き込まずに
メッセージを出して停止する。[uv の導入手順](https://docs.astral.sh/uv/) に従って導入してから再実行すること。

タグの checkout が必要なのは `--skills` を含む場合で、skills.sh CLI の制約ではなくこの kit のポリシー。
install.sh は checkout 中のタグを `github:owner/repo#<tag>` として `skills-lock.json` に記録するため、
タグのない commit では止まる (ブランチ名を pin すると後で中身が変わり、未公開 commit は他環境で解決できないため)。
開発 checkout を試すときだけ `--skill-source <ローカルパス>` を明示する。hooks / rules / agents のみなら
タグなしでも導入できるが、hooks の runtime lock を後で復元するには同じソースが要るのでタグ checkout を推奨する。

| フラグ | 導入内容 |
|---|---|
| `--skills` | 同梱 skills → `<repo>/.agents/skills/` (実体) + `<repo>/.claude/skills/` (symlink)。skills.sh CLI 経由、**要 Node.js/npx** |
| `--rules` | `rules/*.md` → `<repo>/.claude/rules/` |
| `--agents` | `agents/*.md` → `<repo>/.claude/agents/` |
| `--hooks` | 版固定した runtime → `<repo>/.agent-kit/runtimes/`、起動設定を生成 |
| `--codex` | `.codex/config.toml` + `agents/*.toml` |
| `--all` | 上記すべて |
| `--force` | kit 所有ファイル・skill の意図的な更新。runtime は別版を追加して branch pin を変更 |
| `--skill-source` | skill の導入元を明示。既定は checkout 中の公開 GitHub タグ。ローカルパスは開発時のみ |

`--hooks` はコピー後に `settings.json` へ配線すべき hook 設定を標準出力に表示するだけなので、
表示された JSON を `<repo>/.claude/settings.json` の `hooks` キーへ手動で貼り付けること。

`--hooks` / `--codex` の導入先は Git repository の root が前提 (runtime の版固定と worktree 判定に Git を使う)。
Git repository でない場合や配下ディレクトリを指定した場合、installer は何も書き込まずにメッセージを出して停止する。
先に `git init` を実行してから再実行すること。skills / rules / agents のみの導入に Git は不要。

Windows PowerShell のフック導入には次を利用できる (Python 3.10+ と Git が必要):

```text
python -X utf8 scripts/install_harness.py --target <project-directory> --codex
```

Linux では同じコマンドの `python` を `python3` に置き換える。

branch lock と共通ランタイムを導入し、Codex の `hooks.json` を生成する。
既存設定は `.new` に提案を保存し、プロジェクトの override JSON は変更しない。
既存版から意図的に更新するときだけ `--force` を指定する。Claude 配線は表示された JSON を
既存の設定へマージする。`install.sh --hooks` も同じ処理を利用する。
OS 固有の共有環境パスはローカルの Codex 設定で管理し、Windows とコンテナで共有しない。
詳細は [docs/portable-hooks.md](docs/portable-hooks.md) を参照。

lock と起動設定を Git 管理し、`.agent-kit/runtimes/` と `.agent-kit/.pin-update` は gitignore に
追加する。新規 checkout の復元には固定した kit から `--runtime-only` を使う。
Codex ではプロジェクトと生成フックをレビューし、`/hooks` で信頼を確認する。
導入・更新・復元・失敗時の手順は [runtime 契約](docs/hook-runtime.md) を参照。

その他の導入経路 (Claude Code プラグイン / skills.sh 単体) は
[docs/adoption.md](docs/adoption.md) を参照。

## 導入後の最小 override

kit 同梱の hook デフォルトはほとんどのゲートが無効 (空リスト) になっている。
有効化したいものだけ `<repo>/.claude/hooks/rules/*.json` に override を置く:

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

override の詳しい書き方 (`pre_commands.json` の uv ガード有効化例、`response_monitor.json` の
NG ワード例、rules の追記ポイント、`check_config_consistency.py` の CI 組み込み) は
[docs/adoption.md](docs/adoption.md) を参照。同梱しないサードパーティ skill の推奨インストール
リストは [docs/third-party-skills.md](docs/third-party-skills.md) を参照。

## 設計原則

0. **共通の土台 + ハーネス別の生成**: 原本は 1 つ (`rules/`、`agents/`、`skills/`)。`AGENTS.md` と `.agents/skills/` を全ハーネスの共通項にし、形式の違いは導入時・生成時に吸収する
1. **事故 → 原則 → 機械的強制**: ルールは実際の事故を発端とし、人間やエージェントの注意力ではなく hook で機械的にブロックする
2. **更新頻度で文書層を分ける**: 指針層 / 詳細層 (rules) / 実装層 (hook コード) を分離し、頻度の違う情報を混ぜない
3. **frontmatter = SSoT、索引は生成物**: メタデータは frontmatter に一本化し、索引の手編集を禁止する
4. **コマンド形状を変えず環境で設定する**: CLI の承認摩擦を避けるため、env prefix を毎回付けず設定ファイルに1回常設する
5. **設定と文書の整合を lint する**: 「rules が約束する env/hook 配線が settings に実在するか」を検証するチェックを提供する
6. **unknowns を分類する**: 未確定の前提を inspect / test / ask / assume / defer で扱い、未検証の仮定を成果報告に残す

## ドキュメント

- [docs/harness-matrix.md](docs/harness-matrix.md) - ハーネス別の配置先 (出典つき) と kit の対応・未対応
- [docs/adoption.md](docs/adoption.md) - 導入手順の詳細とプロジェクト層 override の書き方
- [docs/skill-install-runbook.md](docs/skill-install-runbook.md) - skill 導入/更新の runbook (canonical レイアウト・sourceType・github@ref bump・footgun 対策)
- [docs/third-party-skills.md](docs/third-party-skills.md) - 同梱しないサードパーティ skill の推奨インストールリスト
- [docs/superpowers/specs/2026-07-02-altairs-agent-dev-kit-design.md](docs/superpowers/specs/2026-07-02-altairs-agent-dev-kit-design.md) - 設計書 (**構築時の歴史記録**。移植元パス等は当時のまま。現行仕様は adoption.md と ADR を参照)
- [docs/superpowers/plans/2026-07-02-altairs-agent-dev-kit.md](docs/superpowers/plans/2026-07-02-altairs-agent-dev-kit.md) - 実装計画 (**構築時の歴史記録**。完了済み)
