#!/usr/bin/env python3
"""設定整合 lint: rules の約束 ⇔ settings.json ⇔ hook 実在の drift を検出する。

発端: settings.json の巻き戻り事故で env と hook 配線が消えたのに
rules は「設定済み」と書いたままになる drift が実際に起きたため。
"""

import argparse
import json
import shlex
import sys
from pathlib import Path


def load_json(path: Path) -> dict:
    try:
        with path.open(encoding="utf-8") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return {}


def iter_hook_commands(settings: dict):
    for entries in settings.get("hooks", {}).values():
        for entry in entries:
            for hook in entry.get("hooks", []):
                if hook.get("type") == "command":
                    yield hook.get("command", "") + " " + shlex.join(hook.get("args", []))


def main() -> int:
    parser = argparse.ArgumentParser(description="設定整合 lint")
    parser.add_argument("--root", type=Path, default=Path.cwd())
    args = parser.parse_args()
    root: Path = args.root.resolve()
    claude = root / ".claude"
    settings = load_json(claude / "settings.json")
    consistency = load_json(claude / "hooks" / "rules" / "consistency.json")
    violations: list[str] = []
    warnings: list[str] = []

    # (a) required_env
    env = settings.get("env", {})
    for key in consistency.get("required_env", []):
        if key not in env:
            violations.append(f"VIOLATION: settings.json env に {key} がない (required_env)")

    # (b)(c) hook 配線
    commands = list(iter_hook_commands(settings))
    wired_scripts: set[str] = set()
    for cmd in commands:
        # プラグイン配線 ("${CLAUDE_PLUGIN_ROOT}"/... 形式) も解決できるよう、
        # 既知の変数を root に展開してからパスを抽出する (kit 自身では plugin root == repo root)。
        for match in shlex.split(cmd):
            for var in (
                "${CLAUDE_PLUGIN_ROOT}",
                "$CLAUDE_PLUGIN_ROOT",
                "${CLAUDE_PROJECT_DIR}",
                "$CLAUDE_PROJECT_DIR",
            ):
                match = match.replace(var, str(root))
            if not match.endswith(".py"):
                continue
            script = Path(match)
            resolved = script if script.is_absolute() else root / script
            wired_scripts.add(resolved.name)
            if not resolved.exists():
                violations.append(f"VIOLATION: 配線された hook が実在しない: {match}")
    hooks_dir = claude / "hooks"
    if hooks_dir.is_dir():
        for script in sorted(hooks_dir.glob("*.py")):
            if script.name not in wired_scripts:
                warnings.append(f"WARNING: 未配線 hook: {script.name} (settings.json に登録なし)")

    for line in violations + warnings:
        print(line)
    if not violations and not warnings:
        print("OK: 設定整合に問題なし")
    return 1 if violations else 0


if __name__ == "__main__":
    sys.exit(main())
