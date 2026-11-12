---
name: issue-to-merge
description: "Carry one piece of work from issue to merged pull request without stalling between stages: create or pick the issue, turn its done-criteria into a goal prompt, start a dedicated worktree, implement and run the project's own check command, open a ready pull request, handle CI and review, squash merge when safe, and clean up. Also use to resume interrupted work by detecting which stage already finished. Works in any language or stack; needs only git and gh. Do NOT use for docs-only or tooling chores that the repository allows on the main branch."
metadata:
  short-description: "Issue → 完了条件 → worktree → 実装と検査 → PR → レビュー対応 → 自動 merge → 掃除を、段の間で止まらずに進める。中断からの再開も扱う。言語・スタック非依存。"
  dependencies: "issue-create, goal-prompt-crafter, worktree-workflow, pr-maintainer, pr-autoloop"
---

# Issue to Merge

1 件の作業を Issue から merge まで運ぶ流れ。各段の詳細は専用の skill が持ち、ここは **段の順序、
段の間で渡すもの、再開のしかた** だけを定める。言語・スタックに依存する部分は「プロジェクトの検査コマンド」
1 つに閉じ込めてあり、それ以外は `git` と `gh` だけで進む。

## 流れ

| 段 | すること | 使う skill | 次の段へ渡すもの |
|---|---|---|---|
| 1 | Issue を作る、または既存の Issue を選ぶ | `issue-create` | Issue 番号、完了条件 |
| 2 | 完了条件を停止条件にする | `goal-prompt-crafter` | 完了条件文 (検査コマンドと上限つき) |
| 3 | 専用の worktree とブランチを作る | `worktree-workflow` | worktree のパス、ブランチ名 |
| 4 | 実装し、検査コマンドを通す | (プロジェクトの rules) | 検査の出力、commit |
| 5 | push して ready な PR を作る | `worktree-workflow` Phase 5 | PR 番号 |
| 6 | CI とレビューに対応し、安全なら squash merge | `pr-autoloop` / `pr-maintainer` | merged / escalated / timeout |
| 7 | worktree とブランチを片付ける | `worktree-workflow` Phase 6 | 最終報告 |

段の間で「続けますか」と聞かない。止まるのは次の場合だけ:

- 完了条件が決まらない (利用者の意図・範囲・価値判断に関わる)
- 認証・権限・ネットワークで進めない。実際のエラーを添えて報告する
- `pr-maintainer` の escalate / timeout に達した
- 利用者が「PR の手前で止めて」「draft のまま」と指定した

repository が worktree と PR を要さないと定めている変更 (文書だけ、開発ツールの chore。git-workflow の
例外節) には、この流れを使わない。

## 検査コマンドを特定する

「テスト・lint・型チェックを通す」の中身はプロジェクトごとに違う。次の順で探し、最初に見つかったものを使う。
見つけたコマンドは Issue の完了条件と PR の本文に書く。

1. `AGENTS.md` / `CLAUDE.md` / README に書かれた検査コマンド
2. CI が実行しているコマンド (`.github/workflows/*.yml` の `run:`)。CI と同じものを手元で通すのが最も確実
3. タスクランナーの定義: `package.json` の `scripts` (`check` / `test` / `lint` / `typecheck`)、
   `Makefile` / `justfile` の target、`pyproject.toml` のツール設定
4. どれも無い: 検査が無いと報告に書き、変更した動作を確かめる最小の実行例を自分で作って出力を残す。
   検査の仕組みを足すのは別の Issue にする

通らない状態で PR を作らない。検査を緩めて通さない (設定の変更、skip、抑制コメント)。

## 段ごとの要点

- **段 1**: 既存の Issue から始めるなら、本文に完了条件があるかを確かめる。無ければ Issue にコメントで
  足してから進む。
- **段 2**: 1 回の実行で終わる小さな作業では、Issue の完了条件をそのまま使ってよい。複数ターンの自律実行に
  渡すときは `goal-prompt-crafter` で上限 (ターン数・時間) と不変条件 (触らない範囲) を足す。
- **段 3**: ブランチ名に Issue 番号を入れる (`fix/issue-<n>` / `feat/issue-<n>`)。
- **段 4**: commit メッセージか PR の本文に `Closes #<n>` を書き、merge で Issue が閉じるようにする。
- **段 5**: draft にしない。PR の本文には、何を変えたか、検査コマンドとその結果、確かめていないことを書く。
- **段 6**: レビューの bot がいない repository、CI が無い repository の扱いは `pr-maintainer` の
  「Review gate」が決める。
- **段 7**: merge を確認してから消す。Issue が閉じたことも確かめる。

## 中断から再開する

セッションが途中で切れた、別のエージェントが引き継ぐ、といった場合は、記憶や前回の報告ではなく
**残っている成果物** から段を判定する。済んだ段をやり直さない。

```bash
gh issue view "$ISSUE" --json state,title,url                      # 段 1: Issue があるか、閉じていないか
git worktree list --porcelain                                      # 段 3: worktree があるか
git -C "$WORKTREE" status --short                                  # 段 4: 未 commit の変更
git -C "$WORKTREE" log --oneline "origin/$DEFAULT..HEAD"           # 段 4: commit 済みの変更
git ls-remote --heads origin "$BRANCH"                             # 段 5: push 済みか
gh pr list --head "$BRANCH" --state all --json number,state,isDraft,mergedAt,url   # 段 5-6: PR の状態
```

| 観察したもの | 再開する段 |
|---|---|
| Issue が無い | 1 |
| Issue はあるが worktree もブランチも無い | 3 (複数ターンの自律実行なら 2 から) |
| worktree に未 commit の変更、または検査が通っていない commit | 4 |
| commit はあるが remote にブランチが無い、または PR が無い | 5 |
| PR が open | 6 |
| PR が merged で worktree が残っている | 7 |
| PR が merged で worktree も無い | 完了。最終報告だけを出す |

外へ出る操作 (push、PR 作成、merge、コメント) は、再実行する前に既に行われていないかを上のコマンドで
確かめる。同じ PR やコメントを 2 つ作らない。

## 最終報告

- Issue と PR の URL
- 最後に観察した状態: merged / escalated / timeout、または止まった段と理由
- 実行した検査コマンドとその結果
- 確かめていないこと

## Related

- `issue-create` / `goal-prompt-crafter` / `worktree-workflow` / `pr-maintainer` / `pr-autoloop`
- git-workflow rule: worktree と PR が必須になる条件と例外
