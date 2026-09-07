---
type: Decision
title: "ADR-0009: submodule 内の cwd は所有 checkout に解決し、起動失敗時も単独の cd は拒否しない"
description: submodule を固定する checkout を superproject 経由で辿って hook を継続し、入れ子 repository で runtime 解決に失敗しても単独の cd だけは通してエージェントが自力で脱出できるようにする
timestamp: 2026-09-07
status: Proposed
---
# ADR-0009: submodule 内の cwd は所有 checkout に解決し、起動失敗時も単独の cd は拒否しない

## Context

`hooks/bootstrap.py` は起動プロセスの cwd から `--show-toplevel` で作業 checkout を決め、
`--git-common-dir` で共有 checkout を求める。stale な `CLAUDE_PROJECT_DIR` や payload の `cwd` を
信用しないための設計で、linked worktree ごとに追跡された lock を選ぶ根拠になっている
([ADR-0008](0008-loop-contracts-and-hook-adapters.md)、[runtime 契約](../hook-runtime.md))。

この解決は submodule を想定していなかった。submodule 内では `--show-toplevel` が submodule root、
`--git-common-dir` が `<superproject>/.git/modules/<path>` を返すため、「shared checkout cannot be
determined」として fatal になる。エージェントが submodule を in-place で編集する運用
(consumer が `local_packages/*` を submodule で持つ構成) では、`cd local_packages/<pkg>` を一度
実行しただけで PreToolUse (Bash / Edit / Write) が全て deny、Stop も block になり、
cwd を戻す `cd` 自体も deny されるため、エージェント側に復旧手段が無くなる。
同じことは tree 内に gitignore して置いた無関係な checkout (kit 自身の開発 checkout 等) に
cd した場合にも起きる。こちらは lock を持たないので「lock が無い」として失敗する。

## Decision

- **submodule は、それを固定する checkout の一部として扱う。** 作業 checkout に lock が無ければ
  `--show-superproject-working-tree` を辿り、lock を持つ checkout に着いた時点で停止する。
  linked worktree 内で初期化した submodule はその worktree に属する。
- **辿るのは Git が宣言する所有関係だけ。** ファイルシステムの親ディレクトリ探索や
  `CLAUDE_PROJECT_DIR` への fallback は行わない。tree 内に入れ子になった無関係な repository は
  引き続き非対応として診断し、上位ディレクトリの policy を借用しない。
- **起動失敗時の PreToolUse は、引数なし・単一パス引数の `cd` (`Set-Location` を含む) だけ
  deny しない。** stdout を空にして通常の permission flow に渡す。連結・置換を含む command は deny のまま。
  Stop / WorktreeCreate 等の失敗契約は変更しない。
- 診断文は、lock が見つからない作業 checkout のパスと「単独の `cd` で脱出できる」旨を含める。

## Rationale

submodule 内の cwd を fatal にする理由は無い。submodule は superproject の tree に固定された
成果物で、どの checkout に属するかは Git が一意に答えられる。superproject を辿る解決は
「cwd が checkout を決める」原則を保ったまま、所有関係を正しく写すだけである。
一方で無関係な入れ子 repository には所有者が居ないため、推測で親の policy を適用すると
別プロジェクトの rule で別プロジェクトの操作を判定することになり、fail-closed の意味が無くなる。

単独の `cd` は policy が判定すべき処理を何も実行しない。これを deny すると、cwd が原因の失敗から
エージェントが抜け出す唯一の手段が失われ、人間がターミナルで `cd` するまでセッションが止まる。
fail-closed は「未検証の操作を通さない」ための性質であり、「何も実行しない操作まで止める」ことは
目的に含まれない。

## Consequences

- consumer は submodule 内を作業ディレクトリにしても hook 保護を失わない。override は
  所有 checkout の `.claude/hooks/rules/*.json` が使われる。
- 入れ子の無関係 repository に入った場合は依然として deny されるが、診断に従って `cd` で戻れる。
- `tests/test_portable_install.py` が submodule (main / linked worktree) と入れ子 repository の
  両ケースを実起動で固定する。
- bootstrap は registration に埋め込まれるため、consumer は kit の pin 更新と登録の再生成
  (`--refresh-wiring` 相当) を行って初めてこの挙動を得る。runtime だけの復元では変わらない。
