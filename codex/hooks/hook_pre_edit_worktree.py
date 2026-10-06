"""Codex entrypoint for the shared-checkout edit gate on apply_patch."""

import sys
from pathlib import Path

root = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(root / "hooks"))
from bootstrap import launch

launch("hook_pre_edit_worktree.py", provider="codex", plugin=root)
