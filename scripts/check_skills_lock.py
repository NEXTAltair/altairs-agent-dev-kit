#!/usr/bin/env python3
"""skills-lock.json の非ポータブルな source を検出する lint。

発端: pin 済み skill に対しうっかり `npx skills add <ローカル絶対パス> --skill X` を
実行すると、lock エントリが黙って `sourceType: github` (ref pin) から
`sourceType: local` + 絶対パスに書き換わり、pin とポータビリティが壊れる事故が起きた。
絶対パスや consumer 外への相対 local source は別マシン / CI で解決できず、
lock を移植不能にするため検出する。不正な JSON / entry 形式も成功扱いしない。

consumer が pre-commit / CI に組み込んで使うことを想定した lint (kit 自身は
skills-lock.json を持たないため、対象が無ければ何もせず成功する)。
"""

import argparse
import json
import re
import sys
from pathlib import Path, PureWindowsPath

# 絶対パス: POSIX (/...) または Windows ドライブ (C:\ / C:/)
_ABS_PATH = re.compile(r"^(/|[A-Za-z]:[\\/])")


def load_lock(path: Path) -> dict:
    with path.open(encoding="utf-8") as f:
        return json.load(f)


def find_violations(lock: dict, root: Path | None = None) -> list[str]:
    if not isinstance(lock, dict):
        return ["VIOLATION: lock は JSON object である必要があります"]
    if type(lock.get("version")) is not int or lock["version"] < 1:
        return ["VIOLATION: lock.version は正の整数である必要があります"]
    violations: list[str] = []
    skills = lock.get("skills")
    if not isinstance(skills, dict):
        return ["VIOLATION: lock.skills は JSON object である必要があります"]
    root = (root or Path.cwd()).resolve()
    for name, entry in sorted(skills.items()):
        if not isinstance(entry, dict):
            violations.append(f"VIOLATION: {name}: skill entry は JSON object である必要があります")
            continue
        source = entry.get("source")
        source_type = entry.get("sourceType")
        if not isinstance(source, str) or not source.strip() or "\x00" in source:
            violations.append(f"VIOLATION: {name}: source は空でないパス文字列である必要があります")
            continue
        if not isinstance(source_type, str) or not source_type.strip():
            violations.append(f"VIOLATION: {name}: sourceType は空でない文字列である必要があります")
            continue
        windows_path = PureWindowsPath(source)
        if _ABS_PATH.match(source) or windows_path.drive or windows_path.root:
            violations.append(
                f"VIOLATION: {name}: 絶対パス source は非ポータブル "
                f"(sourceType={source_type}, source={source})。"
                f"released skill は github@ref を pin する"
            )
        elif source_type == "local":
            try:
                # Interpret either OS's separator and resolve existing symlinks too.
                (root / source.replace("\\", "/")).resolve().relative_to(root)
            except (ValueError, OSError, RuntimeError):
                violations.append(
                    f"VIOLATION: {name}: consumer 外の local source は非ポータブル "
                    f"(source={source})。consumer 内の相対パスか github@ref を使用してください"
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
    try:
        violations = find_violations(load_lock(lock_path), args.root)
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        print(f"ERROR: {lock_path} を読み込めません: {error}", file=sys.stderr)
        return 1
    for line in violations:
        print(line)
    if violations:
        print(
            f"\n{len(violations)} 件の lock 違反を検出。"
            f"形式を修正し、source は github@ref または consumer 内の相対パスにしてください",
            file=sys.stderr,
        )
        return 1
    print("OK: skills-lock.json に非ポータブル source・形式違反なし")
    return 0


if __name__ == "__main__":
    sys.exit(main())
