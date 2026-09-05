"""Install portable hook runtimes; never overwrite project policy overrides."""

import argparse
import json
import shutil
from pathlib import Path

KIT = Path(__file__).resolve().parents[1]


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
    for groups in config["hooks"].values():
        for group in groups:
            for hook in group["hooks"]:
                script = hook["args"][-1].rsplit("/", 1)[-1]
                hook["args"] = ["-X", "utf8", "-c", hook_bootstrap(f".claude/hooks/{script}")]
    return config


def hook_bootstrap(relative: str) -> str:
    """Use the active checkout's rules even when runtime is installed only in main."""
    return (
        "import os,pathlib,runpy,subprocess,sys; "
        "r=pathlib.Path(subprocess.check_output(['git','rev-parse','--show-toplevel'],"
        "text=True,encoding='utf-8').strip()); "
        "os.environ['AGENT_KIT_PROJECT_DIR']=str(r); "
        f"p=r/'{relative}'; "
        "p=p if p.is_file() else pathlib.Path(subprocess.check_output("
        "['git','rev-parse','--path-format=absolute','--git-common-dir'],"
        f"text=True,encoding='utf-8').strip()).parent/'{relative}'; "
        "sys.path.insert(0,str(p.parent)); runpy.run_path(str(p),run_name='__main__')"
    )


def codex_wiring() -> dict:
    events = {}
    for event, script in (("PreToolUse", "hook_pre_commands"), ("Stop", "hook_response_monitor")):
        bootstrap = hook_bootstrap(f".codex/hooks/{script}.py")
        group = {
            "hooks": [
                {
                    "type": "command",
                    "command": f'python3 -X utf8 -c "{bootstrap}"',
                    "commandWindows": f'python -X utf8 -c "{bootstrap}"',
                    "timeout": 5,
                }
            ]
        }
        if event == "PreToolUse":
            group["matcher"] = "Bash|PowerShell"
        events[event] = [group]
    return {"hooks": events}


def install_runtime(target: Path, force: bool = False) -> None:
    """Restore kit-owned files only, leaving all event registrations untouched."""
    if not target.is_dir():
        raise ValueError("--target must be an existing project directory")
    for source in (KIT / "hooks/scripts").glob("*.py"):
        copy_file(source, target / ".claude/hooks" / source.name, force)
    for source in (KIT / "hooks/rules").glob("*.default.json"):
        copy_file(source, target / ".claude/hooks/rules" / source.name, force)
    for source in (KIT / "codex/hooks").glob("*.py"):
        copy_file(source, target / ".codex/hooks" / source.name, force)


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
    args = parser.parse_args()
    wiring = install(args.target.resolve(), args.force, args.codex)
    print("Merge this hooks object into .claude/settings.json:")
    print(json.dumps(wiring, indent=2))


if __name__ == "__main__":
    main()
