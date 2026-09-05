# Index

* [ADR-0001: codex/agents/*.toml を agents/*.md からの生成物にする](decisions/0001-codex-agents-generated-from-md.md) — 手動コピーで drift していた codex agent 定義を md 単一ソースの生成方式に変更し、CI で drift を検出する
* [ADR-0002: OpenClaw/clawdbot 長期記憶インフラの残骸を除去する](decisions/0002-remove-openclaw-ltm-residue.md) — 移植元の私設メモリサービスへの参照を agents/skills から全削除し、長期記憶連携の抽象フックも残さない
* [ADR-0003: planning-memory を documentation-maintenance / git-workflow に整合させる](decisions/0003-align-planning-memory-rules.md) — ADR 索引の手編集指示を生成方式に統一し、具体パスをプロジェクト固有注記でゲートし、Proposed ADR の worktree 隔離を相互参照する
* [ADR-0004: 移植元ドメインの実例を中立化し、キットの対象スタックを明示する](decisions/0004-generalize-domain-examples.md) — 画像アノテーション由来のスキーマ・モジュール名・パッケージ名を中立例に置換し、Python/uv (GUI 例は Qt) 前提を README で宣言する
* [ADR-0005: hooks を Claude Code 現行スキーマに更新し WorktreeCreate は公式契約準拠で維持する](decisions/0005-hooks-current-schema.md) — PreToolUse のブロックを permissionDecision=deny + exit 0 に統一し、監査時に「存在しない」とされた WorktreeCreate は公式ドキュメントで実在を確認して維持・契約準拠化した
* [ADR-0006: skill 導入を canonical レイアウト(.agents/skills 実体 + .claude/skills symlink)に統一する](decisions/0006-canonical-skill-install-layout.md) — install.sh --skills が .claude/skills に実体を置く単一 agent レイアウトを、.agents/skills 実体 + .claude/skills symlink の canonical レイアウトに変更し、skills.sh 既定および検証の期待と一致させる
* [ADR-0007: unknowns discovery を汎用ルールとして追加する](decisions/0007-add-unknowns-discovery-rule.md) — AI エージェントがプロンプト・計画・ルールに書かれていない前提を推測で埋める問題を、Fable 固有の skill ではなく作業横断の unknowns discovery ルールとして扱う
* [ADR-0008: PR autoloop は bounded time-based loop として扱い hook は adapter 分離する](decisions/0008-loop-contracts-and-hook-adapters.md) — PR 保守 loop の観測可能な停止条件と、provider 別の起動設定・共有 policy・branch 固定 runtime の責務を定義する
* [altairs-agent-dev-kit 設計書](superpowers/specs/2026-07-02-altairs-agent-dev-kit-design.md) — LoRAIro の開発標準を汎用化し独立リポジトリとして配布するための設計方針
* [altairs-agent-dev-kit Implementation Plan](superpowers/plans/2026-07-02-altairs-agent-dev-kit.md) — skills / rules / hooks / agents / Codex 設定を汎用化し3経路で導入できる kit を構築する実装計画
* [docs-freshness-audit skill 設計](superpowers/specs/2026-07-05-docs-freshness-audit-skill-design.md)
* [導入ガイド](adoption.md) — skills / rules / hooks / agents / Codex 設定を任意リポジトリへ導入する3経路と設定上書き方法
* [Hook runtime の固定・復元契約](hook-runtime.md) — 作業 checkout の lock と override、共有 runtime、起動・復元失敗の扱い
* [portable-hooks](portable-hooks.md)
* [skill-install-runbook](skill-install-runbook.md)
* [サードパーティ skills](third-party-skills.md) — 本 kit に同梱しないサードパーティ skill の npx skills add インストールリスト
