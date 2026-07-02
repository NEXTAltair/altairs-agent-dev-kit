# Codex hooks

Codex 用の hook は専用スクリプトを持たず、`install.sh --hooks` で `<target>/.claude/hooks/` に
導入される Claude Code と共用の同名スクリプト (`hook_*.py`) をそのまま使う。

`.codex` 側の hook 設定 (hooks.json 相当) では、symlink を経由せず
`<target>/.claude/hooks/hook_*.py` を直接パスで参照する。
