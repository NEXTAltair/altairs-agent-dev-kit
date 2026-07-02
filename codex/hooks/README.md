# Codex hooks

Codex 用の hook は専用スクリプトを持たず、`hooks/scripts/` にある Claude Code と共用の同名スクリプトをそのまま使う。`install.sh --codex` を実行すると、これらのスクリプトへの symlink が `.codex/hooks/` 配下に作成される。
