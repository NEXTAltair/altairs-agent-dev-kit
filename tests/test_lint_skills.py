import subprocess
import sys
from pathlib import Path

SCRIPT = Path(__file__).parent.parent / "scripts" / "lint_skills.py"


def run(skills_dir: Path) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, str(SCRIPT), "--dir", str(skills_dir)],
                          capture_output=True, text=True, timeout=10)


def test_valid_skill_passes(tmp_path):
    d = tmp_path / "my-skill"
    d.mkdir()
    (d / "SKILL.md").write_text("---\nname: my-skill\ndescription: テスト\n---\n本文",
                                encoding="utf-8")
    assert run(tmp_path).returncode == 0


def test_name_mismatch_fails(tmp_path):
    d = tmp_path / "my-skill"
    d.mkdir()
    (d / "SKILL.md").write_text("---\nname: other\ndescription: x\n---\n", encoding="utf-8")
    result = run(tmp_path)
    assert result.returncode == 1
    assert "my-skill" in result.stdout


def test_missing_skill_md_fails(tmp_path):
    (tmp_path / "empty-skill").mkdir()
    assert run(tmp_path).returncode == 1


def test_duplicate_allowed_tools_fails(tmp_path):
    d = tmp_path / "dup-skill"
    d.mkdir()
    (d / "SKILL.md").write_text(
        "---\nname: dup-skill\ndescription: x\nallowed-tools:\n"
        "  - Grep\n  - Grep\n  - Read\n---\n本文",
        encoding="utf-8")
    result = run(tmp_path)
    assert result.returncode == 1
    assert "重複" in result.stdout


def test_unique_allowed_tools_passes(tmp_path):
    d = tmp_path / "ok-skill"
    d.mkdir()
    (d / "SKILL.md").write_text(
        "---\nname: ok-skill\ndescription: x\nallowed-tools:\n"
        "  - Grep\n  - Glob\n  - Read\n---\n本文",
        encoding="utf-8")
    assert run(tmp_path).returncode == 0


def test_version_key_forbidden(tmp_path):
    d = tmp_path / "ver-skill"
    d.mkdir()
    (d / "SKILL.md").write_text(
        '---\nname: ver-skill\nversion: "1.0.0"\ndescription: x\n---\n本文',
        encoding="utf-8")
    result = run(tmp_path)
    assert result.returncode == 1
    assert "禁止キー" in result.stdout


def test_unknown_key_rejected(tmp_path):
    d = tmp_path / "odd-skill"
    d.mkdir()
    (d / "SKILL.md").write_text(
        "---\nname: odd-skill\ndescription: x\ncolor: red\n---\n本文",
        encoding="utf-8")
    result = run(tmp_path)
    assert result.returncode == 1
    assert "未知のキー" in result.stdout


def test_optional_keys_allowed(tmp_path):
    d = tmp_path / "full-skill"
    d.mkdir()
    (d / "SKILL.md").write_text(
        "---\nname: full-skill\ndescription: x\nlicense: Apache-2.0\n"
        "metadata:\n  short-description: 短い説明\ndependencies: []\n---\n本文",
        encoding="utf-8")
    assert run(tmp_path).returncode == 0
