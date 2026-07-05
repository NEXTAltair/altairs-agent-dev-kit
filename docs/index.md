# altairs-agent-dev-kit Docs Index

* [altairs-agent-dev-kit 設計書](superpowers/specs/2026-07-02-altairs-agent-dev-kit-design.md) — LoRAIro の開発標準を汎用化し独立リポジトリとして配布するための設計方針
* [altairs-agent-dev-kit Implementation Plan](superpowers/plans/2026-07-02-altairs-agent-dev-kit.md) — skills / rules / hooks / agents / Codex 設定を汎用化し3経路で導入できる kit を構築する実装計画
* [導入ガイド](adoption.md) — skills / rules / hooks / agents / Codex 設定を任意リポジトリへ導入する3経路と設定上書き方法
* [サードパーティ skills](third-party-skills.md) — 本 kit に同梱しないサードパーティ skill の npx skills add インストールリスト
* [ADR-0001: codex/agents/*.toml を agents/*.md からの生成物にする](decisions/0001-codex-agents-generated-from-md.md) — 手動コピーで drift していた codex agent 定義を md 単一ソースの生成方式に変更し、CI で drift を検出する
* [ADR-0002: OpenClaw/clawdbot 長期記憶インフラの残骸を除去する](decisions/0002-remove-openclaw-ltm-residue.md) — 移植元の私設メモリサービスへの参照を agents/skills から全削除し、長期記憶連携の抽象フックも残さない
* [ADR-0003: planning-memory を documentation-maintenance / git-workflow に整合させる](decisions/0003-align-planning-memory-rules.md) — ADR 索引の手編集指示を生成方式に統一し、具体パスをプロジェクト固有注記でゲートし、Proposed ADR の worktree 隔離を相互参照する
