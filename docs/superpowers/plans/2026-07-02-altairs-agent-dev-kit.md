---
type: Plan
title: altairs-agent-dev-kit Implementation Plan
description: skills / rules / hooks / agents / Codex 設定を汎用化し3経路で導入できる kit を構築する実装計画
timestamp: 2026-07-02
---
# altairs-agent-dev-kit Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** LoRAIro の開発標準 (skills / rules / hooks / agents / Codex 設定) を汎用化し、プラグイン + skills.sh + install.sh の3経路で任意リポジトリへ導入できる kit を構築する。

**Architecture:** 2層構造 (汎用コア = 本リポジトリ、プロジェクト固有値 = 導入先の override)。hooks は `hook_common.py` がプロジェクトルート検出とルールマージを担い、各 hook スクリプトはそれを使う。設定整合 lint (`check_config_consistency.py`) が「rules の約束 ⇔ settings.json ⇔ hook 実在」の drift を検出する。

**Tech Stack:** Python 3.10+ (stdlib only、外部依存なし)、pytest (dev のみ)、bash (install.sh)、GitHub Actions。

## Global Constraints

- 移植元は `/workspaces/LoRAIro` (同 devcontainer 内でアクセス可能)。spec は `docs/superpowers/specs/2026-07-02-altairs-agent-dev-kit-design.md`
- kit 本体 (skills/rules/hooks/agents/codex/scripts) に「LoRAIro」「lorairo」「/workspaces/LoRAIro」という文字列を残さない。例外: `docs/adoption.md` と `docs/third-party-skills.md` の「実例としての参照」のみ可
- hook / scripts は **Python 3.10+ stdlib only** (import は json/os/re/sys/shlex/subprocess/pathlib/datetime/typing/argparse のみ)
- ドキュメント・SKILL.md・rules は日本語主体。コード内コメントも日本語可
- ライセンスファイルは作らない (私的利用の決定)
- コミットは各タスク末尾で行う。メッセージ末尾に `Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>`
- テスト実行コマンドは `uv run --no-project pytest` ではなく、Task 1 で作る venv の `pytest` を使う: `uv run pytest`

## File Structure (最終形)

```
altairs-agent-dev-kit/
├── .claude-plugin/plugin.json
├── skills/<name>/SKILL.md (13 skills)
├── agents/*.md (10)
├── hooks/
│   ├── hooks.json
│   ├── scripts/{hook_common,hook_pre_commands,hook_pre_edit_worktree,
│   │            hook_pre_pr_submodule_check,hook_response_monitor,
│   │            hook_worktree_create}.py
│   └── rules/{pre_commands,response_monitor,pre_pr_submodule_check}.default.json
├── rules/*.md (8)
├── codex/{config.toml.template, agents/*.toml, hooks/README.md}
├── scripts/{check_config_consistency.py, lint_skills.py}
├── tests/ (pytest)
├── install.sh
├── pyproject.toml
├── README.md
└── docs/{adoption.md, third-party-skills.md}
```

---

### Task 1: リポジトリ骨格と pytest 環境

**Files:**
- Create: `pyproject.toml`, `.gitignore`, ディレクトリ骨格

**Interfaces:**
- Produces: `uv run pytest` が動く空のテスト環境。以降の全タスクが使う

- [ ] **Step 1: ディレクトリと .gitignore を作成**

```bash
cd /workspaces/altairs-agent-dev-kit
mkdir -p .claude-plugin skills agents hooks/scripts hooks/rules rules codex/agents codex/hooks scripts tests docs
printf '%s\n' '.venv/' '__pycache__/' '*.pyc' '.pytest_cache/' > .gitignore
```

- [ ] **Step 2: pyproject.toml を作成**

```toml
[project]
name = "altairs-agent-dev-kit"
version = "0.1.0"
description = "AI エージェント開発標準 kit: skills / rules / hooks / agents"
requires-python = ">=3.10"

[dependency-groups]
dev = ["pytest>=8.0"]

[tool.pytest.ini_options]
testpaths = ["tests"]
```

- [ ] **Step 3: 動作確認**

Run: `cd /workspaces/altairs-agent-dev-kit && uv sync --dev && uv run pytest`
Expected: `no tests ran` (exit 5) — 環境が動くこと

- [ ] **Step 4: Commit**

```bash
git add -A && git commit -m "chore: リポジトリ骨格と pytest 環境"
```

---

### Task 2: hooks 共通基盤 hook_common.py (TDD)

**Files:**
- Create: `hooks/scripts/hook_common.py`
- Test: `tests/test_hook_common.py`

**Interfaces:**
- Produces (Task 3-5 が consume):
  - `find_project_root() -> Path` — `CLAUDE_PROJECT_DIR` env → `git rev-parse --show-toplevel` → `Path.cwd()` の順で解決
  - `get_log_dir(root: Path) -> Path` — `root / ".claude" / "logs"` を返す (mkdir はしない)
  - `deep_merge(base: dict, override: dict) -> dict` — dict は再帰マージ、list は連結 (base + override)、スカラは override 優先。非破壊 (新 dict を返す)
  - `load_hook_rules(hook_name: str, project_root: Path) -> dict` — `hooks/rules/<hook_name>.default.json` (スクリプト隣接) を読み、`<project_root>/.claude/hooks/rules/<hook_name>.json` があれば deep_merge。どちらも無ければ `{}`

- [ ] **Step 1: 失敗するテストを書く** (`tests/test_hook_common.py`)

```python
import json
import os
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "hooks" / "scripts"))
import hook_common


def test_find_project_root_env(monkeypatch, tmp_path):
    monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(tmp_path))
    assert hook_common.find_project_root() == tmp_path


def test_find_project_root_git(monkeypatch, tmp_path):
    monkeypatch.delenv("CLAUDE_PROJECT_DIR", raising=False)
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    monkeypatch.chdir(tmp_path)
    assert hook_common.find_project_root() == tmp_path.resolve()


def test_deep_merge_lists_concat_and_scalar_override():
    base = {"blocked": [{"pattern": "a"}], "flag": 1, "nested": {"x": 1, "y": 2}}
    override = {"blocked": [{"pattern": "b"}], "flag": 2, "nested": {"y": 9}}
    merged = hook_common.deep_merge(base, override)
    assert [r["pattern"] for r in merged["blocked"]] == ["a", "b"]
    assert merged["flag"] == 2
    assert merged["nested"] == {"x": 1, "y": 9}
    assert base["blocked"] == [{"pattern": "a"}]  # 非破壊


def test_load_hook_rules_default_plus_override(tmp_path, monkeypatch):
    # default 側: スクリプト隣接の rules ディレクトリを monkeypatch で差し替え
    default_dir = tmp_path / "defaults"
    default_dir.mkdir()
    (default_dir / "pre_commands.default.json").write_text(
        json.dumps({"blocked_commands": [{"pattern": "^rm -rf"}]}), encoding="utf-8"
    )
    monkeypatch.setattr(hook_common, "DEFAULT_RULES_DIR", default_dir)
    # override 側: project の .claude/hooks/rules/
    proj = tmp_path / "proj"
    ov_dir = proj / ".claude" / "hooks" / "rules"
    ov_dir.mkdir(parents=True)
    (ov_dir / "pre_commands.json").write_text(
        json.dumps({"blocked_commands": [{"pattern": "^pip "}]}), encoding="utf-8"
    )
    rules = hook_common.load_hook_rules("pre_commands", proj)
    patterns = [r["pattern"] for r in rules["blocked_commands"]]
    assert patterns == ["^rm -rf", "^pip "]


def test_load_hook_rules_missing_files(tmp_path, monkeypatch):
    monkeypatch.setattr(hook_common, "DEFAULT_RULES_DIR", tmp_path / "none")
    assert hook_common.load_hook_rules("pre_commands", tmp_path) == {}
```

- [ ] **Step 2: 失敗を確認**

Run: `uv run pytest tests/test_hook_common.py -v`
Expected: FAIL (`ModuleNotFoundError: No module named 'hook_common'`)

- [ ] **Step 3: 実装** (`hooks/scripts/hook_common.py`)

```python
#!/usr/bin/env python3
"""hook 共通基盤: プロジェクトルート検出とルールのマージ読込。

kit の hook はプロジェクト固有パスをハードコードしない。
具体値は環境変数と導入先の override JSON から解決する。
"""

import json
import os
import subprocess
from pathlib import Path
from typing import Any

DEFAULT_RULES_DIR = Path(__file__).parent.parent / "rules"


def find_project_root() -> Path:
    env = os.environ.get("CLAUDE_PROJECT_DIR")
    if env:
        return Path(env)
    try:
        out = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            capture_output=True, text=True, check=True, timeout=5,
        )
        return Path(out.stdout.strip()).resolve()
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired, FileNotFoundError):
        return Path.cwd()


def get_log_dir(root: Path) -> Path:
    return root / ".claude" / "logs"


def deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    merged: dict[str, Any] = dict(base)
    for key, value in override.items():
        if key in merged and isinstance(merged[key], dict) and isinstance(value, dict):
            merged[key] = deep_merge(merged[key], value)
        elif key in merged and isinstance(merged[key], list) and isinstance(value, list):
            merged[key] = merged[key] + value
        else:
            merged[key] = value
    return merged


def _read_json(path: Path) -> dict[str, Any]:
    try:
        with path.open(encoding="utf-8") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return {}


def load_hook_rules(hook_name: str, project_root: Path) -> dict[str, Any]:
    default = _read_json(DEFAULT_RULES_DIR / f"{hook_name}.default.json")
    override = _read_json(project_root / ".claude" / "hooks" / "rules" / f"{hook_name}.json")
    if not default:
        return override
    if not override:
        return default
    return deep_merge(default, override)
```

- [ ] **Step 4: テストが通ることを確認**

Run: `uv run pytest tests/test_hook_common.py -v`
Expected: 5 PASS

- [ ] **Step 5: Commit**

```bash
git add hooks/scripts/hook_common.py tests/test_hook_common.py
git commit -m "feat(hooks): プロジェクトルート検出とルールマージの共通基盤"
```

---

### Task 3: hook_pre_commands.py 移植 + デフォルトルール JSON

**Files:**
- Create: `hooks/scripts/hook_pre_commands.py` (移植元: `/workspaces/LoRAIro/.claude/hooks/hook_pre_commands.py`)
- Create: `hooks/rules/pre_commands.default.json`
- Test: `tests/test_hook_pre_commands.py`

**Interfaces:**
- Consumes: `hook_common.find_project_root/get_log_dir/load_hook_rules`
- Produces: PreToolUse(Bash) hook。stdin に Claude Code hook JSON (`{"tool_input": {"command": ...}}`) を受け、block 時 exit 2 + stderr、transform 時は updated input を stdout、許可時 exit 0

- [ ] **Step 1: 移植元を読み、以下の変更を適用して移植**

移植元の構造 (load_rules / apply_uv_transform / check_blocked / PR draft ブロック / worktree uv guard / main 関数) を維持しつつ:

1. 冒頭のモジュール定数 `LOG_DIR` / `WORKTREE_ROOT` / `SHARED_UV_ENV_VALUE` のハードコードを削除し、`main()` 冒頭で解決:
   ```python
   from hook_common import find_project_root, get_log_dir, load_hook_rules
   PROJECT_ROOT = find_project_root()
   LOG_DIR = get_log_dir(PROJECT_ROOT)
   WORKTREE_ROOT = PROJECT_ROOT / ".agents" / "worktree"
   SHARED_UV_ENV_VALUE = str(PROJECT_ROOT / ".venv")
   ```
2. `load_rules()` を `load_hook_rules("pre_commands", PROJECT_ROOT)` 呼び出しに置換
3. worktree uv guard (UV_PROJECT_ENVIRONMENT 必須チェック) は、マージ後 rules の `"worktree_uv_guard": true` の時のみ有効化 (default JSON には含めない = 汎用デフォルトでは無効)
4. uv transform 群は default JSON に含めない (Python/uv プロジェクト固有のため override 側)
5. docstring から LoRAIro への参照を除去し、2層構造 (default + override) の説明に置換

- [ ] **Step 2: デフォルトルール JSON を作成** (`hooks/rules/pre_commands.default.json`)

言語非依存の安全最小セットのみ。移植元 `/workspaces/LoRAIro/.claude/hooks/rules/hook_pre_commands_rules.json` の `blocked_commands` から `^pip ` (Python 固有) と `uv run --active` (uv 固有) を除いた git 破壊系 5 件 + `rm -rf` を採用:

```json
{
  "description": "汎用デフォルト: 破壊的コマンドのブロック (言語非依存)",
  "blocked_commands": [
    {"pattern": "^rm\\s+-rf\\s+.+", "reason": "破壊的操作", "suggestion": "対象を確認しユーザーに確認を取ってください"},
    {"pattern": "git\\s+filter-repo", "reason": "【危険】ワーキングディレクトリのファイルも削除されます", "suggestion": "git rm --cached + .gitignore を検討。履歴削除が必要かユーザーに確認"},
    {"pattern": "git\\s+reset\\s+--hard", "reason": "【危険】未コミットの全変更を永久に消去します", "suggestion": "git stash で退避するかユーザーに確認"},
    {"pattern": "git\\s+push\\s+(.*\\s)?(-f|--force)(?!-with-lease)", "reason": "【危険】リモート履歴を強制上書きします", "suggestion": "git push --force-with-lease を使うかユーザーに確認"},
    {"pattern": "git\\s+checkout\\s+(--\\s*\\.|\\.$|-f)", "reason": "【危険】未コミットの全変更を消去します", "suggestion": "git stash で退避するかユーザーに確認"},
    {"pattern": "git\\s+clean\\s+.*-f", "reason": "【危険】未追跡ファイルを完全に削除します", "suggestion": "git clean -n でドライラン確認かユーザーに確認"}
  ],
  "uv_transforms": [],
  "block_draft_pr": true,
  "worktree_uv_guard": false
}
```

- [ ] **Step 3: テストを書く** (`tests/test_hook_pre_commands.py`)

hook はプロセスとして起動して検証する (stdin JSON → exit code / stderr):

```python
import json
import subprocess
import sys
from pathlib import Path

HOOK = Path(__file__).parent.parent / "hooks" / "scripts" / "hook_pre_commands.py"


def run_hook(command: str, cwd: Path) -> subprocess.CompletedProcess:
    payload = json.dumps({"tool_name": "Bash", "tool_input": {"command": command}})
    return subprocess.run(
        [sys.executable, str(HOOK)], input=payload,
        capture_output=True, text=True, cwd=cwd, timeout=10,
        env={"CLAUDE_PROJECT_DIR": str(cwd), "PATH": "/usr/bin:/bin"},
    )


def test_git_reset_hard_blocked(tmp_path):
    result = run_hook("git reset --hard HEAD~1", tmp_path)
    assert result.returncode == 2
    assert "危険" in result.stderr


def test_normal_command_allowed(tmp_path):
    result = run_hook("ls -la", tmp_path)
    assert result.returncode == 0


def test_project_override_adds_block(tmp_path):
    rules_dir = tmp_path / ".claude" / "hooks" / "rules"
    rules_dir.mkdir(parents=True)
    (rules_dir / "pre_commands.json").write_text(
        json.dumps({"blocked_commands": [
            {"pattern": "^pip ", "reason": "pip 禁止", "suggestion": "uv add"}
        ]}), encoding="utf-8")
    result = run_hook("pip install requests", tmp_path)
    assert result.returncode == 2
    assert "pip" in result.stderr
```

- [ ] **Step 4: テスト実行**

Run: `uv run pytest tests/test_hook_pre_commands.py -v`
Expected: 3 PASS。失敗したら移植コードを修正 (テスト側は Claude Code hook 入出力仕様が SSoT)

- [ ] **Step 5: 汎用化の grep 検証**

Run: `grep -rn "LoRAIro\|lorairo\|/workspaces/" hooks/scripts/hook_pre_commands.py hooks/rules/pre_commands.default.json`
Expected: ヒット 0 件

- [ ] **Step 6: Commit**

```bash
git add hooks/ tests/test_hook_pre_commands.py
git commit -m "feat(hooks): pre_commands hook を汎用化して移植"
```

---

### Task 4: hook_worktree_create.py + hook_pre_edit_worktree.py 移植

**Files:**
- Create: `hooks/scripts/hook_worktree_create.py` (移植元: `/workspaces/LoRAIro/.claude/hooks/hook_worktree_create.py`)
- Create: `hooks/scripts/hook_pre_edit_worktree.py` (移植元: `/workspaces/LoRAIro/.claude/hooks/hook_pre_edit_worktree.py`)
- Test: `tests/test_hook_worktree.py`

**Interfaces:**
- Consumes: `hook_common.find_project_root`
- Produces:
  - `hook_worktree_create.py`: WorktreeCreate hook。`<project_root>/.agents/worktree/<name>` に worktree を作成しパスを stdout に echo する provider 形状
  - `hook_pre_edit_worktree.py`: PreToolUse(Edit|Write|MultiEdit) hook。共有 checkout 直下の保護対象ディレクトリ (デフォルト `src/`, `tests/`) への直接編集を exit 2 でブロック。worktree 内は許可

- [ ] **Step 1: 2 つの hook を移植**

共通の変更:
1. `/workspaces/LoRAIro` ハードコードを `find_project_root()` に置換
2. worktree 配置先は `<root>/.agents/worktree` を定数化
3. `hook_pre_edit_worktree.py` の保護対象ディレクトリを rules から取得可能に: `load_hook_rules("pre_edit_worktree", root).get("protected_dirs", ["src", "tests"])`
4. docstring の LoRAIro 参照を除去

- [ ] **Step 2: テストを書く** (`tests/test_hook_worktree.py`)

```python
import json
import subprocess
import sys
from pathlib import Path

EDIT_HOOK = Path(__file__).parent.parent / "hooks" / "scripts" / "hook_pre_edit_worktree.py"


def run_edit_hook(file_path: str, cwd: Path) -> subprocess.CompletedProcess:
    payload = json.dumps({"tool_name": "Edit", "tool_input": {"file_path": file_path}})
    return subprocess.run(
        [sys.executable, str(EDIT_HOOK)], input=payload,
        capture_output=True, text=True, cwd=cwd, timeout=10,
        env={"CLAUDE_PROJECT_DIR": str(cwd), "PATH": "/usr/bin:/bin"},
    )


def test_shared_checkout_src_edit_blocked(tmp_path):
    (tmp_path / "src").mkdir()
    result = run_edit_hook(str(tmp_path / "src" / "app.py"), tmp_path)
    assert result.returncode == 2


def test_worktree_src_edit_allowed(tmp_path):
    wt = tmp_path / ".agents" / "worktree" / "fix-1" / "src"
    wt.mkdir(parents=True)
    result = run_edit_hook(str(wt / "app.py"), tmp_path)
    assert result.returncode == 0


def test_non_protected_edit_allowed(tmp_path):
    result = run_edit_hook(str(tmp_path / "docs" / "note.md"), tmp_path)
    assert result.returncode == 0
```

- [ ] **Step 3: テスト実行と grep 検証**

Run: `uv run pytest tests/test_hook_worktree.py -v && grep -rn "LoRAIro\|lorairo" hooks/scripts/hook_worktree_create.py hooks/scripts/hook_pre_edit_worktree.py`
Expected: 3 PASS、grep 0 件

- [ ] **Step 4: Commit**

```bash
git add hooks/scripts/ tests/test_hook_worktree.py
git commit -m "feat(hooks): worktree 作成/編集ガード hook を汎用化して移植"
```

---

### Task 5: hook_response_monitor.py + hook_pre_pr_submodule_check.py 移植

**Files:**
- Create: `hooks/scripts/hook_response_monitor.py` (移植元: `/workspaces/LoRAIro/.claude/hooks/hook_response_monitor.py`)
- Create: `hooks/rules/response_monitor.default.json`
- Create: `hooks/scripts/hook_pre_pr_submodule_check.py` (移植元: `/workspaces/LoRAIro/.claude/hooks/hook_pre_pr_submodule_check.py`)
- Create: `hooks/rules/pre_pr_submodule_check.default.json`
- Test: `tests/test_hook_response_monitor.py`

**Interfaces:**
- Consumes: `hook_common`
- Produces: Stop hook (NG ワード検出) と PreToolUse(Bash) hook (`gh pr create` 時の submodule 検証ゲート)

- [ ] **Step 1: hook_response_monitor.py を移植**

1. NG ワードリストを `load_hook_rules("response_monitor", root)` から取得 (移植元は `hook_stop_words_rules.json`)
2. `response_monitor.default.json` は **空の word リスト** をデフォルトとする (NG ワードは完全にプロジェクト文化依存のため)。移植元の LoRAIro ルール内容は `docs/adoption.md` に override 例として掲載する (Task 13)
3. ルールが空なら即 exit 0

- [ ] **Step 2: hook_pre_pr_submodule_check.py を移植**

1. submodule パスパターン (`local_packages/*`) と bypass marker (`CI-EQUIV-TESTED`) を rules 化: `pre_pr_submodule_check.default.json` に `{"submodule_globs": [], "bypass_marker": "CI-EQUIV-TESTED"}`。`submodule_globs` が空なら即 exit 0 (= デフォルト無効、submodule を持つ導入先だけが override で有効化)
2. LoRAIro 固有の説明文 (CI filter 表参照等) は「導入先の testing ルールを参照」という汎用文に置換

- [ ] **Step 3: テストを書く** (`tests/test_hook_response_monitor.py`)

```python
import json
import subprocess
import sys
from pathlib import Path

HOOK = Path(__file__).parent.parent / "hooks" / "scripts" / "hook_response_monitor.py"


def run_hook(text: str, cwd: Path) -> subprocess.CompletedProcess:
    payload = json.dumps({"last_assistant_message": text})
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
```

注意: 移植元の stdin ペイロードのキー名 (`last_assistant_message` 等) は移植元コードの実装を読んで一致させること。テスト側を実装に合わせて修正してよい。

- [ ] **Step 4: テスト実行と grep 検証**

Run: `uv run pytest tests/ -v && grep -rn "LoRAIro\|lorairo\|local_packages" hooks/`
Expected: 全 PASS、grep 0 件

- [ ] **Step 5: Commit**

```bash
git add hooks/ tests/test_hook_response_monitor.py
git commit -m "feat(hooks): response_monitor / pr_submodule_check を汎用化して移植"
```

---

### Task 6: rules 8本の汎用化移植

**Files:**
- Create: `rules/{coding-style,git-workflow,testing,logging,security,parallel-execution,dependency-management,planning-memory}.md` (移植元: `/workspaces/LoRAIro/.claude/rules/` の同名 8 ファイル)

**Interfaces:**
- Produces: 導入先が `.claude/rules/` へ copy/symlink して使う汎用ルール群

- [ ] **Step 1: 各ファイルを移植し汎用化する**

全ファイル共通の除去・置換:
1. `/workspaces/LoRAIro` → 「プロジェクトルート」/ `<project root>` 表記
2. Issue 番号・PR 番号・ADR 番号への参照 → 「(発端事例は導入先の記録参照)」に置換または削除
3. LoRAIro 固有の表・コマンド (CI filter 表、`make test-iam-lib`、`local_packages`、submodule 運用、iam-lib/genai-tag-db-tools) → 削除し、代わりに `> プロジェクト固有: 導入先はここに自プロジェクトの具体値を追記した override 版を置く` という追記ポイントのコメントを残す
4. 具体プロダクト名 (pytest-qt / PySide6 / loguru / SQLAlchemy) が主題のセクション → **残す** (技術スタック汎用であり LoRAIro 固有ではない)。ただし logging.md の loguru 前提は冒頭に「loguru を使うプロジェクト向け。他のロガーでもレベル設計の原則は同じ」と明記

ファイル別の要点:
- `parallel-execution.md`: venv 分離粒度 (worktree 間・package 間) の記述をこのファイルに集約する (spec の決定事項。git-workflow.md 側には集約先への参照だけ残す)
- `git-workflow.md`: worktree 配置先を「`.agents/worktree/` 配下 (kit の hook のデフォルト)」とし、完了の定義 (worktree → 検証 → PR → 保守 → merge → 掃除) は普遍なので保持
- `planning-memory.md`: OpenClaw LTM 節は LoRAIro 環境依存のため削除し、「ADR / lessons-learned / 最新計画の事前確認」の普遍部分のみ残す
- `dependency-management.md`: 「AI 推論 SDK は常に最新、lower bound のみ」の原則と判断フローを保持。対象 SDK リストは汎用 (どの AI プロジェクトでも同じ) なので保持

- [ ] **Step 2: 検証**

Run: `grep -rln "LoRAIro\|lorairo\|local_packages\|iam-lib\|/workspaces/" rules/`
Expected: 0 件

- [ ] **Step 3: Commit**

```bash
git add rules/ && git commit -m "feat(rules): 開発ルール 8 本を汎用化して移植"
```

---

### Task 7: skills 13本の移植と汎用化

**Files:**
- Create: `skills/<name>/` × 13 (移植元: `/workspaces/LoRAIro/.agents/skills/` の各ディレクトリ全体、SKILL.md + references/ + scripts/ を含む)

対象と改名:

| kit 名 | 移植元 | 汎用化の要点 |
|---|---|---|
| check-existing | check-existing | local_packages 前提の調査手順を「プロジェクトのローカルパッケージ/モノレポ構成があれば」と条件化 |
| pr-maintainer | agent-pr-maintainer | LoRAIro 固有の CI filter 表・Codex bot 運用の具体値を「導入先の testing ルール参照」に置換。ポーリング間隔/上限/エスカレーション基準 (普遍) は保持 |
| pr-autoloop | agent-pr-autoloop | 同上。ScheduleWakeup 自走の説明は保持 |
| github-ops | github-ops | ほぼそのまま |
| okf-bundle | okf-bundle | 既に汎用設計。そのまま |
| skill-creator | skill-creator | ほぼそのまま |
| lazy-import-refactor | lazy-import-refactor | ほぼそのまま |
| claude-md-progressive-disclosurer | 同名 | ほぼそのまま |
| prompt-optimizer | prompt-optimizer | そのまま |
| qa-expert | qa-expert | そのまま |
| interface-design | interface-design | lorairo-qt-widget への誘導文を「プロジェクト固有の実装スキルがあればそちら」と一般化 |
| sqlalchemy-query-patterns | sqlalchemy-query-patterns | 「LoRAIroのSQLite」表現を「SQLAlchemy プロジェクト」に一般化 |
| context7-openclaw-research | context7-openclaw-research | OpenClaw 接続前提を「利用可能な場合」と条件化 |

- [ ] **Step 1: 13 ディレクトリを cp -r で移植し、上記の表に従い SKILL.md を編集**

frontmatter の `name:` は改名後の kit 名に合わせる (pr-maintainer / pr-autoloop)。description 内の「LoRAIro」も除去。

- [ ] **Step 2: 検証**

Run: `grep -rln "LoRAIro\|lorairo" skills/`
Expected: 0 件

Run: `for d in skills/*/; do test -f "$d/SKILL.md" || echo "MISSING: $d"; done`
Expected: 出力なし (13 ディレクトリ全てに SKILL.md)

- [ ] **Step 3: Commit**

```bash
git add skills/ && git commit -m "feat(skills): 自作スキル 13 本を汎用化して移植"
```

---

### Task 8: agents 10本 + codex テンプレート

**Files:**
- Create: `agents/*.md` × 10 (移植元: `/workspaces/LoRAIro/.claude/agents/*.md`)
- Create: `codex/agents/*.toml` × 9 (移植元: `/workspaces/LoRAIro/.codex/agents/*.toml`)
- Create: `codex/config.toml.template` (移植元: `/workspaces/LoRAIro/.codex/config.toml`)
- Create: `codex/hooks/README.md`

**Interfaces:**
- Produces: プラグインの agents/ と、install.sh が `.codex/` へ展開するテンプレート

- [ ] **Step 1: agents を移植**

1. 「Repository Rules Reference」段落の `/workspaces/LoRAIro` を「the shared project checkout」に置換 (worktree パス `.agents/worktree/` は 2026-07-02 の修正で既に現行化済み)
2. `db-schema-reviewer` / `query-analyzer` の SQLAlchemy/Alembic 前提は主題なので保持
3. `lorairo-mem` スキルへの言い回しがあれば「プロジェクトの長期記憶スキルがあれば」と一般化

- [ ] **Step 2: codex/config.toml.template を作成**

`UV_PROJECT_ENVIRONMENT` などの絶対パスを `{{PROJECT_ROOT}}` プレースホルダに置換。install.sh (Task 11) が `sed` で実パスに展開する。LoRAIro 固有の MCP 設定・プロジェクト名があれば除去。

- [ ] **Step 3: codex/hooks/README.md を作成**

内容: 「Codex 用 hook は `hooks/scripts/` の同名スクリプトを共用する。install.sh --codex が `.codex/hooks/` に symlink を張る」という 1 段落。

- [ ] **Step 4: 検証と Commit**

Run: `grep -rln "LoRAIro\|lorairo\|/workspaces/" agents/ codex/`
Expected: 0 件

```bash
git add agents/ codex/ && git commit -m "feat(agents): agent 定義 10 本と Codex テンプレートを移植"
```

---

### Task 9: 設定整合 lint scripts/check_config_consistency.py (TDD)

**Files:**
- Create: `scripts/check_config_consistency.py`
- Test: `tests/test_check_config_consistency.py`

**Interfaces:**
- Produces: CLI `python3 scripts/check_config_consistency.py [--root <path>]`。検査対象は導入先リポジトリ。exit 0 = 整合、exit 1 = 違反あり (violation を 1 行 1 件で stdout に出す)
- 検査 3 種:
  - (a) `required_env`: `<root>/.claude/hooks/rules/consistency.json` の `required_env` リストの各キーが `<root>/.claude/settings.json` の `env` に存在するか
  - (b) 未配線 hook: `<root>/.claude/hooks/*.py` の各スクリプトが settings.json の `hooks.*[].hooks[].command` のどれかに含まれているか (含まれなければ WARNING 行、exit code には影響しない)
  - (c) 死んだ配線: settings.json の command 文字列中の `.py` パスが実在するか (実在しなければ violation)

- [ ] **Step 1: 失敗するテストを書く** (`tests/test_check_config_consistency.py`)

```python
import json
import subprocess
import sys
from pathlib import Path

SCRIPT = Path(__file__).parent.parent / "scripts" / "check_config_consistency.py"


def make_project(tmp_path: Path, settings: dict, consistency: dict | None = None,
                 hook_files: list[str] = ()) -> Path:
    claude = tmp_path / ".claude"
    (claude / "hooks" / "rules").mkdir(parents=True)
    (claude / "settings.json").write_text(json.dumps(settings), encoding="utf-8")
    if consistency is not None:
        (claude / "hooks" / "rules" / "consistency.json").write_text(
            json.dumps(consistency), encoding="utf-8")
    for name in hook_files:
        (claude / "hooks" / name).write_text("#!/usr/bin/env python3\n", encoding="utf-8")
    return tmp_path


def run(root: Path) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, str(SCRIPT), "--root", str(root)],
                          capture_output=True, text=True, timeout=10)


def test_missing_required_env_fails(tmp_path):
    root = make_project(tmp_path, {"env": {}},
                        consistency={"required_env": ["UV_PROJECT_ENVIRONMENT"]})
    result = run(root)
    assert result.returncode == 1
    assert "UV_PROJECT_ENVIRONMENT" in result.stdout


def test_dead_hook_wiring_fails(tmp_path):
    settings = {"hooks": {"PreToolUse": [{"matcher": "Bash", "hooks": [
        {"type": "command", "command": "/usr/bin/timeout 5s .claude/hooks/missing.py"}]}]}}
    result = run(make_project(tmp_path, settings))
    assert result.returncode == 1
    assert "missing.py" in result.stdout


def test_unwired_hook_warns_but_passes(tmp_path):
    root = make_project(tmp_path, {"hooks": {}}, hook_files=["orphan.py"])
    result = run(root)
    assert result.returncode == 0
    assert "orphan.py" in result.stdout  # WARNING 行


def test_consistent_project_passes(tmp_path):
    settings = {
        "env": {"MY_ENV": "1"},
        "hooks": {"PreToolUse": [{"matcher": "Bash", "hooks": [
            {"type": "command", "command": "/usr/bin/timeout 5s .claude/hooks/guard.py"}]}]},
    }
    root = make_project(tmp_path, settings,
                        consistency={"required_env": ["MY_ENV"]}, hook_files=["guard.py"])
    result = run(root)
    assert result.returncode == 0
```

- [ ] **Step 2: 失敗を確認**

Run: `uv run pytest tests/test_check_config_consistency.py -v`
Expected: FAIL (スクリプト不在)

- [ ] **Step 3: 実装** (`scripts/check_config_consistency.py`)

```python
#!/usr/bin/env python3
"""設定整合 lint: rules の約束 ⇔ settings.json ⇔ hook 実在の drift を検出する。

発端: settings.json の巻き戻り事故で env と hook 配線が消えたのに
rules は「設定済み」と書いたままになる drift が実際に起きたため。
"""

import argparse
import json
import re
import sys
from pathlib import Path


def load_json(path: Path) -> dict:
    try:
        with path.open(encoding="utf-8") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return {}


def iter_hook_commands(settings: dict):
    for entries in settings.get("hooks", {}).values():
        for entry in entries:
            for hook in entry.get("hooks", []):
                if hook.get("type") == "command":
                    yield hook.get("command", "")


def main() -> int:
    parser = argparse.ArgumentParser(description="設定整合 lint")
    parser.add_argument("--root", type=Path, default=Path.cwd())
    args = parser.parse_args()
    root: Path = args.root.resolve()
    claude = root / ".claude"
    settings = load_json(claude / "settings.json")
    consistency = load_json(claude / "hooks" / "rules" / "consistency.json")
    violations: list[str] = []
    warnings: list[str] = []

    # (a) required_env
    env = settings.get("env", {})
    for key in consistency.get("required_env", []):
        if key not in env:
            violations.append(f"VIOLATION: settings.json env に {key} がない (required_env)")

    # (b)(c) hook 配線
    commands = list(iter_hook_commands(settings))
    wired_scripts: set[str] = set()
    for cmd in commands:
        for match in re.findall(r"\S+\.py", cmd):
            script = Path(match)
            resolved = script if script.is_absolute() else root / script
            wired_scripts.add(resolved.name)
            if not resolved.exists():
                violations.append(f"VIOLATION: 配線された hook が実在しない: {match}")
    hooks_dir = claude / "hooks"
    if hooks_dir.is_dir():
        for script in sorted(hooks_dir.glob("*.py")):
            if script.name not in wired_scripts:
                warnings.append(f"WARNING: 未配線 hook: {script.name} (settings.json に登録なし)")

    for line in violations + warnings:
        print(line)
    if not violations and not warnings:
        print("OK: 設定整合に問題なし")
    return 1 if violations else 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: テストが通ることを確認**

Run: `uv run pytest tests/test_check_config_consistency.py -v`
Expected: 4 PASS

- [ ] **Step 5: Commit**

```bash
git add scripts/check_config_consistency.py tests/test_check_config_consistency.py
git commit -m "feat(scripts): 設定整合 lint (env/hook 配線 drift 検出)"
```

---

### Task 10: skills lint scripts/lint_skills.py (TDD)

**Files:**
- Create: `scripts/lint_skills.py`
- Test: `tests/test_lint_skills.py`

**Interfaces:**
- Produces: CLI `python3 scripts/lint_skills.py [--dir skills]`。各 `skills/*/SKILL.md` の frontmatter に `name:` と `description:` があり、`name` がディレクトリ名と一致することを検証。exit 0/1

- [ ] **Step 1: テストを書く** (`tests/test_lint_skills.py`)

```python
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
```

- [ ] **Step 2: 失敗確認 → 実装 → 成功確認**

実装 (`scripts/lint_skills.py`):

```python
#!/usr/bin/env python3
"""skills lint: SKILL.md の frontmatter 必須フィールドとディレクトリ名一致を検証。"""

import argparse
import re
import sys
from pathlib import Path


def parse_frontmatter(text: str) -> dict[str, str]:
    match = re.match(r"\A---\n(.*?)\n---\n", text, re.DOTALL)
    if not match:
        return {}
    fields: dict[str, str] = {}
    for line in match.group(1).splitlines():
        if ":" in line and not line.startswith((" ", "\t")):
            key, _, value = line.partition(":")
            fields[key.strip()] = value.strip()
    return fields


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dir", type=Path, default=Path("skills"))
    args = parser.parse_args()
    errors: list[str] = []
    for skill_dir in sorted(p for p in args.dir.iterdir() if p.is_dir()):
        skill_md = skill_dir / "SKILL.md"
        if not skill_md.exists():
            errors.append(f"{skill_dir.name}: SKILL.md がない")
            continue
        fm = parse_frontmatter(skill_md.read_text(encoding="utf-8"))
        if not fm.get("name"):
            errors.append(f"{skill_dir.name}: frontmatter に name がない")
        elif fm["name"] != skill_dir.name:
            errors.append(f"{skill_dir.name}: name '{fm['name']}' がディレクトリ名と不一致")
        if not fm.get("description"):
            errors.append(f"{skill_dir.name}: frontmatter に description がない")
    for e in errors:
        print(f"VIOLATION: {e}")
    if not errors:
        print("OK: 全 skill が有効")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
```

Run: `uv run pytest tests/test_lint_skills.py -v`
Expected: 3 PASS

- [ ] **Step 3: kit 自身の skills に対して実行**

Run: `uv run python scripts/lint_skills.py --dir skills`
Expected: `OK: 全 skill が有効`。VIOLATION が出たら Task 7 の成果物 (frontmatter) を修正

- [ ] **Step 4: Commit**

```bash
git add scripts/lint_skills.py tests/test_lint_skills.py skills/
git commit -m "feat(scripts): skills frontmatter lint"
```

---

### Task 11: install.sh + smoke テスト

**Files:**
- Create: `install.sh`
- Test: `tests/test_install.py`

**Interfaces:**
- Produces: `./install.sh --target <repo> [--rules] [--agents] [--hooks] [--codex] [--all]`
  - `--rules`: `rules/*.md` → `<target>/.claude/rules/` へ copy
  - `--agents`: `agents/*.md` → `<target>/.claude/agents/` へ copy
  - `--hooks`: `hooks/scripts/*.py` → `<target>/.claude/hooks/` へ copy、`hooks/rules/*.default.json` → `<target>/.claude/hooks/rules/` へ copy。settings.json の配線は自動変更せず、追加すべき JSON 断片を stdout に表示
  - `--codex`: `codex/config.toml.template` の `{{PROJECT_ROOT}}` を target 絶対パスに置換して `<target>/.codex/config.toml` へ (既存があれば `.new` 拡張子で並置)、`codex/agents/*.toml` → `<target>/.codex/agents/`
  - 既存ファイルは上書きせず `SKIP (exists)` 表示 (`--force` で上書き)

- [ ] **Step 1: install.sh を実装**

```bash
#!/usr/bin/env bash
# altairs-agent-dev-kit installer: rules / agents / hooks / codex を導入先へ展開する
set -euo pipefail

KIT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TARGET="" ; DO_RULES=0 ; DO_AGENTS=0 ; DO_HOOKS=0 ; DO_CODEX=0 ; FORCE=0

while [[ $# -gt 0 ]]; do
  case "$1" in
    --target) TARGET="$2"; shift 2 ;;
    --rules) DO_RULES=1; shift ;;
    --agents) DO_AGENTS=1; shift ;;
    --hooks) DO_HOOKS=1; shift ;;
    --codex) DO_CODEX=1; shift ;;
    --all) DO_RULES=1; DO_AGENTS=1; DO_HOOKS=1; DO_CODEX=1; shift ;;
    --force) FORCE=1; shift ;;
    *) echo "unknown option: $1" >&2; exit 1 ;;
  esac
done

[[ -n "$TARGET" && -d "$TARGET" ]] || { echo "--target <existing repo> が必要" >&2; exit 1; }
TARGET="$(cd "$TARGET" && pwd)"

copy_file() {  # copy_file <src> <dest>
  local src="$1" dest="$2"
  if [[ -e "$dest" && "$FORCE" -eq 0 ]]; then
    echo "SKIP (exists): $dest"
  else
    mkdir -p "$(dirname "$dest")"
    cp "$src" "$dest"
    echo "INSTALL: $dest"
  fi
}

if [[ "$DO_RULES" -eq 1 ]]; then
  for f in "$KIT_DIR"/rules/*.md; do copy_file "$f" "$TARGET/.claude/rules/$(basename "$f")"; done
fi

if [[ "$DO_AGENTS" -eq 1 ]]; then
  for f in "$KIT_DIR"/agents/*.md; do copy_file "$f" "$TARGET/.claude/agents/$(basename "$f")"; done
fi

if [[ "$DO_HOOKS" -eq 1 ]]; then
  for f in "$KIT_DIR"/hooks/scripts/*.py; do copy_file "$f" "$TARGET/.claude/hooks/$(basename "$f")"; done
  for f in "$KIT_DIR"/hooks/rules/*.default.json; do copy_file "$f" "$TARGET/.claude/hooks/rules/$(basename "$f")"; done
  chmod +x "$TARGET"/.claude/hooks/hook_*.py
  echo ""
  echo "== settings.json へ以下の hooks 配線を手動追加してください =="
  cat "$KIT_DIR/hooks/hooks.json"
fi

if [[ "$DO_CODEX" -eq 1 ]]; then
  mkdir -p "$TARGET/.codex/agents"
  dest="$TARGET/.codex/config.toml"
  [[ -e "$dest" && "$FORCE" -eq 0 ]] && dest="$dest.new"
  sed "s|{{PROJECT_ROOT}}|$TARGET|g" "$KIT_DIR/codex/config.toml.template" > "$dest"
  echo "INSTALL: $dest"
  for f in "$KIT_DIR"/codex/agents/*.toml; do copy_file "$f" "$TARGET/.codex/agents/$(basename "$f")"; done
fi

echo "DONE"
```

- [ ] **Step 2: smoke テストを書く** (`tests/test_install.py`)

```python
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
```

- [ ] **Step 3: テスト実行**

Run: `chmod +x install.sh && uv run pytest tests/test_install.py -v`
Expected: 3 PASS (Task 12 の hooks.json が未作成だと Step 2 のテストが cat で失敗する — その場合は先に Task 12 の hooks.json だけ作ってから戻る)

- [ ] **Step 4: Commit**

```bash
git add install.sh tests/test_install.py
git commit -m "feat: install.sh (rules/agents/hooks/codex の選択導入)"
```

---

### Task 12: plugin.json + hooks.json

**Files:**
- Create: `.claude-plugin/plugin.json`
- Create: `hooks/hooks.json`

**Interfaces:**
- Produces: Claude Code プラグインとしての一括導入経路。`${CLAUDE_PLUGIN_ROOT}` はプラグイン機構が展開する変数

- [ ] **Step 1: plugin.json を作成**

```json
{
  "name": "altairs-agent-dev-kit",
  "version": "0.1.0",
  "description": "AI エージェント開発標準 kit: skills / rules / hooks / agents を任意リポジトリへ",
  "author": {"name": "NEXTAltair"},
  "skills": "./skills/",
  "agents": "./agents/",
  "hooks": "./hooks/hooks.json"
}
```

- [ ] **Step 2: hooks/hooks.json を作成**

```json
{
  "hooks": {
    "PreToolUse": [
      {
        "matcher": "Bash",
        "hooks": [
          {"type": "command", "command": "/usr/bin/timeout 5s ${CLAUDE_PLUGIN_ROOT}/hooks/scripts/hook_pre_commands.py"},
          {"type": "command", "command": "/usr/bin/timeout 15s ${CLAUDE_PLUGIN_ROOT}/hooks/scripts/hook_pre_pr_submodule_check.py"}
        ]
      },
      {
        "matcher": "Edit|Write|MultiEdit",
        "hooks": [
          {"type": "command", "command": "/usr/bin/timeout 5s ${CLAUDE_PLUGIN_ROOT}/hooks/scripts/hook_pre_edit_worktree.py"}
        ]
      }
    ],
    "Stop": [
      {
        "matcher": "*",
        "hooks": [
          {"type": "command", "command": "/usr/bin/timeout 5s ${CLAUDE_PLUGIN_ROOT}/hooks/scripts/hook_response_monitor.py"}
        ]
      }
    ],
    "WorktreeCreate": [
      {
        "matcher": "*",
        "hooks": [
          {"type": "command", "command": "/usr/bin/timeout 120s ${CLAUDE_PLUGIN_ROOT}/hooks/scripts/hook_worktree_create.py"}
        ]
      }
    ]
  }
}
```

注意: plugin.json / hooks.json のスキーマは実装時に Claude Code 公式ドキュメント (code.claude.com/docs の plugins 節) を WebFetch で確認し、フィールド名が違えばそちらに合わせる。

- [ ] **Step 3: 検証と Commit**

Run: `python3 -c "import json; json.load(open('.claude-plugin/plugin.json')); json.load(open('hooks/hooks.json')); print('valid')"`
Expected: `valid`

```bash
git add .claude-plugin hooks/hooks.json
git commit -m "feat(plugin): Claude Code プラグインマニフェストと hook 配線"
```

---

### Task 13: docs (adoption.md / third-party-skills.md) + README

**Files:**
- Create: `docs/adoption.md`, `docs/third-party-skills.md`, `README.md`

- [ ] **Step 1: docs/adoption.md を書く**

必須内容:
1. 3 経路の導入手順 (プラグイン: marketplace add → plugin install / skills.sh: `npx skills add github:NEXTAltair/altairs-agent-dev-kit --skill <name>` / install.sh: clone して `./install.sh --target <repo> --all`)
2. プロジェクト層 override の書き方: `.claude/hooks/rules/pre_commands.json` (uv ガード等の有効化例)、`response_monitor.json` (NG ワード例 — LoRAIro の `hook_stop_words_rules.json` の内容を実例として転記)、`consistency.json` (required_env 宣言)
3. rules の追記ポイント (「プロジェクト固有」コメントの箇所に自分の具体値を書く)
4. プロジェクト固有スキルの実例として LoRAIro の `lorairo-qt-widget` / `lorairo-repository-pattern` / `lorairo-test-generator` / `lorairo-mem` / `lorairo-design-capture` へのリンク (github.com/NEXTAltair/LoRAIro の .agents/skills/)
5. `scripts/check_config_consistency.py` を導入先 CI / hook に組み込む方法

- [ ] **Step 2: docs/third-party-skills.md を書く**

LoRAIro の `skills-lock.json` (sourceType: github のエントリ 12 件) を転記した推奨インストール表:

| skill | source | install |
|---|---|---|
| python-error-handling ほか python-* 4 種 | wshobson/agents | `npx skills add github:wshobson/agents --skill <name>` |
| sql-optimization-patterns, database-migration | wshobson/agents | 同上 |
| vercel-* 5 種, web-design-guidelines, deploy-to-vercel | vercel-labs/agent-skills | `npx skills add github:vercel-labs/agent-skills --skill <name>` |

(正確な skill 名と source は `/workspaces/LoRAIro/skills-lock.json` を読んで転記する)

- [ ] **Step 3: README.md を書く**

構成: kit の目的 (1 段落) / 収録物一覧 (skills 13, rules 8, hooks 5, agents 10, codex) / 3 経路のクイックスタート / 設計原則 5 つ (spec から要約) / spec と plan へのリンク。

- [ ] **Step 4: Commit**

```bash
git add docs/ README.md
git commit -m "docs: 導入ガイド・サードパーティスキル一覧・README"
```

---

### Task 14: CI (GitHub Actions)

**Files:**
- Create: `.github/workflows/ci.yml`

- [ ] **Step 1: workflow を作成**

```yaml
name: CI
on:
  push:
    branches: [main]
  pull_request:

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v5
      - run: uv sync --dev
      - run: uv run pytest -v
      - run: uv run python scripts/lint_skills.py --dir skills
      - name: 汎用性 grep gate (kit 本体にプロジェクト固有文字列を残さない)
        run: |
          ! grep -rn "LoRAIro\|lorairo\|/workspaces/" \
            skills/ rules/ hooks/ agents/ codex/ scripts/ install.sh
```

- [ ] **Step 2: ローカルで各ステップ相当を実行して確認**

Run: `uv run pytest -v && uv run python scripts/lint_skills.py --dir skills && ! grep -rn "LoRAIro\|lorairo\|/workspaces/" skills/ rules/ hooks/ agents/ codex/ scripts/ install.sh`
Expected: 全て成功 (grep は「見つからない」= 成功)

- [ ] **Step 3: Commit & push**

```bash
git add .github/
git commit -m "ci: pytest + skills lint + 汎用性 grep gate"
git push origin main
```

push 後 `gh run watch` で CI green を確認。

---

## Self-Review 済み確認事項

- spec の全セクション (2層構造 / 3経路 / 収録物 / hook 汎用化 / 整合 lint / テスト / 決定事項) に対応するタスクが存在する
- LoRAIro 側の移行 (spec 第6節) は spec どおり本計画のスコープ外 (別フェーズ)
- Task 11 が Task 12 の hooks.json に依存する点は Task 11 Step 3 に明記済み (実行順を入れ替えてもよい)
- marketplace 登録 (プラグイン配布の最終形) は plugin.json 完成後に別途判断 — リポジトリ自体を `.claude-plugin/marketplace.json` 付き self-marketplace にするかは Task 12 実装時に公式ドキュメントを確認して決める
