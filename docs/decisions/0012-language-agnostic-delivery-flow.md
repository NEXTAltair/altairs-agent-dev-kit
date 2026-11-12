---
type: Decision
title: "ADR-0012: Issue から merge までの流れを言語非依存の core にし、global に置く"
description: Issue 起票・完了条件・worktree・PR レビュー対応・自動 merge の skills と git-workflow rule から Python/uv と特定ハーネスの前提を外し、通しの手順と起票の skill を足して global に分類した
timestamp: 2026-11-12
status: Accepted
---
# ADR-0012: Issue から merge までの流れを言語非依存の core にし、global に置く

## 背景

利用者の指摘 (2026-11-12): Issue を作り、ゴールプロンプトを作り、worktree を作成し、PR のレビュー対応から自動 merge
までの流れは、どの言語でもどのプロジェクトでも使えるはず。

実際には次の前提が混ざっていた。

| 場所 | 混ざっていた前提 |
|---|---|
| `worktree-workflow` | 共有 venv と `uv run` を全 worktree の前提にしていた。Node.js では依存を worktree 間で共有できない |
| `pr-maintainer` / `pr-autoloop` | レビューの完了を Codex connector の reaction だけで判定。bot のいない repository では必ず 20 分の timeout になる。返信は日本語固定、検証は「Ruff と mypy」、待機の方法は Claude Code と Codex だけ |
| `goal-prompt-crafter` | 例の検証コマンドがすべて `uv run pytest` / `ruff` |
| git-workflow rule | 検証の手順が Python 向けの rule (coding-style / testing) へのリンク。project scope |
| `hook_worktree_remove.py` | 消してよい ignore 対象が Python のキャッシュだけ。`node_modules` がある worktree は merge 後も必ず残る |
| kit 全体 | Issue を起票する skill と、流れ全体をつなぐ skill が無い |

## 決定

1. **スタックに依存する入力を「プロジェクトの検査コマンド」1 つに閉じ込める。** 探し方 (指示ファイル → CI の実行コマンド →
   タスクランナーの定義 → 無ければ無いと報告) を `issue-to-merge` に置き、他の skill はそこを参照する。
2. **`issue-create` を足す。** 起票先の権限確認、重複検索、根拠、実行できる完了条件。
3. **`issue-to-merge` を足す。** 段の順序と段の間で渡すものだけを定め、詳細は既存の skill に委ねる。
   中断からの再開は、記憶や前回の報告ではなく残っている成果物 (Issue、worktree、remote のブランチ、PR) から段を判定する。
4. **レビューの完了条件を repository ごとに決める (`pr-maintainer` の Review gate)。** 指示ファイルに書いてあればそれ、
   無ければ直近 5 件の merge 済み PR に bot の成果物があるかで判定する。bot がいなければ CI と人のレビューだけを条件にし、
   CI も無ければ手元で検査コマンドを実行して結果を PR に残す。
5. **返信の言語は repository の作業言語 (PR の説明や Issue で使われている言語) に合わせる。** bot が書く言語には合わせない。 待機の方法に Antigravity (`schedule`) と OpenClaw (automation) を足す。
6. **worktree の依存環境はスタック別に定める。** Python + uv は共有、Node.js は worktree ごとに install。
7. **`hook_worktree_remove.py` が消してよい ignore 対象に `node_modules`、`*.tsbuildinfo`、`.eslintcache` を足す。**
   lockfile と source から作り直せるものに限る。`dist/` のような生成物は足さない。runtime の内容が変わるので、
   導入先は次のリリースで branch pin を更新する ([hook-runtime.md](../hook-runtime.md))。
8. **これらを core かつ global に分類する** (`kit.json`)。`worktree-workflow` と git-workflow rule は project から global へ移した。
   global を導入していない環境には `--standalone` で repository へ入れる。

## 検証

- 直近 5 件の merge 済み PR から bot を判定するコマンドを、この repository で実行した (Codex connector を検出)
- `gh pr checks --json` は gh 2.45 に無いことを実機で確認し、`statusCheckRollup` を使う代替を書いた
- `node_modules` (pnpm の symlink 配置を含む) だけが残る worktree を hook が削除し、`dist/` が残る worktree は残すテストを追加
- Antigravity / OpenClaw の待機の方法、bot のいない repository での merge までの通しは、実際には動かしていない
