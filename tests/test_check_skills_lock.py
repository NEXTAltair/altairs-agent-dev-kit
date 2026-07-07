import json
import subprocess
import sys
from pathlib import Path

SCRIPT = Path(__file__).parent.parent / "scripts" / "check_skills_lock.py"


def write_lock(tmp_path: Path, skills: dict) -> Path:
    (tmp_path / "skills-lock.json").write_text(
        json.dumps({"version": 1, "skills": skills}), encoding="utf-8")
    return tmp_path


def run(root: Path) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, str(SCRIPT), "--root", str(root)],
                          capture_output=True, text=True, timeout=10)


def test_absolute_local_source_fails(tmp_path):
    # 絶対パスの local source (footgun の署名) は VIOLATION
    root = write_lock(tmp_path, {
        "foo": {"source": "/some/abs/kit", "sourceType": "local", "computedHash": "x"},
    })
    result = run(root)
    assert result.returncode == 1
    assert "foo" in result.stdout
    assert "非ポータブル" in result.stdout


def test_github_ref_source_ok(tmp_path):
    # github@ref の pin は正常
    root = write_lock(tmp_path, {
        "foo": {"source": "owner/repo", "ref": "v1.0.0",
                "sourceType": "github", "computedHash": "x"},
    })
    result = run(root)
    assert result.returncode == 0
    assert "OK" in result.stdout


def test_windows_abs_path_detected(tmp_path):
    # Windows ドライブ形式の絶対パスも検出
    root = write_lock(tmp_path, {
        "bar": {"source": "C:\\kit\\skills", "sourceType": "local"},
    })
    result = run(root)
    assert result.returncode == 1
    assert "bar" in result.stdout


def test_no_lock_is_ok(tmp_path):
    # skills-lock.json が無ければ検査対象なしで成功 (kit 自身など)
    result = run(tmp_path)
    assert result.returncode == 0
    assert "OK" in result.stdout
