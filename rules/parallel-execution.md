# Parallel Execution Rules

複数のパッケージマネージャ操作 (例: `uv`) を並列に走らせた際の共有仮想環境 (venv) 破損事故を再発させないための運用ルール。プロジェクトルートの venv を共有するすべての操作に適用する。venv / 実行環境の分離粒度 (worktree 間・package 間でどこまで環境を共有し、どこから分離するか) の判断はこのファイルに集約する。他のルール文書 (`git-workflow.md`, `testing.md` 等) からはこのファイルを参照するだけにとどめる。

> **プロジェクト固有:** 実際のプロジェクトルート venv のパス、パッケージマネージャ、CI で使う env 変数名は導入先で追記する。以下は `uv` (Python) を例にした記法。

## 核心ルール

**並列で `uv` を走らせる場合は同一 venv への同期系操作を競合させない。** worktree 内で実行する通常のコマンドは共有 venv の場所を明示して使う。`uv sync` / `uv lock` などの書き換え系は直列化し、`uv run --active` は使わない。

## Hook で自動ブロックされる操作

kit の PreToolUse hook (`hook_pre_commands.py`) は、導入先が `worktree_uv_guard: true` を override で有効化すると、`.agents/worktree/` 配下での `uv` 実行が共有 venv の明示 (`UV_PROJECT_ENVIRONMENT=<project root>/.venv`) を伴わない場合にブロックする。デフォルトルールは `hooks/rules/pre_commands.default.json`、導入先 override は `<project_root>/.claude/hooks/rules/pre_commands.json` に置く。

```bash
# 禁止例 (worktree_uv_guard 有効時に hook がブロック)
uv run --active pytest
uv run --active python script.py

# 正しい
UV_PROJECT_ENVIRONMENT=<project root>/.venv uv run pytest
```

`--active` が必要な特殊ケースでも、venv を直接 activate 済みなら `.venv/bin/<command>` を直接呼ぶことで hook ブロックを回避できる。

## 4 つのルール

### 1. 並列で実行する場合は worktree 分離

並列タスクごとに独立した worktree を切る (配置先は `.agents/worktree/` 配下、詳細は `git-workflow.md` 参照)。ただし通常は worktree ごとの venv を作らず、共有実行環境を明示する。

```bash
# 正しい: 並列ジョブごとに worktree
git worktree add .agents/worktree/job-a -b feat/job-a
git worktree add .agents/worktree/job-b -b feat/job-b
# それぞれの worktree 内で共有 venv を明示して実行
UV_PROJECT_ENVIRONMENT=<project root>/.venv uv run pytest

# 禁止: 同一 venv を並列で叩く
uv run pytest tests/unit/ &
uv run pytest tests/integration/ &
wait
```

### 2. `--active` 相当のフラグは原則使わない

`--active` は現在 activate 中の venv を尊重するが、マニフェストの制約と不一致な場合に **venv 再作成のトリガー** になり得る。前述の hook で自動ブロックできる。

```bash
# 禁止
uv run --active pytest

# 正しい: パッケージマネージャが管理する venv (自動同期、並列セーフ)
uv run pytest
```

### 3. 同期系操作 (`sync` / `lock`) は直列実行

`uv sync` / `uv lock` 相当のコマンドは venv および lockfile を書き換えるため、並列実行で競合する。複数タスクの同時実行でも逐次に並べる。

```bash
# 禁止
uv sync &
uv sync --dev &
wait

# 正しい
uv sync && uv sync --dev
```

### 4. 言語ランタイムのバージョンは固定ファイルで管理

`.python-version` (Python の場合) 等、ランタイムバージョン固定ファイルを使い、手動 activate するシェルでもバージョン一致を確認する。

```bash
# 確認
cat .python-version
python --version
.venv/bin/python --version
```

固定バージョンを変更する場合は影響範囲が広いため PR レビュー必須。

## venv 分離粒度: worktree 間

- 原則としてワークツリー内に専用 venv を作らない (共有のプロジェクトルート venv を使う)
- worktree 配下で実行する場合は、共有実行環境のパスを明示する
- **共有 venv パスの指定はツール側の環境設定で常設し、コマンドには毎回 env prefix を付けない**のが標準運用
  - Claude Code 系ツール: 設定ファイル (例: `.claude/settings.json`) の `env` に `UV_PROJECT_ENVIRONMENT` を設定しておけば、worktree からでも素の `uv run ...` で共有 venv を使える
  - Codex 系ツール: 設定ファイル (例: `.codex/config.toml`) の shell 環境変数設定に同様の値を設定する
- その環境設定が効かない shell (手動端末など) では `UV_PROJECT_ENVIRONMENT=<project root>/.venv uv ...` を明示する
- read-only 検証で対象 checkout を固定したい場合は、`--no-sync` 相当のオプションと `PYTHONPATH` 明示を併用する
- `uv` 単体の help/inspection は venv を作らないため例外として許可する
- worktree 固有の venv が必要な特殊事情がある場合は、理由を明示してから実行する

| | 共有 venv 常設方法 | コマンド記法 |
|---|---|---|
| Claude Code 系 | 設定ファイルの `env` | `uv run ...` (env prefix 不要) |
| Codex 系 | 設定ファイルの shell 環境変数設定 | `uv run ...` (env prefix 不要) |

どちらも常設設定が効かない shell では `UV_PROJECT_ENVIRONMENT=<project root>/.venv uv ...` を明示する。

## venv 分離粒度: package (サブモジュール) 間

複数の独立した package (submodule / monorepo の sub-package 等、それぞれ独自の `pyproject.toml` を持つもの) を扱う場合:

- 各 package のテストはそれぞれ独立した pytest セッションとして実行するのが基本 (単一 invocation に混ぜない)
- ただし package ごとに専用 venv を作ると、重い依存 (機械学習ライブラリ等) の重複ダウンロードや低速な I/O 環境 (ネットワークマウント等) 上での venv 作成で実用速度を損なうことがある
- 対策: プロジェクトルートの共有 venv (dev dependency group にまとめておく) を `UV_PROJECT_ENVIRONMENT` で指し示し、package root から `--no-sync` 相当で実行することで、package 固有の venv 作成を避けられる

```bash
# 例: package root から共有 venv を使ってテストする
cd <package root>
UV_PROJECT_ENVIRONMENT=<project root>/.venv uv run --no-sync pytest
```

> **プロジェクト固有:** 実際の package 一覧、依存グループへの統合方針、I/O 制約のあるマウント構成 (devcontainer のネットワークマウント等) は導入先で追記する。

## 復旧手順

### 兆候

以下のエラーが出たら venv 破損を疑う:

```
failed to remove directory '.venv/lib': Directory not empty
failed to rename file from .../*.tmp* to ...: No such file or directory (os error 2)
Removed virtual environment at: <project root>/.venv
Creating virtual environment at: <project root>/.venv
```

### 復旧コマンド

```bash
rm -rf .venv
uv sync --dev
```

注意点:
- 重い依存の再ダウンロードが発生する場合がある (数分〜十数分)
- worktree 内の venv が壊れた場合は当該 worktree 内で同様に実行
- 復旧中は他のパッケージマネージャコマンドを走らせない

> **プロジェクト固有:** 復旧を1コマンド化する Makefile ターゲット等があれば、ここに追記する。

## 判断フロー

並列タスクをディスパッチする前のチェックリスト:

1. このタスクはパッケージマネージャを内部で呼び出すか? → No なら気にしなくて良い
2. 並列で走らせる別タスクも同じツールを呼ぶか? → No なら気にしなくて良い
3. 同じ venv を共有しているか? → No (worktree 分離済み) なら OK
4. 上記 3 すべて Yes → **直列に並べ替える、または worktree を切る**
