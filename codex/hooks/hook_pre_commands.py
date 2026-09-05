"""Codex entrypoint for the shared command policy and current JSON contract."""

import sys
from pathlib import Path

root = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(root / "hooks"))
from bootstrap import launch

launch("hook_pre_commands.py", provider="codex", plugin=root)
