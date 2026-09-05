"""Stdlib-only launch contract, embedded in registrations before any kit import."""

import hashlib
import json
import os
from pathlib import Path
import re
import runpy
import subprocess
import sys
import types

LOCK = ".agent-kit/hooks.lock.json"
REQUIRED = {
    "hooks/scripts/hook_common.py",
    "hooks/scripts/hook_pre_commands.py",
    "hooks/scripts/hook_pre_edit_worktree.py",
    "hooks/scripts/hook_pre_pr_submodule_check.py",
    "hooks/scripts/hook_response_monitor.py",
    "hooks/scripts/hook_worktree_create.py",
    "hooks/rules/pre_commands.default.json",
    "hooks/rules/pre_edit_worktree.default.json",
    "hooks/rules/pre_pr_submodule_check.default.json",
    "hooks/rules/response_monitor.default.json",
}


def git_root(cwd, *args):
    return Path(subprocess.check_output(
        ["git", "-C", str(cwd), "rev-parse", *args],
        text=True, encoding="utf-8", stderr=subprocess.PIPE, timeout=5,
    ).strip()).resolve()


def roots():
    active = git_root(Path.cwd(), "--show-toplevel")
    common = git_root(active, "--path-format=absolute", "--git-common-dir")
    if common.name != ".git" or not (common.parent / ".git").is_dir():
        raise ValueError("unsupported Git layout: shared checkout cannot be determined")
    return active, common.parent


def validate(runtime, lock):
    if lock.get("schema") != 1 or not re.fullmatch(r"[0-9a-f]{64}", lock.get("runtime", "")):
        raise ValueError("invalid runtime lock")
    files = lock.get("files")
    if not isinstance(files, dict) or not REQUIRED.issubset(files):
        raise ValueError("runtime lock is missing required implementation/default files")
    digest = hashlib.sha256(json.dumps(files, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    if digest != lock["runtime"]:
        raise ValueError("runtime lock digest mismatch")
    for name, expected in files.items():
        path = runtime / name
        if not path.resolve().is_relative_to(runtime.resolve()) or Path(name).is_absolute():
            raise ValueError("invalid runtime file path")
        if hashlib.sha256(path.read_bytes()).hexdigest() != expected:
            raise ValueError("runtime file mismatch: " + name)
    return runtime


def failure(event, error):
    reason = ("agent-kit runtime unavailable: " + str(error)
              + ". Restore the branch-pinned kit using scripts/install_harness.py --runtime-only --target <checkout>."
              + " If an existing runtime is corrupt, stop hook sessions and move its directory aside first; see docs/hook-runtime.md.")
    print(reason, file=sys.stderr)
    if event == "PreToolUse":
        print(json.dumps({"hookSpecificOutput": {"hookEventName": event,
              "permissionDecision": "deny", "permissionDecisionReason": reason}}))
    elif event == "Stop":
        # The runtime's own recursion guard cannot run when startup failed.
        # Read stdin only on this failure path; successful consumer launches
        # must receive the original stream unchanged.
        try:
            payload = json.load(sys.stdin)
        except (OSError, ValueError):
            payload = None
        if isinstance(payload, dict) and payload.get("stop_hook_active"):
            return
        print(json.dumps({"decision": "block", "reason": reason}))
    else:
        raise SystemExit(2)


def launch(script, provider="claude", event="PreToolUse", consumer=False, plugin=None):
    try:
        active, shared = roots()
        lock = json.loads((active / LOCK).read_text(encoding="utf-8"))
        # Validate even the ID before constructing a path from it.
        if not isinstance(lock, dict) or not re.fullmatch(r"[0-9a-f]{64}", lock.get("runtime", "")):
            raise ValueError("invalid runtime lock")
        candidates = [active / ".agent-kit/runtimes" / lock["runtime"],
                      shared / ".agent-kit/runtimes" / lock["runtime"]]
        if plugin:
            candidates.insert(0, Path(plugin))
        errors = []
        runtime = None
        for candidate in candidates:
            try:
                runtime = validate(candidate, lock)
                break
            except (OSError, ValueError, TypeError) as error:
                errors.append(str(error))
        if runtime is None:
            raise ValueError("; ".join(errors))
        if consumer:
            entry = active / script
            if not entry.resolve().is_relative_to(active) or not entry.is_file():
                raise ValueError("consumer hook must exist in the active checkout")
        else:
            relative = "hooks/scripts/" + script
            if relative not in lock["files"]:
                raise ValueError("hook is not part of the pinned runtime")
            entry = runtime / relative
        os.environ["AGENT_KIT_PROJECT_DIR"] = str(active)
        os.environ["AGENT_KIT_PROVIDER"] = provider
        sys.dont_write_bytecode = True
        # Import the verified source, never a stale/unlisted bytecode cache.
        common_path = runtime / "hooks/scripts/hook_common.py"
        common = types.ModuleType("hook_common")
        common.__file__ = str(common_path)
        exec(compile(common_path.read_bytes(), str(common_path), "exec"), common.__dict__)
        sys.modules["hook_common"] = common
        sys.path.insert(0, str(runtime / "hooks/scripts"))
    except (OSError, ValueError, TypeError, subprocess.SubprocessError) as error:
        failure(event, error)
        return
    runpy.run_path(str(entry), run_name="__main__")
