---
type: Guide
title: Hook runtime の固定・復元契約
description: 作業 checkout の lock と override、共有 runtime、起動・復元失敗の扱い
timestamp: 2026-09-05
---
# Hook runtime の固定・復元契約

kit は起動入口・実装・defaults を所有し、consumer は固定版・登録設定・固有フックと
override を所有する。固有フックのために `hook_common` や runtime 探索を再実装しない。

## 配置と起動

- 作業 checkout: Git の `--show-toplevel`。ここにある `.agent-kit/hooks.lock.json` と
  `.claude/hooks/rules/*.json` を使う。サブディレクトリ起動でも同じ。親 checkout の lock へ fallback しない。
- 共有 checkout: `--git-common-dir` が指す `.git` の親。共有資源と共有 checkout の編集保護対象を計算する。
  bare repository / separate-git-dir は非対応で、診断して拒否する。
- runtime: `.agent-kit/runtimes/<SHA-256>/`。作業 checkout、共有 checkout の順に
  lock の全実装・共通モジュール・defaults の内容を検証する。plugin 経路は plugin ソースを先に検証する。
  rules だけのディレクトリや旧 adapter の存在では runtime と判定しない。

lock は相対パスごとの SHA-256 と、それらをソートした manifest の SHA-256 を保持する。
同じ Git commit の配布ファイルは `.gitattributes` により Windows/Linux とも LF に固定される。
共有先に別版を追加しても既存ブランチは旧版を使い続ける。lock と起動設定は Git 管理し、
`.agent-kit/runtimes/`、`.agent-kit/.pin-update` は consumer の gitignore に追加する。

インストール型の登録コマンドは kit 所有の `hooks/bootstrap.py` を圧縮して埋め込み、
Python 標準ライブラリだけで探索する。`python -I` で cwd/PYTHONPATH による標準モジュールの
取り違えを防ぐ。起動時のネットワーク取得・依存インストールはしない。
consumer hook は以下で作ったコードを `python -I -X utf8 -c <code>` に渡して登録する:

```python
from install_harness import hook_bootstrap  # 固定 kit の scripts を installer 側で import
code = hook_bootstrap('.claude/hooks/teammate.py', event='TeammateIdle', consumer=True)
```

固有スクリプトは作業 checkout に追跡する。起動入口が対応する `hook_common` を提供し、
stdin は消費せずそのまま固有スクリプトへ渡す。runtime 内の bytecode は生成せず、
`hook_common` は検証したソースから読み込む。consumer 自身の依存は consumer が管理する。

## 導入・更新・復元

固定した kit checkout から実行する (Windows は `python`、Linux は `python3`):

```bash
python scripts/install_harness.py --target /path/to/consumer --codex
python scripts/install_harness.py --target /path/to/consumer --runtime-only
```

最初のコマンドは Claude 設定を表示し、Codex 設定を生成する。既存設定は `.new` へ提案し、
固有 override と旧ファイルは保持する。表示された起動設定へ移行し、lock とともにコミットする。
旧 `.claude/hooks/hook_*.py` / `.codex/hooks/hook_*.py` を直接登録する形式は移行対象。
plugin も事前に `--runtime-only` で lock を作る。plugin 自動更新だけでは branch pin は変更しない。

`--runtime-only` は登録設定を書き換えない。既存 lock とソースが違えば停止する。
意図的な版更新には固定ソースを切り替えて `--force` を指定し、lock の差分をレビューする。
起動コードの更新を含む場合は通常導入で設定も再生成する。`--force` は既存 runtime の上書きを許可しない。

復元は同じファイルシステム内の一時ディレクトリへコピーし、一式の検証後に rename で公開する。
その後 lock を一時ファイルから atomic replace する。途中失敗で旧 lock/旧 runtime は保持される。
共有先への同時復元は同一内容を検証して合流する。単一 checkout の pin 更新競合は
`.pin-update` によって拒否する。OS の電源断に対する永続化保証までは提供しない。

既存 runtime の破損時は自動上書きしない。hook セッションと installer を停止してから、
診断に出た `.agent-kit/runtimes/<ID>` を同じ親の `<ID>.corrupt` などへ移動し、
**そのブランチが固定する kit ソース**から `--runtime-only` で再作成する。
復旧を確認するまで退避コピーを保持する。プロセス強制終了で `.pin-update` が残った場合も、
installer が動いていないことを確認して空のディレクトリを削除してから再実行する。

## 失敗の契約

runtime 欠損・版不一致・不正 lock・Git root 検出失敗は stderr に `agent-kit runtime unavailable`
と復元案内を出す。PreToolUse は stdout の `hookSpecificOutput.permissionDecision=deny`、
Stop は `decision=block` (ともに exit 0 の構造化拒否) を返す。
WorktreeCreate / TeammateIdle などは exit 2 で失敗する。正常な検査成功として扱わない。
固有 hook 本体の出力契約は consumer の責務。

Windows/Linux の CI は `test_portable_install.py` と `test_hook_portability.py` を実行する。
テストは各 OS 上で Git repository と linked worktree を新規作成し、登録コマンドを実起動する。
Windows の Git メタデータを Linux へ mount しただけの検証とは区別する。
