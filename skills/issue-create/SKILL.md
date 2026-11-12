---
name: issue-create
description: "Turn a bug, improvement, or task into a GitHub issue that an agent can implement without asking again: search for duplicates, write evidence (version, command, actual output), and state the done-criteria as a command that can be run. Use when asked to file or write up an issue, when work is about to start without one, or when an out-of-scope defect is found mid-task. Works in any language or stack; needs only git and gh. Do NOT use for filing on repositories the user does not own unless they asked for it."
metadata:
  short-description: "不具合・改善・作業を、追加の質問なしに実装へ進める Issue にする。重複検索、根拠、実行できる完了条件。言語・スタック非依存。"
---

# Issue Create

実装を始められる Issue を作る手順。言語・スタックに依存せず、`git` と `gh` だけを使う。
Issue は「何が起きているか」と「何をもって完了とするか」を、後から読む別のエージェントや人が
質問なしに理解できる形で残すためのもの。

## When to Use

- 「Issue 作って」「起票して」と言われたとき
- 実装に着手しようとして、対応する Issue が無いとき (`issue-to-merge` の最初の段)
- 依頼された作業の途中で、依頼範囲の外にある不具合・文書の誤り・テストの欠陥を見つけたとき

## 起票先を決める

```bash
gh repo view --json nameWithOwner,isFork,viewerPermission,parent \
  --jq '{repo: .nameWithOwner, fork: .isFork, permission: .viewerPermission, parent: .parent.nameWithOwner}'
```

- `permission` が `ADMIN` / `MAINTAIN` / `WRITE` の repository には、確認を取らずに起票してよい。
- それ以外 (他人の repository、fork の `parent`) へは、利用者が起票を頼んだときだけ起票する。
  頼まれていなければ、下書きを会話に出して止める。
- セキュリティ上の欠陥は公開の Issue にしない。repository の報告手順 (`SECURITY.md`) に従う。

## 手順

1. **重複を探す。** 既にあれば新規に作らず、その Issue に根拠を追記する。

   ```bash
   gh issue list --state all --search "<症状や対象を表す語> in:title,body" --json number,title,state,url
   ```

   閉じた Issue と同じ症状なら、再発として新規に作り、元の Issue を本文で参照する。

2. **根拠を集める。** 自分で確かめられることは起票前に確かめる。
   - 版 (ツール、ランタイム、対象の commit)
   - 実行したコマンドと実際の出力 (要点を抜粋。長いログは折りたたむ)
   - 再現手順。再現できなかった場合は、できなかったと書く
   - 推測は推測と明記する。確かめた事実と混ぜない

3. **完了条件を、実行できる形で書く。** 「直す」「改善する」ではなく、実行するコマンドと期待する結果。
   プロジェクトの検査コマンドが分からなければ `issue-to-merge` の「検査コマンドを特定する」で調べる。

4. **起票する。** 本文はファイルから渡す (shell の引用で壊れない)。

   ```bash
   gh issue create --title "<対象>: <起きていること>" --body-file issue.md
   ```

   label は repository に既にあるものだけを付ける (`gh label list`)。無い label を作らない。

5. **Issue の URL を報告する。** 続けて実装するなら `issue-to-merge` へ進む。

## 本文の形

````markdown
## 起きていること
<観察した事実。1〜3 文>

## 根拠
- 版: <ツール / ランタイム / commit>
- 実行: `<コマンド>`
- 出力:
  ```
  <実際の出力の要点>
  ```
- 再現手順: <手順、または「再現できていない」>

## 期待する動作
<こうなるべき、を 1〜2 文>

## 完了条件
- `<検査コマンド>` が通る
- <観察できる結果。例: `<コマンド>` の出力に <語> が含まれない>

## 範囲に含めないこと
<今回やらないこと。無ければ節ごと省く>
````

- タイトルは対象と症状を書く。「〜の件」「不具合」だけにしない。
- 1 つの Issue には 1 つの完了条件の組。独立に完了できる作業は分ける。
- 原因の推測や修正案は、確かめた範囲だけを「根拠」に書く。確かめていない案は「推測」と見出しを分ける。
- 本文の言語は repository の既存の Issue に合わせる。

## Related

- `issue-to-merge`: Issue から merge までの全体の流れ
- `goal-prompt-crafter`: 完了条件を自律実行の停止条件にする
