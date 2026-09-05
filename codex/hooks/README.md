# Codex hooks

`scripts/install_harness.py` が `.codex/hooks.json` を生成する。
`command` は Linux、`commandWindows` は Windows の Python を起動し、標準ライブラリだけの
共通 bootstrap が作業 checkout の `.agent-kit/hooks.lock.json` に対応する runtime を検証する。
override は作業 checkout、runtime は版固定した `.agent-kit/runtimes/<ID>` から読む。

このディレクトリのスクリプトは kit ソース配置用 adapter。consumer にはコピーしない。
以前の adapter / `.claude/hooks/*.py` の直接登録は生成された起動設定へ移行する。
詳細と復元・固有 hook の接続方法は [Hook runtime 契約](../../docs/hook-runtime.md) を参照。
