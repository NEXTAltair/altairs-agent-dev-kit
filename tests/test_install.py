import json
import os
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
        ["bash", str(KIT / "install.sh"), "--target", str(tmp_path), "--skills", "--skill-source", str(KIT)],
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

    # Restore an installer-owned dangling link without --force.
    shutil.rmtree(agents_skills / "check-existing")
    restored = subprocess.run(result.args, capture_output=True, text=True, timeout=180)
    assert restored.returncode == 0, restored.stderr
    assert (claude_skills / "check-existing/SKILL.md").is_file()

    protected = agents_skills / "check-existing/SKILL.md"
    original = protected.read_text(encoding="utf-8")
    protected.write_text(original + "\nLOCAL_EDIT_SENTINEL\n", encoding="utf-8")
    own = agents_skills / "consumer-own"
    own.mkdir()
    (own / "SKILL.md").write_text("canonical consumer skill", encoding="utf-8")
    own_claude = claude_skills / "consumer-own"
    own_claude.mkdir()
    (own_claude / "SKILL.md").write_text("independent consumer skill", encoding="utf-8")
    lock_path = tmp_path / "skills-lock.json"
    lock = json.loads(lock_path.read_text(encoding="utf-8"))
    lock["skills"]["check-existing"].update(sourceType="github", source="owner/pinned", ref="v1")
    lock_path.write_text(json.dumps(lock), encoding="utf-8")
    before_lock = lock_path.read_bytes()
    # A retry repairs links even when canonical content has local edits and a different pin.
    (claude_skills / "check-existing").unlink()
    again = subprocess.run(result.args, capture_output=True, text=True, timeout=180)
    assert again.returncode == 0, again.stderr
    assert "LOCAL_EDIT_SENTINEL" in protected.read_text(encoding="utf-8")
    assert lock_path.read_bytes() == before_lock
    assert (claude_skills / "check-existing").resolve() == agents_skills / "check-existing"
    assert (claude_skills / "check-existing/SKILL.md").is_file()
    assert not own_claude.is_symlink()
    assert (own_claude / "SKILL.md").read_text(encoding="utf-8") == "independent consumer skill"
    # A fresh checkout may have only a tracked pin, with both skill locations absent.
    lock = json.loads(lock_path.read_text(encoding="utf-8"))
    lock["skills"]["check-existing"].update(sourceType="github", source="owner/pinned", ref="v1")
    lock_path.write_text(json.dumps(lock), encoding="utf-8")
    pinned = lock_path.read_bytes()
    (claude_skills / "check-existing").unlink()
    shutil.rmtree(agents_skills / "check-existing")
    refused = subprocess.run(result.args, capture_output=True, text=True, timeout=180)
    assert refused.returncode != 0
    assert "pin" in refused.stderr
    assert lock_path.read_bytes() == pinned
    assert not (agents_skills / "check-existing").exists()
    forced = subprocess.run([*result.args, "--force"], capture_output=True, text=True, timeout=180)
    assert forced.returncode == 0, forced.stderr
    assert protected.read_text(encoding="utf-8") == original
    assert not own_claude.is_symlink()
    assert (own_claude / "SKILL.md").read_text(encoding="utf-8") == "independent consumer skill"


def test_existing_file_not_overwritten(tmp_path):
    rules = tmp_path / ".claude" / "rules"
    rules.mkdir(parents=True)
    (rules / "git-workflow.md").write_text("custom", encoding="utf-8")
    result = run_install(tmp_path, "--rules")
    assert result.returncode == 0
    assert (rules / "git-workflow.md").read_text(encoding="utf-8") == "custom"
    assert "SKIP" in result.stdout


@pytest.mark.parametrize("origin", ["https://github.com/example/kit.git", "git@github.com:example/kit.git"])
def test_skill_source_defaults_to_exact_release_tag(tmp_path, monkeypatch, origin):
    kit = tmp_path / "source"
    kit.mkdir()
    shutil.copyfile(KIT / "install.sh", kit / "install.sh")
    for name in ("one", "two"):
        skill = kit / "skills" / name
        skill.mkdir(parents=True)
        (skill / "SKILL.md").write_text(f"---\nname: {name}\ndescription: test\n---\n", encoding="utf-8")

    def git(*args):
        subprocess.run(["git", "-C", str(kit), *args], check=True, capture_output=True)

    git("init")
    git("add", ".")
    git("-c", "user.name=Test", "-c", "user.email=test@example.com", "commit", "-m", "release")
    git("remote", "add", "origin", origin)
    git("tag", "v9.8.7")
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    npx = bin_dir / "npx"
    npx.write_text(
        "#!/usr/bin/env python3\nimport json,os,sys\nfrom pathlib import Path\n"
        "if os.environ.get('FAKE_NPX_FAIL'): sys.exit('source unavailable')\n"
        "args=sys.argv[1:]\nPath('npx-call.json').write_text(json.dumps(args))\n"
        "for name in args[args.index('--skill')+1:args.index('--agent')]:\n"
        " p=Path('.agents/skills')/name\n p.mkdir(parents=True)\n (p/'SKILL.md').write_text(name)\n",
        encoding="utf-8",
    )
    npx.chmod(0o755)
    monkeypatch.setenv("PATH", str(bin_dir) + os.pathsep + os.environ["PATH"])
    target = tmp_path / "target"
    target.mkdir()
    result = subprocess.run(
        ["bash", str(kit / "install.sh"), "--target", str(target), "--skills"],
        capture_output=True, text=True, timeout=30,
    )
    assert result.returncode == 0, result.stderr
    args = json.loads((target / "npx-call.json").read_text())
    assert args[args.index("add") + 1] == "github:example/kit#v9.8.7"
    assert args[args.index("--skill") + 1:args.index("--agent")] == ["one", "two"]
    # Untagged source must not silently become a local/unpinned dependency.
    git("-c", "user.name=Test", "-c", "user.email=test@example.com", "commit", "--allow-empty", "-m", "unreleased")
    unpublished = tmp_path / "unpublished"
    unpublished.mkdir()
    (kit / "rules").mkdir()
    (kit / "rules/test.md").write_text("replacement")
    existing = unpublished / ".claude/rules/test.md"
    existing.parent.mkdir(parents=True)
    existing.write_text("consumer rule")
    result = subprocess.run(
        ["bash", str(kit / "install.sh"), "--target", str(unpublished), "--all", "--force"],
        capture_output=True, text=True, timeout=30,
    )
    assert result.returncode != 0
    assert "--skill-source" in result.stderr
    assert not (unpublished / "npx-call.json").exists()
    assert existing.read_text() == "consumer rule"
    assert not (unpublished / ".agent-kit").exists()
    assert not (unpublished / ".codex").exists()
    # An invalid explicit override must fail at the same preflight boundary.
    for bad_source in (str(tmp_path / "missing"), "github:example/kit", "https://bad.invalid/kit", "github:example/kit#bad~ref") :
        invalid = subprocess.run(
            [*result.args, "--skill-source", bad_source],
            capture_output=True, text=True, timeout=30,
        )
        assert invalid.returncode != 0
        assert "--skill-source" in invalid.stderr
        assert existing.read_text() == "consumer rule"
        assert not (unpublished / ".agent-kit").exists()
        assert not (unpublished / ".codex").exists()
        assert not (unpublished / "npx-call.json").exists()
    monkeypatch.setenv("FAKE_NPX_FAIL", "1")
    unavailable = subprocess.run(
        [*result.args, "--skill-source", "github:example/kit#valid-but-unavailable"],
        capture_output=True, text=True, timeout=30,
    )
    assert unavailable.returncode != 0
    assert "source unavailable" in unavailable.stderr
    assert existing.read_text() == "consumer rule"
    assert not (unpublished / ".agent-kit").exists()
    assert not (unpublished / ".codex").exists()


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
