#!/usr/bin/env python3
"""skills-lock.json の非ポータブルな source を検出する lint。

発端: pin 済み skill に対しうっかり `npx skills add <ローカル絶対パス> --skill X` を
実行すると、lock エントリが黙って `sourceType: github` (ref pin) から
`sourceType: local` + 絶対パスに書き換わり、pin とポータビリティが壊れる事故が起きた。
絶対パス source は別マシン / CI で解決できず lock を移植不能にするため、これを検出する。

consumer が pre-commit / CI に組み込んで使うことを想定した lint (kit 自身は
skills-lock.json を持たないため、対象が無ければ何もせず成功する)。
"""

import argparse
import json
import re
import sys
from pathlib import Path

# 絶対パス: POSIX (/...) または Windows ドライブ (C:\ / C:/)
_ABS_PATH = re.compile(r"^(/|[A-Za-z]:[\\/])")


def load_lock(path: Path) -> dict:
    try:
        with path.open(encoding="utf-8") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return {}


def find_violations(lock: dict) -> list[str]:
    violations: list[str] = []
    skills = lock.get("skills", {})
    if not isinstance(skills, dict):
        return violations
    for name, entry in sorted(skills.items()):
        source = (entry or {}).get("source", "")
        if isinstance(source, str) and _ABS_PATH.match(source):
            source_type = (entry or {}).get("sourceType", "?")
            violations.append(
                f"VIOLATION: {name}: 絶対パス source は非ポータブル "
                f"(sourceType={source_type}, source={source})。"
                f"released skill は github@ref を pin する"
            )
    return violations


def main() -> int:
    parser = argparse.ArgumentParser(description="skills-lock.json の非ポータブル source lint")
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--lock", type=Path, default=None,
                        help="skills-lock.json のパス (既定: <root>/skills-lock.json)")
    args = parser.parse_args()
    lock_path = args.lock if args.lock else args.root.resolve() / "skills-lock.json"
    if not lock_path.exists():
        print(f"OK: {lock_path} が無いため検査対象なし")
        return 0
    violations = find_violations(load_lock(lock_path))
    for line in violations:
        print(line)
    if violations:
        print(
            f"\n{len(violations)} 件の非ポータブル source を検出。"
            f"github@ref に切り替えるか絶対パスを排除してください",
            file=sys.stderr,
        )
        return 1
    print("OK: skills-lock.json に非ポータブルな絶対パス source なし")
    return 0


if __name__ == "__main__":
    sys.exit(main())
