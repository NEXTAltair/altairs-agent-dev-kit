---
type: Reference
title: ハーネス別の配置先と kit の対応
description: Claude Code / Codex / Antigravity / OpenClaw が指示・rules・skills・agents・hooks をどこから読むかの調査結果と、kit がどこへ何を置くかの対応表
timestamp: 2026-11-12
---
# ハーネス別の配置先と kit の対応

`scripts/agent_kit.py` が各ハーネスへ置く場所の根拠。調査日は 2026-11-12、確認した版は
Claude Code 2.1.322 / Codex CLI 0.167.0 / Antigravity CLI (`agy`) 1.5.5 / skills.sh CLI (`skills@1`)。
配置先は各ハーネスの更新で変わるので、版を上げたときはこの表を一次情報と照合し直す。

## 各ハーネスが読む場所

| 種別 | Claude Code | Codex | Antigravity | OpenClaw |
|---|---|---|---|---|
| 指示ファイル (project) | `CLAUDE.md`。無いときだけ `AGENTS.md` (v2.1.277 以降) | `AGENTS.md` | `AGENTS.md` / `GEMINI.md` | 作業フォルダの `AGENTS.md` だけを project context として読む |
| 指示ファイル (global) | `~/.claude/CLAUDE.md` | `~/.codex/AGENTS.md` | `~/.gemini/AGENTS.md` / `GEMINI.md` | agent workspace の `AGENTS.md` 等 (OpenClaw が管理) |
| rules (project) | `.claude/rules/*.md` (`paths:` で対象を絞る) | 専用の置き場なし | `.agents/rules/*.md` (`trigger:` frontmatter 必須) | 専用の置き場なし |
| rules (global) | `~/.claude/rules/*.md` | 専用の置き場なし | `~/.gemini/config/rules/*.md` | — |
| skills (project) | `.claude/skills/` | `.agents/skills/` | `.agents/skills/` | `<workspace>/.agents/skills/` (作業フォルダのものも読む) |
| skills (global) | `~/.claude/skills/` | `~/.agents/skills/` | `~/.gemini/config/skills/` | `~/.agents/skills/` |
| subagent 定義 (project) | `.claude/agents/*.md` | `.codex/agents/*.toml` | `.agents/agents/*.md` | OpenClaw の設定と SDK で定義 |
| subagent 定義 (global) | `~/.claude/agents/*.md` | `~/.codex/agents/*.toml` | `~/.gemini/config/agents/*.md` | 同上 |
| hooks (project) | `.claude/settings.json` の `hooks` | `.codex/hooks.json` | `.agents/hooks.json` | plugin SDK の hook |
| hooks (global) | `~/.claude/settings.json` | `~/.codex/hooks.json` | `~/.gemini/config/hooks.json` | 同上 |
| plugin | `.claude-plugin/plugin.json` + marketplace | ルート `plugin.json` (Agent Plugins)、互換として `.codex-plugin/plugin.json` | `.antigravity-plugin/plugin.json` またはルート `plugin.json` | OpenClaw plugin SDK |

出典:

- Claude Code: [memory](https://code.claude.com/docs/en/memory) (AGENTS.md の読み込み条件、`.claude/rules/` と `paths:`)、
  [skills](https://code.claude.com/docs/en/skills)、[sub-agents](https://code.claude.com/docs/en/sub-agents)、
  [hooks](https://code.claude.com/docs/en/hooks)
- Codex: [hooks](https://learn.chatgpt.com/docs/hooks)、同ドキュメントの subagents (`.codex/agents/*.toml`) と
  plugin のパッケージ手順 (ルート `plugin.json` と `.codex-plugin/plugin.json` の互換)
- Antigravity: [rules](https://antigravity.google/docs/rules)、[skills](https://antigravity.google/docs/skills)、
  [subagents](https://antigravity.google/docs/subagents)、[hooks](https://antigravity.google/docs/hooks)、
  [plugins](https://antigravity.google/docs/plugins)
- OpenClaw: [skills](https://docs.openclaw.ai/tools/skills) (読み込み元の優先順位)、
  [system prompt](https://docs.openclaw.ai/concepts/system-prompt) (作業フォルダは `AGENTS.md` だけを足す)
- skills.sh: `npx skills@1 add` を隔離した HOME と一時 repository で実行し、生成された配置を確認

読み取れる共通項は 2 つ。`AGENTS.md` は 4 つすべてが読む唯一の指示ファイルで、`.agents/skills/` は
Claude Code 以外の 3 つが直接読む skill の置き場である。kit はこの 2 つを共通の土台にし、差がある部分だけを
ハーネス別に生成する。

## kit が置く場所

### project scope (`--scope project --target <repo>`)

| 部品 | 置き場 | 対象ハーネス |
|---|---|---|
| skills | `.agents/skills/<name>/` (実体、skills.sh 経由) | Codex / Antigravity / OpenClaw |
| | `.claude/skills/<name>` (symlink) | Claude Code |
| rules | `.agents/rules/<name>.md` (`trigger:` frontmatter 付き) | Antigravity が直接読む。Codex / OpenClaw は索引から読む |
| | `.claude/rules/<name>.md` (glob 指定の rule だけ `paths:` 付き) | Claude Code |
| rules の索引 | `AGENTS.md` の `<!-- agent-kit:begin -->` 〜 `<!-- agent-kit:end -->` | Codex / OpenClaw (rules を自動で読まないハーネス) |
| agents | `.claude/agents/<name>.md` | Claude Code |
| | `.codex/agents/<name>.toml` (`codex/agents/` の生成物) | Codex |
| | `.agents/agents/<name>.md` (`antigravity/agents/` の生成物) | Antigravity |
| hooks | `.agent-kit/` の runtime と lock、`.codex/hooks.json`、Claude Code 用の配線 JSON を表示 | Claude Code / Codex |
| 導入記録 | `.agent-kit/install.json` | — |

### global scope (`--scope global`)

| 部品 | 置き場 | 対象ハーネス |
|---|---|---|
| skills | `~/.agents/skills/<name>/` (実体) | Codex / OpenClaw |
| | `~/.claude/skills/<name>`、`~/.gemini/config/skills/<name>` (symlink) | Claude Code / Antigravity |
| rules | `~/.claude/rules/`、`~/.gemini/config/rules/`、`~/.agents/rules/` | Claude Code / Antigravity / Codex |
| rules の索引 | `~/.codex/AGENTS.md` (`CODEX_HOME` があればその下) の管理区画 | Codex |
| agents | `~/.claude/agents/`、`~/.codex/agents/`、`~/.gemini/config/agents/` | Claude Code / Codex / Antigravity |
| 導入記録 | `~/.agents/agent-kit/install.json` | — |

skills の実体が既にあるとき (先に別のハーネス向けに導入した、link を消した) は、`install` が足りない link だけを足す。
`--force` は実体を入れ直すときだけ要る。

`~/.agents/rules/` は kit が決めた置き場で、Codex が自動で読む場所ではない。Codex は `~/.codex/AGENTS.md` の
索引に書かれたパスを辿って読む。

## 対応していないもの

| 項目 | 状態 |
|---|---|
| Antigravity の hooks (`.agents/hooks.json`) | 未対応。payload が `toolCall.name` / `toolCall.args` の camelCase、判定は `{"decision": "deny"}` で、Claude Code / Codex と契約が違う。Stop には最後の応答本文が渡らないので応答監視は同じ形では動かない |
| global の hooks | 未対応。hook の runtime は checkout ごとに内容ハッシュで固定する設計 ([hook-runtime.md](hook-runtime.md)) |
| Codex / Antigravity の plugin 形式での配布 | 未対応。kit のルートは Claude Code plugin の配置で、`rules/` と `agents/` は Claude Code 形式の原本なので、そのまま Antigravity plugin として読ませると検証に落ちる |
| OpenClaw の agent workspace (`AGENTS.md` / `SOUL.md` 等)、`openclaw.json`、plugin / hook | 対象外。OpenClaw 自身の SDK と設定で定義するもので、kit は触れない ([ADR-0011](decisions/0011-multi-harness-framework.md)) |

## 検証した範囲

- `agy plugin validate --strict` (1.5.5): kit が生成した rules 14 本と agents 8 本を一時 plugin に入れて合格。
  生成前の原本 (`rules/testing.md`、`agents/test-runner.md`) に差し替えると 2 件のエラーで落ちることも確認
- skills.sh: project は `-a codex claude-code`、global は `-a codex claude-code antigravity -g` で上表の配置になる
- Claude Code / Codex / OpenClaw が導入後のファイルを実際のセッションで読み込むことは、この調査では確かめていない。
  配置先は上記の公式ドキュメントに基づく
