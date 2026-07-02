import json
import subprocess
import sys
from pathlib import Path

HOOK = Path(__file__).parent.parent / "hooks" / "scripts" / "hook_response_monitor.py"


def run_hook(text: str, cwd: Path) -> subprocess.CompletedProcess:
    # extract_response_content() が最初に確認するのはトップレベル "response" フィールド
    # (移植元 hook_response_monitor.py の extract_response_content() 実装が SSoT)。
    payload = json.dumps({"response": text})
    return subprocess.run(
        [sys.executable, str(HOOK)], input=payload,
        capture_output=True, text=True, cwd=cwd, timeout=10,
        env={"CLAUDE_PROJECT_DIR": str(cwd), "PATH": "/usr/bin:/bin"},
    )


def test_no_rules_allows_everything(tmp_path):
    assert run_hook("なんでも書ける", tmp_path).returncode == 0


def test_override_word_blocks(tmp_path):
    rules_dir = tmp_path / ".claude" / "hooks" / "rules"
    rules_dir.mkdir(parents=True)
    (rules_dir / "response_monitor.json").write_text(json.dumps({
        "ng_words": [{"keyword": "たぶん", "message": "推測禁止。検証せよ"}]
    }), encoding="utf-8")
    result = run_hook("たぶん動きます", tmp_path)
    assert result.returncode == 2
    assert "推測禁止" in result.stderr


def test_override_word_not_present_allows(tmp_path):
    rules_dir = tmp_path / ".claude" / "hooks" / "rules"
    rules_dir.mkdir(parents=True)
    (rules_dir / "response_monitor.json").write_text(json.dumps({
        "ng_words": [{"keyword": "たぶん", "message": "推測禁止。検証せよ"}]
    }), encoding="utf-8")
    result = run_hook("確認してテストしました", tmp_path)
    assert result.returncode == 0


def test_quoted_mention_is_excluded(tmp_path):
    rules_dir = tmp_path / ".claude" / "hooks" / "rules"
    rules_dir.mkdir(parents=True)
    (rules_dir / "response_monitor.json").write_text(json.dumps({
        "ng_words": [{"keyword": "たぶん", "message": "推測禁止。検証せよ"}]
    }), encoding="utf-8")
    # 引用符内の言及はキーワード対象外 (strip_quoted_content)
    result = run_hook("「たぶん」という表現は禁止ワードです", tmp_path)
    assert result.returncode == 0


def test_threshold_group_blocks_on_repetition(tmp_path):
    rules_dir = tmp_path / ".claude" / "hooks" / "rules"
    rules_dir.mkdir(parents=True)
    (rules_dir / "response_monitor.json").write_text(json.dumps({
        "ng_words": [{
            "keywords": ["さらに", "また", "加えて"],
            "threshold": 3,
            "message": "接続詞の連打",
        }]
    }), encoding="utf-8")
    result = run_hook("さらに書きます。また書きます。加えて書きます。", tmp_path)
    assert result.returncode == 2
    assert "接続詞の連打" in result.stderr


def test_threshold_group_allows_below_threshold(tmp_path):
    rules_dir = tmp_path / ".claude" / "hooks" / "rules"
    rules_dir.mkdir(parents=True)
    (rules_dir / "response_monitor.json").write_text(json.dumps({
        "ng_words": [{
            "keywords": ["さらに", "また", "加えて"],
            "threshold": 3,
            "message": "接続詞の連打",
        }]
    }), encoding="utf-8")
    result = run_hook("さらに書きます。", tmp_path)
    assert result.returncode == 0
