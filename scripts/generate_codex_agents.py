#!/usr/bin/env python3
"""agents/*.md から codex/agents/*.toml を生成する。

codex 側の agent 定義は agents/*.md が単一ソース。toml は生成物であり手編集しない。
語彙置換はハーネス名フレーズ "Claude Code" → "Codex" のみ。裸の "Claude" や
"Anthropic" は製品・API への言及なので置換しない (旧 sed はここを巻き添えにしていた)。

Usage:
    python scripts/generate_codex_agents.py            # 再生成
    python scripts/generate_codex_agents.py --check    # drift 検出 (CI 用、drift あれば exit 1)
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent

# Codex 対象外の agent。library-research は WebFetch/WebSearch 前提のため
# Codex 版を持たない (設計計画で agents x10 / codex x9 と確定済み)。
SKIP_AGENTS = {"library-research"}

# ハーネス名フレーズのみ置換する。順序が意味を持つ場合に備え tuple で保持。
PHRASE_MAP = (("Claude Code", "Codex"),)


class GenerationError(Exception):
    """入力 md が生成契約を満たさない場合に送出する。"""


def parse_agent_md(text: str) -> tuple[str, str, str]:
    """frontmatter から name/description を取り、本文を返す。"""
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

    name = fields.get("name", "")
    description = fields.get("description", "")
    if not name:
        raise GenerationError("frontmatter に name がない")
    if not description:
        raise GenerationError("frontmatter に description がない")
    return name, description, body.lstrip("\n")


def transform_body(body: str) -> str:
    for src, dst in PHRASE_MAP:
        body = body.replace(src, dst)
    return body


def render_toml(name: str, description: str, body: str) -> str:
    if "'''" in body:
        raise GenerationError(f"{name}: 本文に ''' が含まれ、リテラル文字列にできない")
    body = body.rstrip() + "\n"
    # description は JSON 互換エスケープで TOML basic string にする
    desc = json.dumps(description, ensure_ascii=False)
    return f"description = {desc}\ndeveloper_instructions = '''\n{body}'''\nname = {json.dumps(name, ensure_ascii=False)}\n"


def generate_all(agents_dir: Path, out_dir: Path, *, check: bool) -> list[str]:
    """生成または drift 検出。check=True では書き込まず差分メッセージを返す。"""
    drift: list[str] = []
    expected: dict[str, str] = {}

    for md_path in sorted(agents_dir.glob("*.md")):
        stem = md_path.stem
        if stem in SKIP_AGENTS:
            continue
        name, description, body = parse_agent_md(md_path.read_text(encoding="utf-8"))
        if name != stem:
            raise GenerationError(f"{md_path.name}: frontmatter name '{name}' がファイル名と不一致")
        expected[f"{stem}.toml"] = render_toml(name, description, transform_body(body))

    if check:
        for fname, content in expected.items():
            toml_path = out_dir / fname
            if not toml_path.exists():
                drift.append(f"{fname}: 未生成 (agents/{fname.removesuffix('.toml')}.md に対応する toml がない)")
            elif toml_path.read_text(encoding="utf-8") != content:
                drift.append(f"{fname}: agents/*.md と drift している (再生成が必要)")
        for toml_path in sorted(out_dir.glob("*.toml")):
            if toml_path.name not in expected:
                drift.append(f"{toml_path.name}: 対応する agents/*.md がない orphan")
        return drift

    out_dir.mkdir(parents=True, exist_ok=True)
    for fname, content in expected.items():
        (out_dir / fname).write_text(content, encoding="utf-8", newline="\n")
    for toml_path in sorted(out_dir.glob("*.toml")):
        if toml_path.name not in expected:
            drift.append(f"{toml_path.name}: 対応する agents/*.md がない orphan (手動で削除すること)")
    return drift


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="生成せず drift を検出する")
    parser.add_argument("--agents-dir", type=Path, default=REPO_ROOT / "agents")
    parser.add_argument("--out-dir", type=Path, default=REPO_ROOT / "codex" / "agents")
    args = parser.parse_args()

    try:
        drift = generate_all(args.agents_dir, args.out_dir, check=args.check)
    except GenerationError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    if drift:
        for line in drift:
            print(f"DRIFT: {line}", file=sys.stderr)
        if args.check:
            print("codex/agents/*.toml は生成物です。scripts/generate_codex_agents.py を実行して再生成してください。", file=sys.stderr)
        return 1

    if not args.check:
        print(f"generated: {args.out_dir}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
