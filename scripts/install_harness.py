"""Install portable hook runtimes; never overwrite project policy overrides."""

import argparse
import base64
import hashlib
import json
import os
import shutil
import sys
import tempfile
from pathlib import Path

KIT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(KIT / "hooks"))
from bootstrap import LOCK, REQUIRED, git_root, validate


def copy_file(source: Path, destination: Path, force: bool) -> None:
    if destination.exists() and not force:
        print(f"SKIP (exists): {destination}")
        return
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, destination)
    print(f"INSTALL: {destination}")


def write_config(path: Path, content: str, force: bool) -> None:
    if path.exists() and not force:
        path = path.with_name(path.name + ".new")
        if path.exists():
            raise FileExistsError(f"Review existing proposal before reinstalling: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    print(f"INSTALL: {path}")


def claude_wiring() -> dict:
    config = json.loads((KIT / "hooks/hooks.json").read_text(encoding="utf-8"))
    for event, groups in config["hooks"].items():
        for group in groups:
            for hook in group["hooks"]:
                hook["command"] = "python" if os.name == "nt" else "python3"
                script = hook["args"][-2]
                hook["args"] = ["-I", "-X", "utf8", "-c", hook_bootstrap(script, event=event)]
    return config


def hook_bootstrap(script: str, provider: str = "claude", event: str = "PreToolUse",
                   consumer: bool = False) -> str:
    """Embed kit-owned stdlib startup; no installed module is needed to find runtime.

    Consumer hooks use the same contract with consumer=True and an active-root-relative path.
    Compress to stay below Windows command-line limits, with shell-independent ASCII quoting.
    """
    import zlib
    source = (KIT / "hooks/bootstrap.py").read_text(encoding="utf-8")
    source += f"\nlaunch({script!r}, {provider!r}, {event!r}, consumer={consumer!r})\n"
    encoded = base64.b64encode(zlib.compress(source.encode())).decode()
    return f"import base64,zlib; exec(zlib.decompress(base64.b64decode('{encoded}')))"


def codex_wiring() -> dict:
    events = {}
    for event, script in (("PreToolUse", "hook_pre_commands"), ("Stop", "hook_response_monitor")):
        bootstrap = hook_bootstrap(f"{script}.py", provider="codex", event=event)
        group = {
            "hooks": [
                {
                    "type": "command",
                    "command": f'python3 -I -X utf8 -c "{bootstrap}"',
                    "commandWindows": f'python -I -X utf8 -c "{bootstrap}"',
                    "timeout": 5,
                }
            ]
        }
        if event == "PreToolUse":
            group["matcher"] = "Bash|PowerShell"
        events[event] = [group]
    return {"hooks": events}


def runtime_lock() -> dict:
    paths = sorted(REQUIRED | {"hooks/bootstrap.py"})
    files = {name: hashlib.sha256((KIT / name).read_bytes()).hexdigest() for name in paths}
    digest = hashlib.sha256(json.dumps(files, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    return {"schema": 1, "runtime": digest, "files": files}


def atomic_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=".lock-", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(data, stream, indent=2)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        Path(temporary).unlink(missing_ok=True)


def install_runtime(target: Path, force: bool = False) -> dict:
    """Publish a verified immutable runtime, then atomically pin this checkout.

    An interrupted/concurrent copy never exposes a partial runtime. Existing IDs
    are never overwritten, even with force; force only allows changing the branch pin.
    """
    if not target.is_dir():
        raise ValueError("--target must be an existing project directory")
    lock = runtime_lock()
    lock_path = target / LOCK
    if lock_path.exists() and not force:
        if json.loads(lock_path.read_text(encoding="utf-8")) != lock:
            raise ValueError("source differs from branch lock; restore its pinned source or use --force to repin")
    # Installation into a non-Git staging directory is supported. Execution requires Git.
    shared = target
    if (target / ".git").exists():
        common = git_root(target, "--path-format=absolute", "--git-common-dir")
        if common.name != ".git":
            raise ValueError("unsupported Git layout")
        shared = common.parent
    store = shared / ".agent-kit/runtimes"
    store.mkdir(parents=True, exist_ok=True)
    destination = store / lock["runtime"]
    if destination.exists():
        validate(destination, lock)
    else:
        with tempfile.TemporaryDirectory(prefix=".staging-", dir=store) as directory:
            stage = Path(directory) / "runtime"
            stage.mkdir()
            for name in lock["files"]:
                output = stage / name
                output.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(KIT / name, output)
            validate(stage, lock)
            try:
                stage.rename(destination)
            except OSError:
                # A concurrent installer may have published this exact ID first.
                validate(destination, lock)
    # Serialize branch pin updates separately from shared runtime publication.
    # A killed process may leave this directory; do not steal a possibly live lock.
    guard = target / ".agent-kit/.pin-update"
    guard.parent.mkdir(parents=True, exist_ok=True)
    try:
        guard.mkdir()
    except FileExistsError as error:
        raise RuntimeError("pin update in progress; see docs/hook-runtime.md before clearing .pin-update") from error
    try:
        if lock_path.exists() and not force:
            if json.loads(lock_path.read_text(encoding="utf-8")) != lock:
                raise ValueError("source differs from branch lock; restore its pinned source or use --force to repin")
        atomic_json(lock_path, lock)
    finally:
        guard.rmdir()
    return lock


def install(target: Path, force: bool = False, codex: bool = False) -> dict:
    install_runtime(target, force)
    write_config(target / ".codex/hooks.json", json.dumps(codex_wiring(), indent=2) + "\n", force)
    if codex:
        # POSIX spelling is also a valid Windows absolute path and avoids TOML escapes.
        template = (KIT / "codex/config.toml.template").read_text(encoding="utf-8")
        write_config(
            target / ".codex/config.toml", template.replace("{{PROJECT_ROOT}}", target.as_posix()), force
        )
        for source in (KIT / "codex/agents").glob("*.toml"):
            copy_file(source, target / ".codex/agents" / source.name, force)
    return claude_wiring()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--target", type=Path, required=True)
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--codex", action="store_true", help="Also install local Codex config and agents")
    parser.add_argument("--runtime-only", action="store_true", help="Restore runtime without changing event registrations")
    args = parser.parse_args()
    if args.runtime_only:
        install_runtime(args.target.resolve(), args.force)
        return
    wiring = install(args.target.resolve(), args.force, args.codex)
    print("Merge this hooks object into .claude/settings.json:")
    print(json.dumps(wiring, indent=2))


if __name__ == "__main__":
    main()
