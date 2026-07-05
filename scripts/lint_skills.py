#!/usr/bin/env python3
"""skills lint: SKILL.md の frontmatter 必須フィールドとディレクトリ名一致を検証。"""

import argparse
import re
import sys
from pathlib import Path


def parse_frontmatter(text: str) -> dict[str, str]:
    match = re.match(r"\A---\n(.*?)\n---\n", text, re.DOTALL)
    if not match:
        return {}
    fields: dict[str, str] = {}
    for line in match.group(1).splitlines():
        if ":" in line and not line.startswith((" ", "\t")):
            key, _, value = line.partition(":")
            fields[key.strip()] = value.strip()
    return fields


def find_duplicate_allowed_tools(text: str) -> list[str]:
    """frontmatter の allowed-tools リストに同一ツールが重複していたら返す。

    過去に一括置換で複数の MCP ツール名が同一ツールに潰され、重複が生まれた
    (監査 issue #4)。重複は置換ミスの兆候として lint で検出する。
    """
    match = re.match(r"\A---\n(.*?)\n---\n", text, re.DOTALL)
    if not match:
        return []
    seen: set[str] = set()
    dups: list[str] = []
    in_allowed = False
    for line in match.group(1).splitlines():
        if not line.startswith((" ", "\t", "-")) and ":" in line:
            in_allowed = line.partition(":")[0].strip() == "allowed-tools"
            continue
        if in_allowed:
            item = line.strip()
            if item.startswith("- "):
                tool = item[2:].strip()
                if tool in seen and tool not in dups:
                    dups.append(tool)
                seen.add(tool)
    return dups


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dir", type=Path, default=Path("skills"))
    args = parser.parse_args()
    errors: list[str] = []
    for skill_dir in sorted(p for p in args.dir.iterdir() if p.is_dir()):
        skill_md = skill_dir / "SKILL.md"
        if not skill_md.exists():
            errors.append(f"{skill_dir.name}: SKILL.md がない")
            continue
        text = skill_md.read_text(encoding="utf-8")
        fm = parse_frontmatter(text)
        if not fm.get("name"):
            errors.append(f"{skill_dir.name}: frontmatter に name がない")
        elif fm["name"] != skill_dir.name:
            errors.append(f"{skill_dir.name}: name '{fm['name']}' がディレクトリ名と不一致")
        if not fm.get("description"):
            errors.append(f"{skill_dir.name}: frontmatter に description がない")
        for tool in find_duplicate_allowed_tools(text):
            errors.append(f"{skill_dir.name}: allowed-tools に '{tool}' が重複 (置換ミスの疑い)")
    for e in errors:
        print(f"VIOLATION: {e}")
    if not errors:
        print("OK: 全 skill が有効")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
