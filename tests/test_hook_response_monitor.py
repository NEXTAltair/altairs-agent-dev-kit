import json
import subprocess
import sys
from pathlib import Path

from conftest import stop_block_reason

HOOK = Path(__file__).parent.parent / "hooks" / "scripts" / "hook_response_monitor.py"


def run_hook(text: str, cwd: Path) -> subprocess.CompletedProcess:
    # 実際の Stop イベント入力形式で渡す: 応答本文は transcript (JSONL) の
    # 末尾 assistant エントリから読まれる (本番で唯一動くパス)。
    transcript = cwd / "transcript.jsonl"
    entries = [
        {"type": "user", "message": {"content": [{"type": "text", "text": "質問"}]}},
        {"type": "assistant", "message": {"content": [{"type": "text", "text": text}]}},
    ]
    transcript.write_text("\n".join(json.dumps(e, ensure_ascii=False) for e in entries) + "\n",
                          encoding="utf-8")
    payload = json.dumps({
        "session_id": "test-session",
        "transcript_path": str(transcript),
        "cwd": str(cwd),
        "hook_event_name": "Stop",
        "stop_hook_active": False,
    })
    return subprocess.run(
        [sys.executable, str(HOOK)], input=payload,
        capture_output=True, text=True, cwd=cwd, timeout=10,
        env={"CLAUDE_PROJECT_DIR": str(cwd), "PATH": "/usr/bin:/bin"},
    )


def test_missing_transcript_fails_open(tmp_path):
    """transcript が無い/読めない場合は fail-open (allow)"""
    payload = json.dumps({
        "session_id": "s", "transcript_path": str(tmp_path / "nope.jsonl"),
        "cwd": str(tmp_path), "hook_event_name": "Stop", "stop_hook_active": False,
    })
    result = subprocess.run(
        [sys.executable, str(HOOK)], input=payload,
        capture_output=True, text=True, cwd=tmp_path, timeout=10,
        env={"CLAUDE_PROJECT_DIR": str(tmp_path), "PATH": "/usr/bin:/bin"},
    )
    assert result.returncode == 0


def test_no_rules_allows_everything(tmp_path):
    assert run_hook("なんでも書ける", tmp_path).returncode == 0


def test_override_word_blocks(tmp_path):
    rules_dir = tmp_path / ".claude" / "hooks" / "rules"
    rules_dir.mkdir(parents=True)
    (rules_dir / "response_monitor.json").write_text(json.dumps({
        "ng_words": [{"keyword": "たぶん", "message": "推測禁止。検証せよ"}]
    }), encoding="utf-8")
    result = run_hook("たぶん動きます", tmp_path)
    reason = stop_block_reason(result)
    assert reason and "推測禁止" in reason


def test_override_word_not_present_allows(tmp_path):
    rules_dir = tmp_path / ".claude" / "hooks" / "rules"
    rules_dir.mkdir(parents=True)
    (rules_dir / "response_monitor.json").write_text(json.dumps({
        "ng_words": [{"keyword": "たぶん", "message": "推測禁止。検証せよ"}]
    }), encoding="utf-8")
    result = run_hook("確認してテストしました", tmp_path)
    assert result.returncode == 0
    assert stop_block_reason(result) is None


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
    reason = stop_block_reason(result)
    assert reason and "接続詞の連打" in reason


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


def _exclude_rules(tmp_path, exclude_patterns):
    rules_dir = tmp_path / ".claude" / "hooks" / "rules"
    rules_dir.mkdir(parents=True)
    (rules_dir / "response_monitor.json").write_text(json.dumps({
        "ng_words": [{
            "keywords": ["かもしれ"],
            "message": "推測禁止",
            "exclude_patterns": exclude_patterns,
        }]
    }), encoding="utf-8")


def test_exclude_pattern_allows_conceded_form(tmp_path):
    """exclude_patterns に一致する箇所はそのルールの判定対象から除外される"""
    _exclude_rules(tmp_path, ["かもしれない(が|けど)"])
    result = run_hook("失敗するかもしれないが、検証した上で対応済みです。", tmp_path)
    assert result.returncode == 0
    assert stop_block_reason(result) is None


def test_exclude_pattern_still_blocks_plain_hit(tmp_path):
    """exclude に一致しない素の keyword 出現は引き続きブロックされる"""
    _exclude_rules(tmp_path, ["かもしれない(が|けど)"])
    result = run_hook("たぶん動くかもしれません。", tmp_path)
    reason = stop_block_reason(result)
    assert reason and "推測禁止" in reason


def test_exclude_pattern_scoped_per_rule(tmp_path):
    """exclude は自ルールのみに効き、他ルールの判定へ影響しない"""
    rules_dir = tmp_path / ".claude" / "hooks" / "rules"
    rules_dir.mkdir(parents=True)
    (rules_dir / "response_monitor.json").write_text(json.dumps({
        "ng_words": [
            {"keywords": ["かもしれ"], "message": "推測禁止",
             "exclude_patterns": ["かもしれない(が|けど)"]},
            {"keywords": ["ないが"], "message": "別ルール"},
        ]
    }), encoding="utf-8")
    result = run_hook("失敗するかもしれないが、続行します。", tmp_path)
    reason = stop_block_reason(result)
    assert reason and "別ルール" in reason and "推測禁止" not in reason


def test_invalid_exclude_regex_fails_open(tmp_path):
    """不正な正規表現の exclude は無視され、判定自体は継続する"""
    _exclude_rules(tmp_path, ["([unclosed"])
    result = run_hook("かもしれません。", tmp_path)
    reason = stop_block_reason(result)
    assert reason and "推測禁止" in reason
