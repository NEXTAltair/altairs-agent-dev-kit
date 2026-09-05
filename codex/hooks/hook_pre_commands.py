"""Codex entrypoint for the shared command policy and current JSON contract."""

import os
import runpy
import sys
from pathlib import Path

root = Path(__file__).resolve().parents[2]
runtime = root / ".claude/hooks"
if not runtime.is_dir():
    runtime = root / "hooks/scripts"
os.environ["AGENT_KIT_PROVIDER"] = "codex"
sys.path.insert(0, str(runtime))
runpy.run_path(str(runtime / "hook_pre_commands.py"), run_name="__main__")
