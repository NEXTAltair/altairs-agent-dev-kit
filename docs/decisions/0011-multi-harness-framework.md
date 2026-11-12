---
type: Decision
title: "ADR-0011: 4 ハーネス対応の導入 CLI と global / project の分類を持つ"
description: Claude Code / Codex に加えて Antigravity と OpenClaw へ導入できる agent_kit.py を追加し、部品を kit.json で profile と推奨 scope に分類する。OpenClaw 固有の定義は kit に持たない
timestamp: 2026-11-12
status: Accepted
---
# ADR-0011: 4 ハーネス対応の導入 CLI と global / project の分類を持つ

## 背景

kit は Claude Code と Codex、Python/uv プロジェクトだけを対象にしていた。利用者は次を求めた (2026-11-12)。

- Claude Code / OpenClaw / Codex / Antigravity のどれでも使える開発フレームワークにする
- OpenClaw 専用の skill / hook / plugin は OpenClaw 自身の SDK で定義するものなので、kit には開発フレームワークとして
  定義すべきものだけを置く
- global に置くべきものは global へ、project ごとに置くべきものは project へ、簡単に導入できるようにする

各ハーネスの配置先を公式ドキュメントと実バイナリで調べた結果は [harness-matrix.md](../harness-matrix.md) にある。

## 決定

1. **共通の土台は `AGENTS.md` と `.agents/skills/`**。4 つすべてが読む指示ファイルは `AGENTS.md` だけで、
   `.agents/skills/` は Claude Code 以外の 3 つが直接読む。差がある部分 (rules の frontmatter、agent 定義の形式) だけを
   ハーネス別に生成する。
2. **部品の分類は `kit.json` に一本化する**。skill / rule / agent ごとに `profile` (core / python / qt / sql) と
   推奨 `scope` (global / project) を持つ。rule は読み込み方 (`always` / `on-demand` / `glob`) と説明も持つ。
   - global: どのプロジェクトでも同じ内容で効いてよいもの。profile は core に限る (テストで固定)
   - project: スタックに依存するもの、または repository の構成 (worktree、ADR の置き場) を前提にするもの
   - global を導入していない環境 (チームの他の人、CI、クラウド上の agent) 向けに、`--standalone` で global 向けの
     部品も repository へ入れられる
3. **導入は `scripts/agent_kit.py` (stdlib のみ) が行う**。`--scope` と `--harness` (既定は自動検出) で配置先が決まる。
   - rules の原本は frontmatter を持たない Markdown のまま。Antigravity 向けには `trigger:`、Claude Code 向けには
     glob 指定の rule だけ `paths:` を導入時に付ける
   - rules を自動で読まない Codex / OpenClaw には、`AGENTS.md` の管理区画に索引 (必ず読むもの / 該当作業の前に読むもの)
     を書く。区画の外の本文には触れない
   - Antigravity の agent 定義は `agents/*.md` から `antigravity/agents/*.md` へ生成し、CI で drift を検出する
     (Codex の toml と同じ扱い、[ADR-0001](0001-codex-agents-generated-from-md.md))
   - skills は skills.sh に委ねる。実体は `.agents/skills/`、Claude Code (と global の Antigravity) には symlink
   - 置いたファイルの内容ハッシュを導入記録に残し、kit が置いて未変更のファイルだけを更新・削除する
4. **OpenClaw 固有のものは kit に持たない**。OpenClaw の agent workspace (`AGENTS.md` / `SOUL.md` 等)、`openclaw.json`、
   plugin、hook には触れない。OpenClaw が repository で作業するときは作業フォルダの `AGENTS.md` と `.agents/skills/` を
   読むので、project scope の導入がそのまま効く。global の skill は `~/.agents/skills/` から読まれる。
5. **CI の汎用性 grep gate から `OpenClaw` を外す**。この語は [ADR-0002](0002-remove-openclaw-ltm-residue.md) で移植元の
   私設メモリサービスの残骸を検出するために入れたもので、対応ハーネスとしての OpenClaw への言及まで止めてしまう。
   残骸そのものを指す語 (`clawdbot`、`ltm_search` 等) は gate に残す。
6. **`install.sh` は Claude Code + Codex の導入経路として残す**。既存の導入先と lock の扱いを変えない。
   uv の必須チェックもそのまま (python profile 前提の経路のため)。`agent_kit.py` は uv が無くても動き、
   python profile を選んだときだけ警告する。

## やらなかったこと

- **Antigravity の hooks**。payload と判定の契約が違い ([harness-matrix.md](../harness-matrix.md))、Stop に応答本文が
  渡らない。runtime の起動入口に provider を足す変更になるので、別の変更として扱う。
- **global の hooks**。runtime を checkout ごとに固定する設計と両立する形を決めていない。
- **Codex / Antigravity の plugin 形式での配布**。kit のルートを複数の plugin 形式で同時に成立させるには、
  Claude Code 形式の原本 (`rules/`、`agents/`) と生成物の置き場を分ける必要がある。
- **rules 本文の書き換え**。python profile の rule は uv / Ruff を前提にしたまま。他言語の profile は追加していない。

## 検証

- `agy plugin validate --strict` (Antigravity CLI 1.5.5) で、生成した rules 11 本と agents 8 本が合格。原本に差し替えると落ちる
- skills.sh を一時 repository と隔離した HOME で実行し、project / global の配置を確認
- `tests/test_agent_kit.py` は、利用者の変更の保持・global の選別・索引の置換・uninstall の範囲・skills.sh への
  引数を固定する。5 種類の変異 (利用者の変更を上書き、global に全部品、変更済みファイルの削除、索引の二重追記、
  Antigravity の global symlink の欠落) でそれぞれ落ちることを確認した
- Claude Code / Codex / OpenClaw の実セッションで読み込まれることは確かめていない
