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
    assert (tmp_path / ".agent-kit/hooks.lock.json").exists()
    assert "hooks" in result.stdout  # hooks.json 断片が表示される


def test_install_hooks_wiring_uses_standalone_bootstrap(tmp_path):
    result = run_install(tmp_path, "--hooks")
    assert result.returncode == 0, result.stderr
    assert "CLAUDE_PLUGIN_ROOT" not in result.stdout
    assert "/hooks/scripts/" not in result.stdout

    json_start = result.stdout.index("{")
    json_end = result.stdout.rindex("}") + 1
    payload = json.loads(result.stdout[json_start:json_end])
    commands = [
        h["args"]
        for entries in payload["hooks"].values()
        for entry in entries
        for h in entry["hooks"]
    ]
    assert commands
    for args in commands:
        assert args[:4] == ["-I", "-X", "utf8", "-c"]
    lock = json.loads((tmp_path / ".agent-kit/hooks.lock.json").read_text())
    for name in lock["files"]:
        assert (tmp_path / ".agent-kit/runtimes" / lock["runtime"] / name).is_file()


def test_install_skills_requires_npx(tmp_path):
    # --skills は skills.sh CLI (npx skills) に委譲する。npx (Node.js) が無い環境では
    # 黙ってフォールバックせず、明確なエラーメッセージ付きで exit 1 する。
    # /usr/bin may itself contain npx. Expose only the installer's prerequisite.
    isolated_bin = tmp_path / "bin"
    isolated_bin.mkdir()
    (isolated_bin / "dirname").symlink_to(shutil.which("dirname"))
    result = subprocess.run(
        [shutil.which("bash"), str(KIT / "install.sh"), "--target", str(tmp_path), "--skills"],
        capture_output=True, text=True, timeout=30,
        env={"PATH": str(isolated_bin)},
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


def test_installed_hooks_resolve_pinned_default_rules(tmp_path):
    subprocess.run(["git", "init", str(tmp_path)], check=True, capture_output=True)
    result = run_install(tmp_path, "--hooks")
    assert result.returncode == 0, result.stderr

    wiring = json.loads(result.stdout[result.stdout.index("{"):result.stdout.rindex("}") + 1])
    args = wiring["hooks"]["PreToolUse"][0]["hooks"][0]["args"]

    payload = json.dumps({"tool_name": "Bash", "tool_input": {"command": "git reset --hard HEAD~1"}})
    proc = subprocess.run(
        [sys.executable, *args],
        cwd=tmp_path,
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
    subprocess.run(["git", "init", str(tmp_path)], check=True, capture_output=True)
    result = run_install(tmp_path, "--rules", "--hooks")
    assert result.returncode == 0, result.stderr
    assert (tmp_path / ".claude" / "rules" / "git-workflow.md").exists()

    wiring = json.loads(result.stdout[result.stdout.index("{"):result.stdout.rindex("}") + 1])
    args = wiring["hooks"]["PreToolUse"][0]["hooks"][0]["args"]
    payload = json.dumps({"tool_name": "Bash", "tool_input": {"command": "git reset --hard HEAD~1"}})
    proc = subprocess.run(
        [sys.executable, *args],
        cwd=tmp_path,
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
