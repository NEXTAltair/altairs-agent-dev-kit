---
type: Decision
title: "ADR-0001: codex/agents/*.toml を agents/*.md からの生成物にする"
description: 手動コピーで drift していた codex agent 定義を md 単一ソースの生成方式に変更し、CI で drift を検出する
timestamp: 2026-07-05
status: Accepted
---
# ADR-0001: codex/agents/*.toml を agents/*.md からの生成物にする

## Context

`codex/agents/*.toml` は `agents/*.md` の本文を `developer_instructions` に手動コピーし
`Claude → Codex` の sed をかけたスナップショットだった。生成ステップが存在せず
(install.sh は toml を単にコピーするだけ)、既に drift していた:

- `security-reviewer.toml` の `Anthropic/Codex API keys` (sed の巻き添えによる事実誤り)
- 改行コードが CRLF、複数行文字列の区切りが `"""` と `'''` の混在
- `agents/*.md` 側の markdown 破損が toml にも複製 (issue #4)

監査 issue #5 / 親 issue #1 の決定コメント (2026-07-05) で「Codex 対応は維持し生成化する
(案 A)」と確定した。

## Decision

- `scripts/generate_codex_agents.py` を追加し、`agents/*.md` を単一ソースとして
  `codex/agents/*.toml` を生成する。toml は手編集禁止の生成物とする。
- 語彙置換はハーネス名フレーズ `"Claude Code" → "Codex"` のみ。裸の `Claude` /
  `Anthropic` は製品・API への言及なので置換しない。
- `library-research` は WebFetch/WebSearch 前提のため生成対象外 (agents ×10 / codex ×9 の
  設計判断を維持)。
- 出力は LF・`'''` (リテラル複数行文字列) に正規化し、`.gitattributes` で
  `codex/agents/*.toml` を `eol=lf` に固定する。
- CI に `generate_codex_agents.py --check` を追加し、md と toml の drift・orphan toml を
  検出して fail させる。

## Rationale

代替案は「codex/hooks と同様に md を直接参照する」(案 B) だったが、Codex の agent 定義は
toml 形式を要求するため参照だけでは成立せず、変換レイヤが必ず要る。変換を都度手作業に
するのが今回の drift の原因なので、決定論的な生成 + CI 検出に固定した。

## Consequences

- `agents/*.md` を変更する PR は `uv run python scripts/generate_codex_agents.py` を実行して
  toml を同時に更新する (忘れると CI が落ちる)。
- toml への直接編集は次回生成で消える。Codex 固有の記述が必要になった場合は
  生成スクリプトの PHRASE_MAP / SKIP_AGENTS を拡張する。
- issue #2 / #4 / #6 / #8 の agents 修正は md 側のみ行い toml は再生成で追従する。
