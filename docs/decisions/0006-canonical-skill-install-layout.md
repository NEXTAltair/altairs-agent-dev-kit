---
type: Decision
title: "ADR-0006: skill 導入を canonical レイアウト(.agents/skills 実体 + .claude/skills symlink)に統一する"
description: install.sh --skills が .claude/skills に実体を置く単一 agent レイアウトを、.agents/skills 実体 + .claude/skills symlink の canonical レイアウトに変更し、skills.sh 既定および検証の期待と一致させる
timestamp: 2026-07-07
status: Accepted
---
# ADR-0006: skill 導入を canonical レイアウトに統一する

## Context

`install.sh --skills` は `npx skills add "$KIT_DIR" --skill '*' --agent claude-code -y --copy`
で skill を導入していた。この単一 agent 指定では skill 実体が `.claude/skills/` に**実ディレクトリ**
として置かれ、`.agents/skills/` も symlink も作られない。

しかし `skills.sh` の既定(canonical レイアウト)は「Codex / GitHub Copilot / OpenCode が共有する
`.agents/skills/` に canonical な実体を置き、各 agent dir はそこへの symlink」であり、これを前提に
検証する consumer(例: `.claude/skills/<name>` が symlink であることを要求する `validate_harness`)
では、`install.sh --skills` の生成物が**非互換**(`.claude/skills` 実体化で検証が落ちる)だった。

補足として、公式 README・実測で以下を確認した:

- `--copy` は「各 agent へ独立コピー(symlink 非対応環境向け)」であり、**単一 agent 指定では no-op**。
- ローカルパス source は `--copy` の有無に関わらず常にコピーされる(source への live link モードは無い)。
- `.agents/skills` は特定 agent の dir ではなく、複数 agent 共有の canonical 実体置き場。

## Decision

`install.sh --skills` を canonical レイアウトを生成するよう変更する:

- `--agent codex` で実体を `.agents/skills/` に置く(universal 配置)。
- 各 skill について `.claude/skills/<name>` → `../../.agents/skills/<name>` の**相対 symlink** を
  install.sh 側で明示生成する(`--agent codex` は `.claude` を作らないため)。
- symlink 非対応環境(Windows で開発者モード無効など)では `.claude/skills/<name>` を実体コピーに
  フォールバックする。
- README の `--skills` 説明を canonical レイアウトに更新する。
- 導入 / 更新の手順とモデルは [skill 導入 runbook](../skill-install-runbook.md) に明文化する。

## Rationale

canonical レイアウトは `skills.sh` 既定・`validate_harness` の期待・複数 agent 共有のいずれとも
整合し、consumer が別 installer を併用しても構造が一致する。単一 agent の `.claude/skills` 実体は
Claude Code 単独なら動くが、canonical を前提とする consumer と混在すると検証が落ち、
どの経路で入れたかによって挙動が変わる分かりにくさ(および skill の二重実体化)の温床になる。
「一次情報で確認してから壊す」に従い、`--copy` の実挙動と `.agents/skills` の役割を実測・公式
ドキュメントで確認した上で、canonical に一本化する。
