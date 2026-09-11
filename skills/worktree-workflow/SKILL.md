---
name: worktree-workflow
description: "Operate Git worktrees under .agents/worktree/ for implementation work: one-time setup (.gitignore, VS Code detection settings), start a worktree with a branch, work inside it with the shared venv, recover when the pre-edit hook blocks a shared-checkout edit, assign worktrees to parallel workers, hand off to PR, and clean up after merge. Use when starting implementation on an Issue/feature, when a hook message says to start from a worktree, or when asked to 「worktree 切って」「ワークツリー作って」「worktree 掃除」「ワークツリー削除」. Do NOT use for: PR polling/repair/merge (pr-maintainer, pr-autoloop) or deciding whether worktree is required (that policy lives in rules/git-workflow.md)."
metadata:
  short-description: ".agents/worktree/ 配下の worktree の初期設定・作成・作業・hook ブロックからの復帰・並列割当・PR 引き継ぎ・掃除の手順。"
  dependencies: "github-ops"
---

# Worktree Workflow

`.agents/worktree/<name>` に置く専用 worktree の **手順** を定める。「いつ worktree が必須か」「例外は何か」という
方針は [rules/git-workflow.md](../../rules/git-workflow.md) が持つので、ここでは繰り返さない。
このスキルは Claude Code と Codex の両方で使う。Claude Code では `--worktree` や isolation 起動時に
kit の WorktreeCreate hook が作成を代行するので、その場合は「作成後の手順」から入る。

## When to Use

- Issue 解決・機能開発・複数ファイル実装に着手するとき (Plan 承認直後、最初の Edit の前)
- 共有 checkout で編集しようとして hook に「worktree から開始してください」と止められたとき
- 並列実装で worker ごとに作業場所を割り当てるとき
- PR が merge され、worktree を片付けるとき
- 「worktree 切って」「ワークツリー作って」「worktree 一覧」「ワークツリー掃除して」と言われたとき

## Layout and Naming

| 項目 | 値 |
|---|---|
| 配置先 | `<project_root>/.agents/worktree/<name>` (上流や兄弟ディレクトリには作らない) |
| `<name>` | ブランチ名の `/` を `-` にしたもの。例: `fix/issue-123` → `fix-issue-123` |
| ブランチ | `fix/issue-<n>`, `feat/issue-<n>`, `refactor/issue-<n>` (git-workflow.md の命名) |
| 起点 | `origin/<default branch>` を fetch した直後の先端 |

`.agents/` は skills の実体 (`.agents/skills/`) と同じ親。エージェントは固定相対パスで、人は VS Code の
Source Control から、どちらもここを見ればよい。

## Phase 0: One-time Setup (per repository)

初回だけ。既に済んでいれば飛ばす。

1. **`.gitignore`**: worktree の中身が共有 checkout の `git status` に出ないようにする。

   ```bash
   grep -qxF '.agents/worktree/' .gitignore 2>/dev/null || printf '.agents/worktree/\n' >> .gitignore
   ```

2. **VS Code 検出設定** (推奨): フォルダ走査の既定深さは 1 段なので `.agents/worktree/<name>` は走査に
   掛からない。worktree 検出 (`git.detectWorktrees`, 1.103 以降は既定有効) が拾うが、念のため
   `.vscode/settings.json` に次を置く。既存キーは上書きしない。

   ```json
   {
     "git.repositoryScanMaxDepth": 2,
     "git.detectWorktrees": true
   }
   ```

   Source Control の Repositories ビューで worktree が並び、multi-repo モードなら差分も横断表示される。

3. **共有 venv の常設** (Python/uv): `.claude/settings.json` の `env` に
   `UV_PROJECT_ENVIRONMENT=<project_root>/.venv` が入っているか確認する。無ければ導入先の
   parallel-execution.md の手順で追加する。これが無いと worktree 内の素の `uv run` が別 venv を作る。

## Phase 1: Start a Worktree

```bash
cd "$(git rev-parse --show-toplevel)"          # 共有 checkout へ
git fetch origin
DEFAULT="$(git symbolic-ref --short refs/remotes/origin/HEAD | sed 's#^origin/##')"
BRANCH="fix/issue-123"
NAME="${BRANCH//\//-}"
git worktree add ".agents/worktree/$NAME" -b "$BRANCH" "origin/$DEFAULT"
cd ".agents/worktree/$NAME"
```

- 既に同名 worktree があれば再利用する (`git worktree list` で確認)。作り直さない。
- **hook が作った worktree** (Claude Code の `--worktree` / isolation) は detached HEAD で渡される。
  中で最初にブランチを切る:

  ```bash
  git switch -c "$BRANCH"
  ```

- submodule があるリポジトリでは source だけ init する (実行環境には触らない):

  ```bash
  git submodule update --init --recursive
  ```

作成直後に `git status` と `git branch --show-current` で「正しい worktree、正しいブランチ」を確認してから
編集に入る。

## Phase 2: Work Inside the Worktree

- **cwd を worktree に固定する**。Bash の各呼び出しは絶対パスで worktree 内を指す。共有 checkout に
  戻って編集しない (hook が保護ディレクトリの編集を deny する)。
- **venv は共有**: worktree ごとに `uv sync` / `uv venv` をしない。`UV_PROJECT_ENVIRONMENT` が常設されて
  いれば素の `uv run pytest` でよい。効いていない shell では明示する:

  ```bash
  UV_PROJECT_ENVIRONMENT="$(git rev-parse --path-format=absolute --git-common-dir | xargs dirname)/.venv" uv run pytest tests/test_x.py
  ```

- **lockfile / venv を書き換える操作** (`uv sync`, `uv lock`, `uv add`) は共有 checkout で直列に行い、
  worktree からは実行しない。詳細は parallel-execution.md。
- **検証は最小単位から**: 触ったモジュールのテストだけ回し、全体は PR 前に一度 (problem-solving.md)。
- commit / push はこの worktree 内で行う。`git push -u origin "$BRANCH"`。

## Phase 3: Recover From a Hook Block

共有 checkout で src/tests を編集しようとして PreToolUse hook に止められた場合:

1. 止められた編集は **まだ適用されていない**。何も失っていない。
2. 共有 checkout に未コミットの手元変更があるなら退避する:

   ```bash
   git stash push -u -m "move to worktree"
   ```

3. Phase 1 で worktree を作る。
4. 退避したものを worktree 側で戻す:

   ```bash
   cd .agents/worktree/$NAME && git stash pop
   ```

5. 以降の編集は worktree で続ける。共有 checkout の作業ツリーが clean に戻ったことを `git status` で確認する。

## Phase 4: Parallel Workers

- worker ごとに別 worktree、別ブランチ。名前は `<type>-issue-<n>-<scope>` のように担当範囲を含める。
- 書き込み範囲 (担当ファイル/モジュール) を割当時に明示し、重なる範囲は 1 worker に寄せる。
- リード側で作って絶対パスを渡すか、isolation 起動で hook に作らせる。どちらでも配置先は同じ。
- 全 worker が同じ共有 venv を使うので、依存追加が要る worker はリードに依頼し、リードが共有 checkout で
  直列に行う。

## Phase 5: Hand Off to PR

worktree 内で実装と検証が終わったら:

```bash
git push -u origin "$BRANCH"
gh pr create --fill --base "$DEFAULT"
```

PR ができたら **pr-maintainer** (方針) と **pr-autoloop** (自走) に引き継ぐ。同じ worktree、同じセッションで
続ける。ここから先の CI 監視・修正・merge 判断はこのスキルの範囲外。

## Phase 6: Clean Up After Merge

merge 直後に行う。放置しない。

```bash
cd "$(git rev-parse --path-format=absolute --git-common-dir | xargs dirname)"   # 共有 checkout へ戻る
git worktree remove ".agents/worktree/$NAME"
git branch -d "$BRANCH"
git fetch --prune
git worktree prune
```

- **cwd が削除対象**のときは先に共有 checkout へ移動する (上の 1 行目)。
- 未コミット変更が残っていて `remove` が拒否されたら、中身を確認してから判断する。捨ててよいと確認できた
  場合だけ `git worktree remove --force`。確認できないなら止めて報告する。
- まとめて掃除するときの対象は `.agents/worktree/` 配下で、未コミット変更が無く、ブランチが merge 済み
  (`git branch --merged "origin/$DEFAULT"` に載る) のものだけ。導入先に cleanup 用 Makefile ターゲット
  があればそれを使う (git-workflow.md のプロジェクト固有欄を参照)。

一覧確認:

```bash
git worktree list --porcelain
```

## Troubleshooting

| 症状 | 対処 |
|---|---|
| `fatal: '<branch>' is already checked out at ...` | そのブランチの worktree が既にある。`git worktree list` で場所を探して再利用 |
| `git worktree add` 後に `.agents/worktree/x` が `git status` に出る | Phase 0 の `.gitignore` が未設定 |
| worktree 内の `uv run` が `.venv` を新規作成し始めた | `UV_PROJECT_ENVIRONMENT` が効いていない。Phase 2 の明示形で実行し、settings の env を直す |
| VS Code に worktree が出ない | Phase 0 の設定を確認。`git.detectWorktreesLimit` (既定 50) 超過も疑う |
| `remove` が `contains modified or untracked files` で失敗 | 中身を確認。必要なら commit/stash、捨ててよければ `--force` |
| worktree ディレクトリを手で消してしまった | `git worktree prune` で登録を消し、ブランチは `git branch -d` |
| hook が worktree 作成に失敗してセッションが起動しない | stderr の `git worktree add 失敗` を読む。多くは同名ディレクトリの残骸。`prune` 後に再実行 |

## Related

- [rules/git-workflow.md](../../rules/git-workflow.md): worktree が必須になる条件、例外、完了の定義
- [rules/parallel-execution.md](../../rules/parallel-execution.md): 共有 venv と並列実行の詳細
- pr-maintainer / pr-autoloop: PR 作成後の保守
- kit hooks: `hook_worktree_create.py` (作成の代行), `hook_pre_edit_worktree.py` (共有 checkout の編集ゲート)
