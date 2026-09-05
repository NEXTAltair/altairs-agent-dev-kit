# skill 導入 / 更新 runbook

kit の skill を consumer リポジトリへ導入・更新する際の手順と、その裏にある配布モデルをまとめる。
「どの経路で入れるか」「更新はどうするか」で迷わないための一次リファレンス。

## 配布モデル(全体像)

skill の実体は `skills.sh` (`npx skills`) が管理し、2つの経路で consumer に入る:

| 経路 | 用途 | 実体の入り方 |
|---|---|---|
| kit `install.sh --skills` | 公開タグの同梱 skill を一括導入 | `.agents/skills/` に実体 + `.claude/skills/` に symlink(canonical レイアウト) |
| consumer 独自 installer(`skills-lock.json` ベース) | released skill を pin して復元 | 同上。lock の `sourceType` に応じて github/local から復元 |

### canonical レイアウト

- `.agents/skills/<name>` = **実体**(Codex / GitHub Copilot / OpenCode が共有する canonical dir)
- `.claude/skills/<name>` = `../../.agents/skills/<name>` への **symlink**(Claude Code はこちらを読む)

これは `skills.sh` 既定の「canonical コピー + 各 agent の symlink」と一致し、
`.claude/skills/<name>` が symlink であることを要求する検証(`validate_harness` 等)にも通る。
`--copy`(各 agent へ独立コピー)は symlink 非対応環境向けのフォールバックであり、
`.claude/skills` に実体を置く単一 agent レイアウトは canonical と非互換なので避ける。

## sourceType の使い分け(`skills-lock.json`)

| sourceType | 用途 | 例 |
|---|---|---|
| `github` + `ref` | **released skill**(推奨)。タグに pin して再現性・ポータビリティを担保 | `{ "source": "owner/kit", "ref": "v0.2.2", "sourceType": "github" }` |
| `local` | consumer 自前 skill、または開発中に kit を手元参照する場合のみ | git 追跡された自前 skill |

> **絶対パスや consumer 外へ出る相対 `local` source は非ポータブル**(別マシン / CI で解決できない)。
> released skill は必ず `github@ref` を使う。検出は下記 `check_skills_lock.py`。

## kit 一括導入の更新契約

公開タグを checkout して `install.sh --skills` を実行する。既定 source は GitHub origin とそのタグ。
タグのない checkout は明示的な `--skill-source` が必要で、ローカル source へ自動 fallback しない。
skills@1 は ref を clone の branch/tag として使うため、commit SHA の直指定では復元できない。

既存 canonical または Claude 側 skill は `--force` なしでは保持する。lock だけがある新規 checkout
でも、固定 source/ref と異なる版への置換は拒否する。同じタグから復元するか、意図的な更新に
`--skills --force` を使い lock 差分をレビューする。kit に含まれない skill には触れない。
`--force` は kit 所有の同名 skill のローカル編集を置換するため、必要な変更は先に保存する。

未公開の kit を検証する場合のみ `--skill-source /absolute/path/to/kit` を使う。
この経路の local lock は開発用であり、公開用の GitHub pin へ戻してからコミットする。

## released kit skill を更新する(github@ref bump)

kit 側で skill を直したものを consumer に反映する正しい手順:

1. **kit**: 専用 worktree で編集・検証し、PR がレビューを通ってマージされた後にリリースタグを公開する
   ```bash
   git fetch origin
   git tag -a vX.Y.Z origin/main -m "vX.Y.Z"
   git push origin vX.Y.Z
   ```
2. **consumer**: lock を新タグへ bump(ref と hash を一括更新する。ref だけ手で書き換えると
   独自 installer の drift 検出に弾かれる)
   ```bash
   npx skills add "github:owner/kit#vX.Y.Z" --skill <name> --agent codex -y
   ```
3. **consumer**: `.claude/skills` symlink と state を整えて検証 → `skills-lock.json` をコミット
   (consumer の installer / `make skills-install` 等がある場合はそれを実行)

## footgun: ローカルパス add で pin が壊れる

`github@ref` で pin 済みの skill に対し、うっかり

```bash
npx skills add /abs/path/to/kit --skill <name>   # ← やってはいけない
```

を実行すると、lock の該当エントリが**黙って** `sourceType: github`(ref pin)から
`sourceType: local` + 絶対パスに書き換わり、pin とポータビリティが壊れる。警告は出ない。

- 事故ったら `git checkout skills-lock.json` で revert
- pin 済み skill の更新は必ず上記「github@ref bump」手順で行う
- 検出用の lint を CI / pre-commit に入れる:
  ```bash
  python scripts/check_skills_lock.py --root .
  ```
  `skills-lock.json` 内の絶対パス、consumer 外の相対 local source、不正な lock 形式を検出して非ゼロ終了する。

## 関連

- [ADR-0006: skill 導入を canonical レイアウトに統一する](decisions/0006-canonical-skill-install-layout.md)
- [導入ガイド](adoption.md)
- [サードパーティ skills](third-party-skills.md)
