---
type: Decision
title: "ADR-0009: submodule の中にいても hook を動かし、動かせない場所からは cd で戻れるようにする"
description: submodule に cd しただけで全ツールが拒否され、戻る cd まで拒否されて詰む問題への対処。submodule は親 checkout の一部として扱い、hook が起動できない場所でも「引数 1 つの cd」だけは通す
timestamp: 2026-09-07
status: Accepted
---
# ADR-0009: submodule の中にいても hook を動かし、動かせない場所からは cd で戻れるようにする

## 何が起きたか

エージェントが Bash ツールで `cd local_packages/<pkg>` (submodule) を 1 回実行した。
それ以降、セッションの作業ディレクトリがそこに固定され、次の状態になった。

- Bash / Edit / Write のすべてが hook に拒否される
- 応答を終えようとしても Stop hook に差し戻される
- 元の場所に戻るための `cd /workspaces/<project>` も拒否される
- 人間がターミナルで `cd` するまで、エージェントには何もできない

同じことは、プロジェクト内に gitignore して置いた別の Git checkout
(kit 自身の開発 checkout など) に `cd` した場合にも起きる。

## なぜ起きたか

hook の起動コード (`hooks/bootstrap.py`) は「今どの checkout で動いているか」を
作業ディレクトリから Git に聞いて決める。環境変数 `CLAUDE_PROJECT_DIR` は古い値が
残ることがあるので信用しない、という設計である ([runtime 契約](../hook-runtime.md))。

この判定は submodule を想定していなかった。

| 場所 | `git rev-parse --show-toplevel` | `--git-common-dir` | 結果 |
|---|---|---|---|
| プロジェクト直下 | `<project>` | `<project>/.git` | 正常 |
| linked worktree | `<worktree>` | `<project>/.git` | 正常 (worktree 自身の lock を使う) |
| submodule の中 | `<project>/local_packages/<pkg>` | `<project>/.git/modules/...` | **「非対応の Git 配置」として失敗** |
| 無関係な入れ子 checkout | `<project>/vendored` | `<project>/vendored/.git` | lock が無いので失敗 |

失敗すると fail-closed (何も通さない) になる。ここに `cd` も含まれていたため、
失敗の原因である「作業ディレクトリ」を直す手段そのものが失われた。

## どうするか

### 1. submodule は「それを固定している checkout の一部」として扱う

`git rev-parse --show-superproject-working-tree` で親 (superproject) を最外まで辿り、
そこを作業 checkout として lock (`.agent-kit/hooks.lock.json`) を探す。

- `<project>/local_packages/<pkg>` にいる → `<project>` として hook が動く
- linked worktree の中で `submodule update --init` した submodule にいる → その worktree として動く
- submodule 自身が (単独で kit を使うために) lock を持っていても無視する。どの rule で判定するかは
  submodule を固定している側が決める
- 辿るのは **Git が submodule として登録している親だけ**。ファイルシステム上の親ディレクトリや
  `CLAUDE_PROJECT_DIR` は見ない。無関係な入れ子 checkout は今までどおり失敗する
  (別プロジェクトの rule で判定してしまうのを避けるため)

### 2. hook が起動できない場所でも「引数 1 つの `cd`」だけは通す

起動失敗時の PreToolUse は、次の形の command だけ拒否せず通常の permission flow に渡す。

- `cd` / `cd <パス>` / `cd "<パス>"`。Bash は builtin の `cd` のみ。PowerShell は `cd` と
  `Set-Location` を大文字小文字を区別せずに認める (それ以外の名前は任意の実行ファイルや関数になり得る)
- Codex の payload (`tool_name` 無し、command は `tool_input.cmd`) は host の shell の規則で判定する
- `&&` `;` `|` での連結、`$(...)` やバッククオートの置換を含むものは今までどおり拒否

`cd` 単独は何も実行しないので、policy で判定すべきものが無い。そして cwd が原因の失敗から
エージェント自身が抜け出す唯一の手段である。Stop や WorktreeCreate の失敗時の挙動は変えない。

### 3. 診断文に「どの checkout に lock が無かったか」と「`cd` で戻れる」ことを書く

## この変更で何が変わるか

- submodule の中を作業ディレクトリにしても hook の保護は効いたまま。override は親 checkout の
  `.claude/hooks/rules/*.json` が使われる
- 無関係な入れ子 checkout に入った場合は依然として拒否されるが、診断のとおり `cd` で戻れる
- consumer 側は、**kit の pin 更新と登録の再生成 (`--refresh-wiring` 相当) を行って初めて**
  この挙動になる。起動コードは `.claude/settings.json` に埋め込まれているため、
  runtime を復元し直すだけでは変わらない
- `tests/test_portable_install.py` が submodule (main / linked worktree) と入れ子 checkout の
  両方を実起動で固定する
