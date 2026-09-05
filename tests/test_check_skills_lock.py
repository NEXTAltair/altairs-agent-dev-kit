import json
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPT = Path(__file__).parent.parent / "scripts" / "check_skills_lock.py"


def write_lock(tmp_path: Path, skills: dict) -> Path:
    (tmp_path / "skills-lock.json").write_text(
        json.dumps({"version": 1, "skills": skills}), encoding="utf-8")
    return tmp_path


def run(root: Path) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, "-X", "utf8", str(SCRIPT), "--root", str(root)],
                          capture_output=True, text=True, encoding="utf-8", timeout=10)


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


@pytest.mark.parametrize("source", ["../../outside/kit", "skills/../../outside", r"..\outside",
                                   r"\\server\share\kit", "C:kit"])
def test_local_source_outside_consumer_fails(tmp_path, source):
    result = run(write_lock(tmp_path, {"foo": {"source": source, "sourceType": "local"}}))
    assert result.returncode == 1
    assert "foo" in result.stdout
    assert "非ポータブル" in result.stdout


@pytest.mark.parametrize("source", [".", "skills/自前", "skills/../own", r"skills\own"])
def test_consumer_relative_source_is_portable(tmp_path, source):
    result = run(write_lock(tmp_path, {"foo": {"source": source, "sourceType": "local"}}))
    assert result.returncode == 0, result.stderr


def test_local_symlink_cannot_escape_consumer(tmp_path):
    root = tmp_path / "consumer"
    root.mkdir()
    external = tmp_path / "external"
    external.mkdir()
    try:
        (root / "skills").symlink_to(external, target_is_directory=True)
    except OSError:
        pytest.skip("directory symlinks unavailable")
    result = run(write_lock(root, {"foo": {"source": "skills", "sourceType": "local"}}))
    assert result.returncode == 1
    assert "consumer 外" in result.stdout


@pytest.mark.parametrize("lock", [None, [], {}, {"version": True, "skills": {}},
    {"version": 1, "skills": []}, {"version": 1, "skills": {"foo": None}},
    {"version": 1, "skills": {"foo": []}},
    {"version": 1, "skills": {"foo": {"source": 123, "sourceType": "local"}}},
    {"version": 1, "skills": {"foo": {"source": "", "sourceType": "local"}}},
    {"version": 1, "skills": {"foo": {"source": "skills"}}}])
def test_malformed_schema_fails_clearly(tmp_path, lock):
    (tmp_path / "skills-lock.json").write_text(json.dumps(lock), encoding="utf-8")
    result = run(tmp_path)
    assert result.returncode == 1
    assert "VIOLATION" in result.stdout
    assert "OK" not in result.stdout
    assert "Traceback" not in result.stderr


@pytest.mark.parametrize("content", [b'{"skills":', b'\xff\xfe'])
def test_unreadable_json_fails_clearly(tmp_path, content):
    (tmp_path / "skills-lock.json").write_bytes(content)
    result = run(tmp_path)
    assert result.returncode == 1
    assert "ERROR" in result.stderr
    assert "OK" not in result.stdout
    assert "Traceback" not in result.stderr


def test_github_without_ref_remains_supported(tmp_path):
    result = run(write_lock(tmp_path, {"foo": {"source": "owner/repo", "sourceType": "github"}}))
    assert result.returncode == 0
