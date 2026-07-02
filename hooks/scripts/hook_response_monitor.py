#!/usr/bin/env python3
"""
Hook - Response Monitor (Stop Hook)

Claude 応答完了時に実行される Stop hook による NG ワード検出システム。
応答内容をチェックし、NG ワード検出時は decision: block を返して差し戻す。

ルールは 2 層構造で解決する (`hook_common.load_hook_rules`):
- デフォルト層: `hooks/rules/response_monitor.default.json` (kit 同梱、
  `ng_words` は空リスト = デフォルト無効。NG ワードはプロジェクト文化依存のため)
- 導入先 override 層: `<project_root>/.claude/hooks/rules/response_monitor.json`
  (`ng_words` にエントリを追加して有効化する)

ルール形式:
    {
      "ng_words": [
        {"keyword": "たぶん", "message": "推測禁止。検証せよ"},
        {"keywords": ["さらに", "また", "加えて"], "threshold": 3, "message": "接続詞の連打"}
      ]
    }

各エントリのフィールド:
- keyword (str) または keywords (list[str]): 検出対象語 (どちらか一方)
- message (str): 違反時に表示する指摘文
- threshold (int, 省略時 1): 2 以上を指定すると「keywords 内語の合計出現回数」が
  閾値以上の場合にのみ違反とする（接続詞の連打検知など）。1 の場合は 1 回でも
  出現すれば違反。

特徴:
- 引用符 (「」/""/``) 内のコンテンツはキーワード判定から除外する
  (キーワードの言及・例示・引用は対象外)
"""

import json
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).parent))
from hook_common import find_project_root, get_log_dir, load_hook_rules  # noqa: E402


def log_debug(log_dir: Path, message: str) -> None:
    """デバッグログ出力"""
    try:
        log_dir.mkdir(parents=True, exist_ok=True)
        log_file = log_dir / "hook_response_monitor_debug.log"
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with log_file.open("a", encoding="utf-8") as f:
            f.write(f"[{timestamp}] {message}\n")
    except OSError:
        pass


def strip_quoted_content(text: str) -> str:
    """引用符内のコンテンツを除去する（引用・言及・例示は NG ワード対象外）。

    対象: 「」（日本語鉤括弧）、""（英語ダブルクオート）、``（バッククオート）
    """
    text = re.sub(r"「[^」]*」", "", text)
    text = re.sub(r'"[^"]*"', "", text)
    text = re.sub(r"`[^`\n]*`", "", text)
    return text


def check_ng_words(message: str, rules: dict[str, Any]) -> list[str]:
    """NG ワード検出。違反メッセージのリストを返す（空なら違反なし）。"""
    ng_words = rules.get("ng_words", [])
    if not ng_words:
        return []

    check_message = strip_quoted_content(message)
    violations: list[str] = []

    for entry in ng_words:
        if not isinstance(entry, dict):
            continue

        rule_message = entry.get("message", "NG word rule violation")
        threshold = entry.get("threshold", 1)

        keywords = entry.get("keywords")
        if keywords is None:
            single = entry.get("keyword")
            keywords = [single] if single else []
        keywords = [k for k in keywords if isinstance(k, str) and k]
        if not keywords:
            continue

        if isinstance(threshold, int) and threshold > 1:
            total = sum(
                len(re.findall(re.escape(keyword), check_message, re.IGNORECASE))
                for keyword in keywords
            )
            if total >= threshold:
                violations.append(f"🚫 {total}回検出（閾値{threshold}回）\n   → {rule_message}")
            continue

        for keyword in keywords:
            if re.search(re.escape(keyword), check_message, re.IGNORECASE):
                violations.append(f"🚫 キーワード「{keyword}」検出\n   → {rule_message}")
                break

    return violations


def extract_response_content(input_data: dict[str, Any]) -> str | None:
    """Stop hook 入力データから Claude 応答を抽出する。

    Stop hook が渡すフィールド名は Claude Code のバージョンにより変わり得るため、
    複数の候補フィールドと transcript_path フォールバックを順に確認する。
    """
    if "response" in input_data:
        response = input_data["response"]
        if isinstance(response, str) and response.strip():
            return response
        if isinstance(response, dict):
            for field in ("content", "text", "message", "output"):
                content = response.get(field)
                if isinstance(content, str) and content.strip():
                    return content

    for field in ("assistant_response", "claude_response", "output", "content", "text", "message"):
        value = input_data.get(field)
        if isinstance(value, str) and value.strip():
            return value

    transcript_path = input_data.get("transcript_path", "")
    if transcript_path and Path(transcript_path).exists():
        try:
            with open(transcript_path, encoding="utf-8") as f:
                lines = f.readlines()
        except OSError:
            return None

        for line in reversed(lines):
            line = line.strip()
            if not line:
                continue
            try:
                entry = json.loads(line)
            except json.JSONDecodeError:
                continue
            if entry.get("type") != "assistant":
                continue
            msg = entry.get("message", "")
            if isinstance(msg, dict):
                text_parts = [
                    item.get("text", "")
                    for item in msg.get("content", [])
                    if isinstance(item, dict) and item.get("type") == "text"
                ]
                if text_parts:
                    return "\n".join(text_parts)
            elif isinstance(msg, str) and msg.strip():
                return msg

    return None


def main() -> None:
    """メイン処理: Claude 応答完了時の NG ワード監視"""
    try:
        if sys.stdin.isatty():
            sys.exit(0)

        input_data: dict[str, Any] = json.load(sys.stdin)

        root = find_project_root()
        log_dir = get_log_dir(root)
        log_debug(log_dir, "=== Response Monitor (Stop Hook) Started ===")

        rules = load_hook_rules("response_monitor", root)
        if not rules.get("ng_words"):
            log_debug(log_dir, "No ng_words configured, monitoring disabled")
            sys.exit(0)

        response_content = extract_response_content(input_data)
        if not response_content:
            log_debug(log_dir, "No response content to monitor")
            sys.exit(0)

        log_debug(log_dir, f"Monitoring response length: {len(response_content)} characters")

        violations = check_ng_words(response_content, rules)
        if violations:
            violations_text = "\n".join(violations)
            reason = (
                "🚫 NG ワード規則違反が検出されました（ファイル・ブランチ名に含まれている場合を除く）:\n\n"
                f"{violations_text}\n\n"
                "作業を中止し、具体的な調査・検証を実施してから再回答してください。\n"
                "推測・代替案・追加作業は禁止。指示されたことのみを正確に実行してください。"
            )
            print(json.dumps({"decision": "block", "reason": reason}, ensure_ascii=False, indent=2))
            print(reason, file=sys.stderr)
            log_debug(log_dir, f"VIOLATIONS: {len(violations)} detected")
            sys.exit(2)

        log_debug(log_dir, "No violations detected, monitoring complete")
        sys.exit(0)

    except json.JSONDecodeError as e:
        # 入力が壊れている場合は monitoring を諦めて allow (fail-open)
        try:
            log_debug(get_log_dir(find_project_root()), f"JSON decode error: {e}, monitoring disabled")
        except OSError:
            pass
        sys.exit(0)
    except Exception as e:
        # hook は fail-open: 予期しない例外が起きても Stop hook そのものはブロックしない
        try:
            log_debug(get_log_dir(find_project_root()), f"Unexpected error: {e}, monitoring disabled")
        except OSError:
            pass
        sys.exit(0)


if __name__ == "__main__":
    main()
