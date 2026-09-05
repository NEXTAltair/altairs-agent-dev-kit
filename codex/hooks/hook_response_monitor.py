"""Codex entrypoint for the shared Stop policy."""

import sys
from pathlib import Path

root = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(root / "hooks"))
from bootstrap import launch

launch("hook_response_monitor.py", provider="codex", event="Stop", plugin=root)
