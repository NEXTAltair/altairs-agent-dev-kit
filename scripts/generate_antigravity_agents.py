#!/usr/bin/env python3
"""agents/*.md から antigravity/agents/*.md を生成する。

Antigravity の custom subagent は Markdown + YAML frontmatter (name / description / tools / model 等)。
agents/*.md (Claude Code 形式) が単一ソースで、こちらは生成物であり手編集しない。

- tools は Antigravity の組み込みツール名へ対応づける。対応の無いツール (Task* 等) は落とす。
  未知のツール名を渡すと subagent が停止する既知の問題があるため、対応表に無い名前は出力しない。
- 語彙置換はハーネス名フレーズ "Claude Code" → "Antigravity" のみ。

Usage:
    python scripts/generate_antigravity_agents.py            # 再生成
    python scripts/generate_antigravity_agents.py --check    # drift 検出 (CI 用)
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent

PHRASE_MAP = (("Claude Code", "Antigravity"),)

# Claude Code のツール名 → Antigravity の組み込みツール名 (https://antigravity.google/docs/hooks の一覧)。
TOOL_MAP: dict[str, tuple[str, ...]] = {
    "Read": ("view_file", "list_dir"),
    "Grep": ("grep_search",),
    "Glob": ("find_by_name",),
    "Bash": ("run_command",),
    "Edit": ("replace_file_content", "multi_replace_file_content"),
    "Write": ("write_to_file",),
    "WebFetch": ("read_url_content",),
    "WebSearch": ("search_web",),
    "SendMessage": ("send_message",),
}


class GenerationError(Exception):
    """入力 md が生成契約を満たさない場合に送出する。"""


def parse_agent_md(text: str) -> tuple[dict[str, str], str]:
    if not text.startswith("---\n"):
        raise GenerationError("frontmatter がない (--- で始まらない)")
    try:
        _, fm, body = text.split("---\n", 2)
    except ValueError as exc:
        raise GenerationError("frontmatter が閉じていない") from exc
    fields: dict[str, str] = {}
    for line in fm.splitlines():
        if ":" in line and not line.startswith((" ", "\t")):
            key, _, value = line.partition(":")
            fields[key.strip()] = value.strip()
    for key in ("name", "description"):
        if not fields.get(key):
            raise GenerationError(f"frontmatter に {key} がない")
    return fields, body.lstrip("\n")


def map_tools(tools: str) -> list[str]:
    mapped: list[str] = []
    for tool in (item.strip() for item in tools.split(",")):
        for target in TOOL_MAP.get(tool, ()):
            if target not in mapped:
                mapped.append(target)
    return mapped


def render(fields: dict[str, str], body: str) -> str:
    for src, dst in PHRASE_MAP:
        body = body.replace(src, dst)
    lines = [
        "---",
        f"name: {fields['name']}",
        # JSON 文字列は YAML の double-quoted scalar として有効
        f"description: {json.dumps(fields['description'], ensure_ascii=False)}",
    ]
    tools = map_tools(fields.get("tools", ""))
    if tools:
        lines.append("tools:")
        lines.extend(f"  - {tool}" for tool in tools)
    lines += ["subagent: true", "mainAgent: false", "model: inherit", "---", ""]
    return "\n".join(lines) + body.rstrip() + "\n"


def generate_all(agents_dir: Path, out_dir: Path, *, check: bool) -> list[str]:
    drift: list[str] = []
    expected: dict[str, str] = {}
    for md_path in sorted(agents_dir.glob("*.md")):
        fields, body = parse_agent_md(md_path.read_text(encoding="utf-8"))
        if fields["name"] != md_path.stem:
            raise GenerationError(f"{md_path.name}: frontmatter name '{fields['name']}' がファイル名と不一致")
        expected[md_path.name] = render(fields, body)

    if check:
        for fname, content in expected.items():
            path = out_dir / fname
            if not path.exists():
                drift.append(f"{fname}: 未生成")
            elif path.read_text(encoding="utf-8") != content:
                drift.append(f"{fname}: agents/*.md と drift している (再生成が必要)")
    else:
        out_dir.mkdir(parents=True, exist_ok=True)
        for fname, content in expected.items():
            (out_dir / fname).write_text(content, encoding="utf-8", newline="\n")
    for path in sorted(out_dir.glob("*.md")):
        if path.name not in expected:
            drift.append(f"{path.name}: 対応する agents/*.md がない orphan")
    return drift


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="生成せず drift を検出する")
    parser.add_argument("--agents-dir", type=Path, default=REPO_ROOT / "agents")
    parser.add_argument("--out-dir", type=Path, default=REPO_ROOT / "antigravity" / "agents")
    args = parser.parse_args()
    try:
        drift = generate_all(args.agents_dir, args.out_dir, check=args.check)
    except GenerationError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    if drift:
        for line in drift:
            print(f"DRIFT: {line}", file=sys.stderr)
        print("antigravity/agents/*.md は生成物です。scripts/generate_antigravity_agents.py で再生成してください。",
              file=sys.stderr)
        return 1
    if not args.check:
        print(f"generated: {args.out_dir}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
