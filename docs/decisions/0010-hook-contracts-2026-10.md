---
type: Decision
title: "ADR-0010: Claude Code 2.1.290 / Codex 0.160.1 の hook 契約に追従する"
description: WorktreeCreate の payload 名、WorktreeRemove の追加、NotebookEdit と Codex apply_patch の編集ゲート漏れを、実バイナリ・ソース・公式ドキュメントで確認して修正し、古い branch pin を壊さない runtime ファイル追加の規則を定めた
timestamp: 2026-10-06
status: Accepted
---
# ADR-0010: Claude Code 2.1.290 / Codex 0.160.1 の hook 契約に追従する

## 何を確認したか

hook の外部契約を、記憶や過去の ADR ではなく次の一次情報で照合した (2026-10-06 時点)。

- Claude Code 2.1.290: 実行バイナリに埋め込まれた hook 入出力スキーマと worktree 処理、
  [hooks リファレンス](https://code.claude.com/docs/en/hooks)、`claude plugin validate`
- Codex 0.160.1: npm 配布バイナリに埋め込まれた JSON schema、openai/codex の `codex-rs` ソース
  (`core/src/tools/hook_names.rs`, `core/src/tools/handlers/apply_patch.rs`, `apply-patch/src/parser.rs`)、
  [Codex hooks](https://learn.chatgpt.com/docs/hooks)

## 何が古くなっていたか

| 項目 | kit の前提 | 現行の契約 | 影響 |
|---|---|---|---|
| Claude WorktreeCreate の入力 | `worktree_name` / `worktree_path` / `source_ref` (ADR-0005) | `name` のみ (例: `bold-oak-a3f2`) | `name` へのフォールバックで動いていたが、文書とテストが誤り |
| Claude WorktreeRemove | 無し | WorktreeCreate を登録すると、hook が作った worktree の削除は WorktreeRemove に委ねられる | 未登録のため isolation worktree が `kept hook-based worktree` として残り続ける |
| Claude の編集ツール | `Edit|Write|MultiEdit` | `NotebookEdit` (`tool_input.notebook_path`) がある。`MultiEdit` は現行版に無い | `.ipynb` の編集が共有 checkout の編集ゲートを素通り |
| Codex のシェル payload | `tool_name` 無し、`tool_input.cmd` | 全 OS で `tool_name: "Bash"`、`tool_input.command` (文字列) | 既存コードは `command` を先に読むので動作していた。文書のみ誤り |
| Codex のファイル編集 | hook 対象外 | `apply_patch` も PreToolUse が発火 (`tool_input.command` にパッチ本文) | 編集ゲートが未登録で、Codex は共有 checkout の `src/` を直接編集できた |
| Codex hooks の有効化 | 記載なし | GA、既定で有効 (`[features] hooks`)。project hooks は trusted project のみ | 文書化のみ |

変わっていなかったもの: PreToolUse の `hookSpecificOutput.permissionDecision=deny` + exit 0、Stop の
`decision=block` と `stop_hook_active` / `last_assistant_message`、exec 形式 (`command` + `args`)、
plugin の `${CLAUDE_PLUGIN_ROOT}` / `${user_config.*}`、Codex の `commandWindows` と秒単位の `timeout`。

## どうしたか

1. **WorktreeCreate** は `name` を正とし、旧 `worktree_name` / `source_ref` にフォールバックを残す。
2. **WorktreeRemove** (`hook_worktree_remove.py`) を Claude の登録 (plugin・インストール型の両方) に追加する。
   削除は安全側に限定する:
   - `<共有 checkout>/.agents/worktree/` の直下で、同じ repository に登録された linked worktree だけ
   - worktree の HEAD が、worktree を消しても残る ref (ブランチ・リモート追跡・タグ等) から到達できるときだけ。
     WorktreeCreate は detached HEAD で作るので、ブランチを切らずに commit した worktree は clean でも残す
     (`git worktree remove` はこの commit の消失を止めない)
   - 未追跡・変更済みのファイルが無いときだけ。`git status --untracked-files=normal` で hook 自身が確かめる
     (`status.showUntrackedFiles=no` の repository では `git worktree remove` が未追跡ファイルを見逃して消すため)。
     `assume-unchanged` / `skip-worktree` の付いた tracked ファイルがある worktree も、変更が Git の確認に出ないので残す
   - ignore 対象のファイルが、作り直せる Python のキャッシュ (`__pycache__` / `.pytest_cache` / `.mypy_cache` /
     `.ruff_cache` / `.hypothesis`、`*.pyc` / `*.pyo`、`.coverage*`) と kit の hook ログ (`.claude/logs/` / `.codex/logs/`)
     だけのときだけ。`git worktree remove` は `--force` なしでも ignore 対象 (.env、ローカル DB、実験の出力等) を
     確認なしで消す。ignore 対象のディレクトリは中を走査し、作り直せないファイルが 1 つでもあれば残す
   - プロセス起動から登録 timeout (60 秒) − 余裕 5 秒の締め切りまでに確認と削除を終えられるときだけ。
     残りが 10 秒未満なら削除を始めない (途中で打ち切られた削除で worktree が半端に残るのを避ける)
   - hook 自身の cwd を共有 checkout へ移してから (Windows は cwd にあるディレクトリを削除できない)、
     `git worktree remove` を `--force` なしで実行する。ディレクトリが既に無い登録は Git が登録だけを消す。未コミット・未追跡ファイル、lock、init 済み submodule
     (WorktreeCreate が init する) を含む worktree は Git が拒否し、hook は非ゼロで終わって worktree は残る。
     submodule 側の未 push commit を巻き込んで消さないため、ここで `--force` は使わない
3. **編集ゲート**は `notebook_path` と Codex の `apply_patch` を読む。パッチの `*** Add File:` /
   `*** Update File:` / `*** Delete File:` / `*** Move to:` 行を payload の `cwd` 基準で解決する。見出しの判定は
   Codex のパーサに合わせ、Update File の hunk 内では末尾空白だけを除く (行頭が空白の行は context 行で、見出しではない)。Claude の matcher は `Edit|Write|MultiEdit|NotebookEdit`
   (古いクライアント向けに `MultiEdit` を残す)、Codex には `apply_patch` の group を追加する。
4. **起動失敗時の `cd` 例外** (ADR-0009) は Codex でも `tool_name` が `Bash` (または旧版の無し) のときだけ適用する。
5. **整合 lint** は、固定した runtime が `hook_worktree_remove.py` を含む場合だけ `WorktreeRemove` を必須にする。
6. **timeout による素通りを防ぐ**。hook の timeout・異常終了・不正な JSON は、両クライアントとも tool 呼び出しを止めない
   (fail-open)。
   - 起動入口は判定の前に git を 3 回 (submodule の中では入れ子 1 段ごとにもう 1 回) 呼び、hook は共有 checkout を
     探すためにもう 1 回呼ぶ。この起動処理が、5 秒の登録 timeout (編集ゲート・Stop) や 15 秒の登録 timeout
     (コマンド制御・submodule 確認) を使い切ると、git が遅いだけで保護が無効になっていた。
   - 起動入口の git 呼び出しは、1 回ごとに `bootstrap.GIT_TIMEOUT` (5 秒)、全体で `bootstrap.STARTUP_BUDGET` (15 秒)
     に収める。入れ子が何段あっても予算を使い切った時点で起動失敗として扱う (PreToolUse は拒否、Stop は差し戻し)。
     PreToolUse と Stop の登録 timeout は両クライアントで 30 秒に揃え、「登録 timeout ≥ 起動予算 + hook の git 呼び出し
     + 余裕」をテストで固定する。通常は 0.1 秒ほどで終わるので、待ち時間が延びるのは git が遅いときだけ。
   - `hook_pre_commands.py` の `git branch -D` 判定は git と `gh` (最大 10 秒) も呼ぶ。判定の締め切りを
     「プロセス起動 + 登録 timeout − 余裕 2 秒」にし、締め切りまでに統合済みと確認できなければ未統合として拒否する。
     起動時刻は起動入口 (`bootstrap.launch`) が `AGENT_KIT_STARTED` に記録する。締め切りの計算は
     `hook_common.hook_deadline` に置き、WorktreeRemove と共有する。hook が想定する登録 timeout と実際の登録値の
     一致はテストで固定する。

## runtime ファイルを足すときの規則

plugin を更新すると、新しい `bootstrap.py` が consumer の古い branch lock を検証する。lock に必須のファイル
(`bootstrap.REQUIRED`) を増やすと、それ以前に作られた lock が全て拒否され、全ツール呼び出しが deny される。
そのため `REQUIRED` は凍結し、新しいファイルは `bootstrap.OPTIONAL` に置く。`OPTIONAL` を含まない lock でも
既存の hook は従来どおり動き、新しいファイルを使う hook だけが `hook is not part of the pinned runtime` で
失敗する (WorktreeRemove なら worktree が残るだけで、追加前と同じ挙動)。v0.5.0 で固定した consumer に
新しい plugin hook を実行してこの挙動を確認し、`tests/test_portable_install.py` で固定した。

## 影響

- consumer は kit の pin 更新 (`--force`) と登録の再生成で新しい挙動になる。Claude は表示された設定を
  `.claude/settings.json` へマージし直し (WorktreeRemove が増える)、Codex は再生成された `.codex/hooks.json` を
  `/hooks` で信頼し直す (起動コードが変わるので全 hook が再レビュー対象。未信頼の間は実行されない)。
- ADR-0005 の WorktreeCreate payload の記述 (`worktree_name` / `source_ref`) は本 ADR で訂正する。
- hook に処理を足すときは、内部の待ち時間の合計を登録 timeout より短く保つ。超えると、その hook の保護は
  黙って無効になる (fail-open)。
