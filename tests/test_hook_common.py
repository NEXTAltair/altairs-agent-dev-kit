import json
import os
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "hooks" / "scripts"))
import hook_common


def test_find_project_root_env(monkeypatch, tmp_path):
    monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(tmp_path))
    assert hook_common.find_project_root() == tmp_path


def test_find_project_root_git(monkeypatch, tmp_path):
    monkeypatch.delenv("CLAUDE_PROJECT_DIR", raising=False)
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    monkeypatch.chdir(tmp_path)
    assert hook_common.find_project_root() == tmp_path.resolve()


def test_deep_merge_lists_concat_and_scalar_override():
    base = {"blocked": [{"pattern": "a"}], "flag": 1, "nested": {"x": 1, "y": 2}}
    override = {"blocked": [{"pattern": "b"}], "flag": 2, "nested": {"y": 9}}
    merged = hook_common.deep_merge(base, override)
    assert [r["pattern"] for r in merged["blocked"]] == ["a", "b"]
    assert merged["flag"] == 2
    assert merged["nested"] == {"x": 1, "y": 9}
    assert base["blocked"] == [{"pattern": "a"}]  # 非破壊


def test_load_hook_rules_default_plus_override(tmp_path, monkeypatch):
    # default 側: スクリプト隣接の rules ディレクトリを monkeypatch で差し替え
    default_dir = tmp_path / "defaults"
    default_dir.mkdir()
    (default_dir / "pre_commands.default.json").write_text(
        json.dumps({"blocked_commands": [{"pattern": "^rm -rf"}]}), encoding="utf-8"
    )
    monkeypatch.setattr(hook_common, "DEFAULT_RULES_DIR", default_dir)
    # override 側: project の .claude/hooks/rules/
    proj = tmp_path / "proj"
    ov_dir = proj / ".claude" / "hooks" / "rules"
    ov_dir.mkdir(parents=True)
    (ov_dir / "pre_commands.json").write_text(
        json.dumps({"blocked_commands": [{"pattern": "^pip "}]}), encoding="utf-8"
    )
    rules = hook_common.load_hook_rules("pre_commands", proj)
    patterns = [r["pattern"] for r in rules["blocked_commands"]]
    assert patterns == ["^rm -rf", "^pip "]


def test_load_hook_rules_missing_files(tmp_path, monkeypatch):
    monkeypatch.setattr(hook_common, "DEFAULT_RULES_DIR", tmp_path / "none")
    assert hook_common.load_hook_rules("pre_commands", tmp_path) == {}
