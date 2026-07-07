import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

KIT = Path(__file__).parent.parent


def run_install(target: Path, *flags: str) -> subprocess.CompletedProcess:
    return subprocess.run(["bash", str(KIT / "install.sh"), "--target", str(target), *flags],
                          capture_output=True, text=True, timeout=30)


def test_install_rules_and_agents(tmp_path):
    result = run_install(tmp_path, "--rules", "--agents")
    assert result.returncode == 0, result.stderr
    assert (tmp_path / ".claude" / "rules" / "git-workflow.md").exists()
    assert list((tmp_path / ".claude" / "agents").glob("*.md"))


def test_install_hooks_prints_wiring(tmp_path):
    result = run_install(tmp_path, "--hooks")
    assert result.returncode == 0, result.stderr
    assert (tmp_path / ".claude" / "hooks" / "hook_pre_commands.py").exists()
    assert "hooks" in result.stdout  # hooks.json 断片が表示される


def test_install_hooks_wiring_uses_flat_install_paths(tmp_path):
    # install.sh --hooks が表示する配線 JSON は、プラグイン経路の
    # ${CLAUDE_PLUGIN_ROOT}/hooks/scripts/... ではなく、実際にコピーされた
    # <target>/.claude/hooks/hook_*.py の絶対パスを指していなければならない。
    result = run_install(tmp_path, "--hooks")
    assert result.returncode == 0, result.stderr
    assert "CLAUDE_PLUGIN_ROOT" not in result.stdout
    assert "/hooks/scripts/" not in result.stdout

    json_start = result.stdout.index("{")
    json_end = result.stdout.rindex("}") + 1
    payload = json.loads(result.stdout[json_start:json_end])
    hook_paths = [
        "".join(h["command"].split('"')[1:])  # quoted target + unquoted /.claude/hooks/... suffix
        for entries in payload["hooks"].values()
        for entry in entries
        for h in entry["hooks"]
    ]
    assert hook_paths
    for path in hook_paths:
        assert Path(path).exists(), path


def test_install_skills_requires_npx(tmp_path, monkeypatch):
    # --skills は skills.sh CLI (npx skills) に委譲する。npx (Node.js) が無い環境では
    # 黙ってフォールバックせず、明確なエラーメッセージ付きで exit 1 する。
    result = subprocess.run(
        ["bash", str(KIT / "install.sh"), "--target", str(tmp_path), "--skills"],
        capture_output=True, text=True, timeout=30,
        env={"PATH": "/usr/bin:/bin"},
    )
    assert result.returncode == 1
    assert "Node" in result.stderr


@pytest.mark.skipif(shutil.which("npx") is None, reason="skills.sh CLI (npx/Node.js) が必要")
def test_install_skills_canonical_layout(tmp_path):
    # install.sh --skills は canonical レイアウトを生成する:
    #   .agents/skills/<name>  = 実体 (Codex/Copilot/OpenCode 共有 canonical dir)
    #   .claude/skills/<name>  = ../../.agents/skills/<name> への symlink (Claude Code 用)
    # これは validate_harness 等が期待する構成 (.claude/skills は symlink) と一致する。
    result = subprocess.run(
        ["bash", str(KIT / "install.sh"), "--target", str(tmp_path), "--skills"],
        capture_output=True, text=True, timeout=180,
    )
    assert result.returncode == 0, result.stderr

    agents_skills = tmp_path / ".agents" / "skills"
    claude_skills = tmp_path / ".claude" / "skills"
    real_skills = [d for d in agents_skills.iterdir() if (d / "SKILL.md").exists()]
    assert real_skills, "no skills installed under .agents/skills"

    for skill_dir in real_skills:
        assert not skill_dir.is_symlink(), f"{skill_dir} は実体であるべき"
        link = claude_skills / skill_dir.name
        assert link.is_symlink(), f"{link} は symlink であるべき"
        assert link.resolve() == skill_dir.resolve(), f"{link} は {skill_dir} を指すべき"
        assert (link / "SKILL.md").exists(), "symlink 越しに SKILL.md が解決するべき"


def test_existing_file_not_overwritten(tmp_path):
    rules = tmp_path / ".claude" / "rules"
    rules.mkdir(parents=True)
    (rules / "git-workflow.md").write_text("custom", encoding="utf-8")
    result = run_install(tmp_path, "--rules")
    assert result.returncode == 0
    assert (rules / "git-workflow.md").read_text(encoding="utf-8") == "custom"
    assert "SKIP" in result.stdout


def test_empty_source_glob_does_not_crash(tmp_path):
    # rules が空でも --rules がクラッシュせず正常終了する (nullglob)
    import shutil
    kit_copy = tmp_path / "kit"
    shutil.copytree(KIT, kit_copy, ignore=shutil.ignore_patterns(".git", ".venv", "rules"))
    (kit_copy / "rules").mkdir()
    target = tmp_path / "target"
    target.mkdir()
    result = subprocess.run(
        ["bash", str(kit_copy / "install.sh"), "--target", str(target), "--rules"],
        capture_output=True, text=True, timeout=30
    )
    assert result.returncode == 0, result.stderr
    assert "DONE" in result.stdout


def test_codex_target_with_ampersand(tmp_path):
    # --codex で特殊文字を含むパスが正しく処理される
    target = tmp_path / "a&b"
    target.mkdir()
    result = run_install(target, "--codex")
    assert result.returncode == 0, result.stderr
    config = (target / ".codex" / "config.toml").read_text(encoding="utf-8")
    assert str(target) in config
    assert "{{PROJECT_ROOT}}" not in config


def test_installed_hooks_flat_layout_resolves_default_rules(tmp_path):
    # install.sh --hooks はスクリプトを <target>/.claude/hooks/*.py に、
    # default rules を <target>/.claude/hooks/rules/*.default.json にフラット配置する。
    # この配置で hook_pre_commands.py を実行すると default の
    # git reset --hard ブロックが有効に解決される (permissionDecision=deny) ことを確認する。
    result = run_install(tmp_path, "--hooks")
    assert result.returncode == 0, result.stderr

    hook = tmp_path / ".claude" / "hooks" / "hook_pre_commands.py"
    assert hook.exists()

    payload = json.dumps({"tool_name": "Bash", "tool_input": {"command": "git reset --hard HEAD~1"}})
    proc = subprocess.run(
        [sys.executable, str(hook)],
        input=payload,
        capture_output=True,
        text=True,
        timeout=10,
        env={"CLAUDE_PROJECT_DIR": str(tmp_path), "PATH": "/usr/bin:/bin"},
    )
    assert proc.returncode == 0, proc.stderr
    output = json.loads(proc.stdout)["hookSpecificOutput"]
    assert output["permissionDecision"] == "deny"
    assert "危険" in output["permissionDecisionReason"]


def test_flat_layout_defaults_survive_rules_dir(tmp_path):
    # --rules と --hooks を両方導入すると .claude/rules/ (markdown) が存在する。
    # このディレクトリが default rules dir (.claude/hooks/rules/) を隠蔽して
    # kit デフォルトの git 破壊系ブロックが無効化される回帰を検出する (issue #24)。
    result = run_install(tmp_path, "--rules", "--hooks")
    assert result.returncode == 0, result.stderr
    assert (tmp_path / ".claude" / "rules" / "git-workflow.md").exists()

    hook = tmp_path / ".claude" / "hooks" / "hook_pre_commands.py"
    payload = json.dumps({"tool_name": "Bash", "tool_input": {"command": "git reset --hard HEAD~1"}})
    proc = subprocess.run(
        [sys.executable, str(hook)],
        input=payload,
        capture_output=True,
        text=True,
        timeout=10,
        env={"CLAUDE_PROJECT_DIR": str(tmp_path), "PATH": "/usr/bin:/bin"},
    )
    assert proc.returncode == 0, proc.stderr
    output = json.loads(proc.stdout)["hookSpecificOutput"]
    assert output["permissionDecision"] == "deny"
    assert "危険" in output["permissionDecisionReason"]
