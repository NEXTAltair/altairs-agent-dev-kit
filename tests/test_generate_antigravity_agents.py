"""generate_antigravity_agents.py のテスト。

agents/*.md → antigravity/agents/*.md 生成の仕様:
- frontmatter は name / description / tools (YAML list) / subagent / mainAgent / model
- tools は Antigravity の組み込みツール名へ対応づけ、対応の無い名前は出力しない
  (未知のツール名は subagent を停止させる既知の問題がある)
- 語彙置換はフレーズ "Claude Code" → "Antigravity" のみ
- --check で生成結果と実ファイルの drift を検出
"""

import sys
from pathlib import Path

import pytest

KIT = Path(__file__).parent.parent
sys.path.insert(0, str(KIT / "scripts"))

from generate_antigravity_agents import (  # noqa: E402
    TOOL_MAP,
    GenerationError,
    generate_all,
    map_tools,
    parse_agent_md,
    render,
)

SAMPLE = """---
name: sample-agent
description: サンプル: テスト用 "引用" を含む。
color: blue
tools: Read, Bash, TaskList, SendMessage
---

## Role

You are a sample agent for Claude Code. Never leak Claude API keys.
"""

# https://antigravity.google/docs/hooks の組み込みツール一覧 (2026-11-12 確認)
KNOWN_TOOLS = {
    "view_file", "write_to_file", "replace_file_content", "multi_replace_file_content", "list_dir",
    "find_by_name", "grep_search", "search_web", "read_url_content", "run_command", "manage_task",
    "schedule", "list_permissions", "ask_permission", "invoke_subagent", "define_subagent",
    "send_message", "manage_subagents", "ask_question", "generate_image",
}


def test_tool_map_only_emits_documented_tool_names():
    assert {tool for targets in TOOL_MAP.values() for tool in targets} <= KNOWN_TOOLS


def test_unmapped_tools_are_dropped_and_order_is_stable():
    assert map_tools("Read, Bash, TaskList, SendMessage, Read") == [
        "view_file", "list_dir", "run_command", "send_message"]


def test_render_frontmatter_and_body():
    fields, body = parse_agent_md(SAMPLE)
    text = render(fields, body)
    head, _, rest = text.removeprefix("---\n").partition("\n---\n")
    assert head.splitlines() == [
        "name: sample-agent",
        'description: "サンプル: テスト用 \\"引用\\" を含む。"',
        "tools:",
        "  - view_file",
        "  - list_dir",
        "  - run_command",
        "  - send_message",
        "subagent: true",
        "mainAgent: false",
        "model: inherit",
    ]
    assert "color" not in head
    assert "sample agent for Antigravity. Never leak Claude API keys." in rest
    assert text.endswith("\n") and not text.endswith("\n\n")


def test_missing_frontmatter_fields_are_rejected():
    with pytest.raises(GenerationError):
        parse_agent_md("no frontmatter\n")
    with pytest.raises(GenerationError):
        parse_agent_md("---\nname: x\n---\nbody\n")


def test_check_detects_drift_missing_and_orphan(tmp_path):
    agents = tmp_path / "agents"
    out = tmp_path / "out"
    agents.mkdir()
    (agents / "sample-agent.md").write_text(SAMPLE, encoding="utf-8")

    assert generate_all(agents, out, check=True) == ["sample-agent.md: 未生成"]
    assert generate_all(agents, out, check=False) == []
    assert generate_all(agents, out, check=True) == []

    (out / "sample-agent.md").write_text("edited\n", encoding="utf-8")
    (out / "orphan.md").write_text("x\n", encoding="utf-8")
    drift = generate_all(agents, out, check=True)
    assert any("drift" in line for line in drift) and any("orphan" in line for line in drift)


def test_name_must_match_filename(tmp_path):
    agents = tmp_path / "agents"
    agents.mkdir()
    (agents / "other.md").write_text(SAMPLE, encoding="utf-8")
    with pytest.raises(GenerationError):
        generate_all(agents, tmp_path / "out", check=True)


def test_committed_output_is_current():
    assert generate_all(KIT / "agents", KIT / "antigravity" / "agents", check=True) == []
