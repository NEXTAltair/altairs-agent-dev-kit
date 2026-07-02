import subprocess
from pathlib import Path

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


def test_existing_file_not_overwritten(tmp_path):
    rules = tmp_path / ".claude" / "rules"
    rules.mkdir(parents=True)
    (rules / "git-workflow.md").write_text("custom", encoding="utf-8")
    result = run_install(tmp_path, "--rules")
    assert result.returncode == 0
    assert (rules / "git-workflow.md").read_text(encoding="utf-8") == "custom"
    assert "SKIP" in result.stdout
