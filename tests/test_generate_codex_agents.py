"""generate_codex_agents.py のテスト。

agents/*.md → codex/agents/*.toml 生成の仕様:
- frontmatter の name/description と本文を toml (description / developer_instructions / name) に変換
- 語彙置換はフレーズ "Claude Code" → "Codex" のみ (裸の Claude / Anthropic は置換しない)
- library-research は Codex 対象外 (Web ツール前提のため)
- 出力は LF・リテラル複数行文字列 (''') に正規化
- --check で生成結果と実ファイルの drift を検出
"""

import sys
import tomllib
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

from generate_codex_agents import (
    GenerationError,
    generate_all,
    parse_agent_md,
    render_toml,
    transform_body,
)

SAMPLE_MD = """---
name: sample-agent
description: サンプルエージェント。テスト用。
color: blue
tools: Read, Bash
---

## Role

You are a sample agent for Claude Code直接接続 testing.

Never leak:
- Anthropic/Claude API keys
"""


def write_agent(agents_dir: Path, stem: str, text: str = SAMPLE_MD) -> Path:
    agents_dir.mkdir(parents=True, exist_ok=True)
    text = text.replace("name: sample-agent", f"name: {stem}")
    path = agents_dir / f"{stem}.md"
    path.write_text(text, encoding="utf-8")
    return path


class TestParseAgentMd:
    def test_parses_frontmatter_and_body(self):
        name, description, body = parse_agent_md(SAMPLE_MD)
        assert name == "sample-agent"
        assert description == "サンプルエージェント。テスト用。"
        assert body.startswith("## Role")
        assert "---" not in body.split("\n")[0]

    def test_missing_name_raises(self):
        broken = SAMPLE_MD.replace("name: sample-agent\n", "")
        with pytest.raises(GenerationError):
            parse_agent_md(broken)


class TestTransformBody:
    def test_claude_code_phrase_becomes_codex(self):
        assert transform_body("ローカル作業メモリ (Claude Code直接接続)") == "ローカル作業メモリ (Codex直接接続)"

    def test_bare_claude_is_preserved(self):
        # 旧 sed はこれを "Anthropic/Codex API keys" に壊していた
        assert transform_body("- Anthropic/Claude API keys") == "- Anthropic/Claude API keys"

    def test_dot_claude_paths_preserved(self):
        assert transform_body("read `.claude/rules/git-workflow.md`") == "read `.claude/rules/git-workflow.md`"


class TestRenderToml:
    def test_output_is_valid_toml_with_expected_keys(self):
        out = render_toml("sample-agent", "desc with \"quotes\"", "body line\n")
        data = tomllib.loads(out)
        assert data["name"] == "sample-agent"
        assert data["description"] == 'desc with "quotes"'
        assert data["developer_instructions"] == "body line\n"

    def test_output_has_no_crlf(self):
        out = render_toml("a", "d", "line1\nline2\n")
        assert "\r" not in out

    def test_triple_single_quote_in_body_raises(self):
        with pytest.raises(GenerationError):
            render_toml("a", "d", "bad ''' body")


class TestGenerateAll:
    def test_generates_toml_per_agent(self, tmp_path):
        agents = tmp_path / "agents"
        out = tmp_path / "codex" / "agents"
        write_agent(agents, "alpha")
        write_agent(agents, "beta")
        drift = generate_all(agents, out, check=False)
        assert drift == []
        assert (out / "alpha.toml").exists()
        assert (out / "beta.toml").exists()
        data = tomllib.loads((out / "alpha.toml").read_text(encoding="utf-8"))
        assert "Codex直接接続" in data["developer_instructions"]
        assert "Anthropic/Claude API keys" in data["developer_instructions"]

    def test_skips_library_research(self, tmp_path):
        agents = tmp_path / "agents"
        out = tmp_path / "codex" / "agents"
        write_agent(agents, "library-research")
        generate_all(agents, out, check=False)
        assert not (out / "library-research.toml").exists()

    def test_check_passes_when_synced(self, tmp_path):
        agents = tmp_path / "agents"
        out = tmp_path / "codex" / "agents"
        write_agent(agents, "alpha")
        generate_all(agents, out, check=False)
        assert generate_all(agents, out, check=True) == []

    def test_check_detects_drift(self, tmp_path):
        agents = tmp_path / "agents"
        out = tmp_path / "codex" / "agents"
        write_agent(agents, "alpha")
        generate_all(agents, out, check=False)
        toml_path = out / "alpha.toml"
        toml_path.write_text(toml_path.read_text(encoding="utf-8") + "\n# drift\n", encoding="utf-8")
        drift = generate_all(agents, out, check=True)
        assert any("alpha.toml" in d for d in drift)

    def test_check_detects_orphan_toml(self, tmp_path):
        agents = tmp_path / "agents"
        out = tmp_path / "codex" / "agents"
        write_agent(agents, "alpha")
        generate_all(agents, out, check=False)
        (out / "ghost.toml").write_text('name = "ghost"\n', encoding="utf-8")
        drift = generate_all(agents, out, check=True)
        assert any("ghost.toml" in d for d in drift)

    def test_name_dir_mismatch_raises(self, tmp_path):
        agents = tmp_path / "agents"
        out = tmp_path / "codex" / "agents"
        path = write_agent(agents, "alpha")
        path.write_text(SAMPLE_MD.replace("name: sample-agent", "name: not-alpha"), encoding="utf-8")
        with pytest.raises(GenerationError):
            generate_all(agents, out, check=False)


class TestRealRepo:
    def test_repo_agents_generate_valid_toml(self, tmp_path):
        """実リポジトリの agents/ 全部が valid な toml を生成できる。"""
        repo = Path(__file__).parent.parent
        out = tmp_path / "out"
        drift = generate_all(repo / "agents", out, check=False)
        assert drift == []
        tomls = sorted(p.name for p in out.glob("*.toml"))
        assert "library-research.toml" not in tomls
        assert len(tomls) == len(list((repo / "agents").glob("*.md"))) - 1
        for p in out.glob("*.toml"):
            tomllib.loads(p.read_text(encoding="utf-8"))
