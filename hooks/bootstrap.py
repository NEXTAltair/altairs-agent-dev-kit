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


def superproject(checkout):
    output = subprocess.check_output(
        ["git", "-C", str(checkout), "rev-parse", "--show-superproject-working-tree"],
        text=True, encoding="utf-8", stderr=subprocess.PIPE, timeout=5,
    ).strip()
    return Path(output).resolve() if output else None


def roots():
    active = git_root(Path.cwd(), "--show-toplevel")
    # A submodule is part of the checkout that pins it, so climb to the outermost
    # superproject before looking for the lock: a lock the submodule carries for its own
    # standalone use never outranks the pinning checkout. Only Git-declared ownership is
    # followed: a linked worktree keeps its own tracked lock, and an unrelated repository
    # nested in the tree never borrows the policy of the directory above it.
    visited = {active}
    while True:
        owner = superproject(active)
        if owner is None:
            break
        if owner in visited:
            raise ValueError("submodule ownership cycle at " + str(owner))
        visited.add(owner)
        active = owner
    if not (active / LOCK).is_file():
        raise ValueError(LOCK + " not found in active checkout " + str(active)
                         + " (a bare `cd <owning checkout>` is permitted to leave a nested repository)")
    common = git_root(active, "--path-format=absolute", "--git-common-dir")
    if common.name != ".git" or not (common.parent / ".git").is_dir():
        raise ValueError("unsupported Git layout: shared checkout cannot be determined")
    return active, common.parent


BARE_CD_ARGUMENT = r"(?:[ \t]+(?:\"[^\"$`;&|<>\n]*\"|'[^'\n]*'|[^\s\"'$`;&|<>()]+))?[ \t]*$"
# Bash has only the `cd` builtin; PowerShell adds `Set-Location` and resolves names
# case-insensitively. Any other name could be an arbitrary executable or function.
BARE_CD_BY_TOOL = {
    "Bash": re.compile(r"^[ \t]*cd" + BARE_CD_ARGUMENT),
    "PowerShell": re.compile(r"^[ \t]*(?:cd|Set-Location)" + BARE_CD_ARGUMENT, re.IGNORECASE),
}


def is_bare_cd(payload, provider):
    if not isinstance(payload, dict) or not isinstance(payload.get("tool_input"), dict):
        return False
    tool_input = payload["tool_input"]
    if provider == "codex":
        # Codex omits tool_name, may carry the command in `cmd`, and runs the host shell.
        shell = "PowerShell" if os.name == "nt" else "Bash"
        command = tool_input.get("command") or tool_input.get("cmd")
    else:
        shell = payload.get("tool_name")
        command = tool_input.get("command")
    pattern = BARE_CD_BY_TOOL.get(shell)
    return pattern is not None and isinstance(command, str) and pattern.fullmatch(command) is not None


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


def failure(event, error, provider="claude"):
    reason = ("agent-kit runtime unavailable: " + str(error)
              + ". Restore the branch-pinned kit from the pinned kit checkout with"
              + " scripts/install_harness.py --runtime-only --target <checkout> (or the consumer's own restore command)."
              + " If an existing runtime is corrupt, stop hook sessions and move its directory aside first; see docs/hook-runtime.md.")
    print(reason, file=sys.stderr)
    # The runtime's own guards cannot run when startup failed. Read stdin only on this
    # failure path; successful consumer launches must receive the original stream unchanged.
    try:
        payload = json.load(sys.stdin)
    except (OSError, ValueError):
        payload = None
    if event == "PreToolUse":
        # A bare `cd` runs nothing the policy could judge, and it is the only way an agent
        # can leave a nested repository whose cwd caused this failure. Everything else is
        # denied: leaving stdout empty here hands the call to the normal permission flow.
        if is_bare_cd(payload, provider):
            return
        print(json.dumps({"hookSpecificOutput": {"hookEventName": event,
              "permissionDecision": "deny", "permissionDecisionReason": reason}}))
    elif event == "Stop":
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
        failure(event, error, provider)
        return
    runpy.run_path(str(entry), run_name="__main__")
