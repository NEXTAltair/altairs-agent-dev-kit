#!/usr/bin/env python3
"""agent-kit: skills / rules / agents を複数のエージェントハーネスへ導入する (stdlib のみ)。

対応ハーネス: claude (Claude Code) / codex (Codex CLI) / antigravity (Google Antigravity) / openclaw。
各ハーネスが実際に読む場所へ、kit.json の分類 (profile と推奨 scope) に従って配置する。

    python3 scripts/agent_kit.py install --scope global
    python3 scripts/agent_kit.py install --scope project --target <repo> [--profile python,sql]
    python3 scripts/agent_kit.py status  --scope project --target <repo>
    python3 scripts/agent_kit.py uninstall --scope project --target <repo>
    python3 scripts/agent_kit.py list

配置先と根拠は docs/harness-matrix.md、設計判断は docs/decisions/0011 を参照。
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

KIT = Path(__file__).resolve().parents[1]
HARNESSES = ("claude", "codex", "antigravity", "openclaw")
COMPONENTS = ("rules", "agents", "skills", "hooks")
BEGIN = "<!-- agent-kit:begin -->"
END = "<!-- agent-kit:end -->"
BLOCK = re.compile(re.escape(BEGIN) + r".*?" + re.escape(END) + r"\n?", re.DOTALL)
# PATH 上の CLI 名と、ハーネスが自分で作る設定ディレクトリ (自動検出用)。
DETECT = {
    "claude": ("claude", ".claude"),
    "codex": ("codex", ".codex"),
    "antigravity": ("agy", ".gemini"),
    "openclaw": ("openclaw", ".openclaw"),
}


class KitError(Exception):
    """何も書き込まずに止めるべき入力・環境の誤り。"""


@dataclass
class Context:
    scope: str
    root: Path                      # project: 導入先 repository / global: home
    harnesses: tuple[str, ...]
    profiles: tuple[str, ...]
    standalone: bool = False
    force: bool = False
    dry_run: bool = False
    codex_home: Path | None = None
    manifest: dict = field(default_factory=dict)

    @property
    def state_path(self) -> Path:
        base = ".agent-kit" if self.scope == "project" else ".agents/agent-kit"
        return self.root / base / "install.json"

    def selected(self, kind: str) -> list[str]:
        names = []
        for name, meta in self.manifest[kind].items():
            if self.scope == "global":
                chosen = meta["scope"] == "global"
            else:
                chosen = meta["profile"] in self.profiles and (self.standalone or meta["scope"] == "project")
            if chosen:
                names.append(name)
        return sorted(names)


def kit_version() -> str:
    return json.loads((KIT / ".claude-plugin/plugin.json").read_text(encoding="utf-8"))["version"]


def load_manifest() -> dict:
    return json.loads((KIT / "kit.json").read_text(encoding="utf-8"))


# ---------------------------------------------------------------- 配置先 (docs/harness-matrix.md)

def rules_dirs(ctx: Context) -> dict[Path, str]:
    """rule の配置先 → 形式。canonical は Antigravity の trigger frontmatter 付き。"""
    out: dict[Path, str] = {}
    project = ctx.scope == "project"
    for harness in ctx.harnesses:
        if harness == "claude":
            out[ctx.root / ".claude/rules"] = "claude"
        elif harness == "antigravity":
            out[ctx.root / (".agents/rules" if project else ".gemini/config/rules")] = "canonical"
        elif harness == "codex" or (harness == "openclaw" and project):
            # 専用の rules 置き場を持たないハーネスは AGENTS.md の索引から .agents/rules を読む。
            out[ctx.root / ".agents/rules"] = "canonical"
    return out


def agents_dirs(ctx: Context) -> dict[Path, str]:
    """agent 定義の配置先 → 取得元ディレクトリ (kit 相対)。OpenClaw の agent は OpenClaw 側の定義に従う。"""
    out: dict[Path, str] = {}
    project = ctx.scope == "project"
    for harness in ctx.harnesses:
        if harness == "claude":
            out[ctx.root / ".claude/agents"] = "agents"
        elif harness == "codex":
            base = ctx.root / ".codex" if project or ctx.codex_home is None else ctx.codex_home
            out[base / "agents"] = "codex/agents"
        elif harness == "antigravity":
            out[ctx.root / (".agents/agents" if project else ".gemini/config/agents")] = "antigravity/agents"
    return out


def index_file(ctx: Context) -> Path | None:
    """rule の索引を書き込む指示ファイル。rules を自動で読まないハーネスがあるときだけ使う."""
    if ctx.scope == "project":
        return ctx.root / "AGENTS.md" if {"codex", "openclaw"} & set(ctx.harnesses) else None
    if "codex" in ctx.harnesses:
        return (ctx.codex_home or ctx.root / ".codex") / "AGENTS.md"
    return None


def skill_agents(ctx: Context) -> list[str]:
    """skills.sh へ渡す agent 名。実体は .agents/skills (Codex / Antigravity / OpenClaw が直接読む)。"""
    agents = ["codex"]
    if "claude" in ctx.harnesses:
        agents.append("claude-code")
    if "antigravity" in ctx.harnesses and ctx.scope == "global":
        agents.append("antigravity")  # global は ~/.gemini/config/skills への symlink が要る
    return agents


# ---------------------------------------------------------------- 内容の生成

def render_rule(name: str, meta: dict, fmt: str) -> str:
    body = (KIT / "rules" / f"{name}.md").read_text(encoding="utf-8")
    description = json.dumps(meta["description"], ensure_ascii=False)
    globs = meta.get("globs", [])
    if fmt == "claude":
        if meta["activation"] != "glob":
            return body
        paths = "".join(f"  - {json.dumps(glob)}\n" for glob in globs)
        return f"---\npaths:\n{paths}---\n\n{body}"
    trigger = {"always": "always_on", "on-demand": "model_decision", "glob": "glob"}[meta["activation"]]
    head = f"---\ntrigger: {trigger}\ndescription: {description}\n"
    if trigger == "glob":
        head += f"globs: {json.dumps(', '.join(globs))}\n"
    return head + "---\n\n" + body


def render_index(ctx: Context, rules: list[str], target: Path) -> str:
    prefix = ".agents/rules" if ctx.scope == "project" else "~/.agents/rules"
    groups: dict[str, list[str]] = {"always": [], "other": []}
    for name in rules:
        meta = ctx.manifest["rules"][name]
        path = f"{prefix}/{name}.md"
        link = f"[{path}]({path})" if ctx.scope == "project" else f"`{path}`"
        line = f"- {link} — {meta['description']}"
        if meta["activation"] == "glob":
            line += " (対象: " + ", ".join(f"`{glob}`" for glob in meta["globs"]) + ")"
        groups["always" if meta["activation"] == "always" else "other"].append(line)
    lines = [
        BEGIN,
        "## Agent kit rules",
        "",
        f"altairs-agent-dev-kit {kit_version()} が管理する区画。手で編集せず `agent_kit.py install` で更新する。",
        "Claude Code と Antigravity は同じ内容を自分の rules ディレクトリから読み込む。",
        "それ以外のエージェントは次の一覧に従ってファイルを読む。",
    ]
    if groups["always"]:
        lines += ["", "作業を始める前に必ず読む:", *groups["always"]]
    if groups["other"]:
        lines += ["", "該当する作業の前に読む:", *groups["other"]]
    return "\n".join(lines + [END]) + "\n"


def plan_files(ctx: Context, components: set[str]) -> dict[Path, bytes]:
    files: dict[Path, bytes] = {}
    if "rules" in components:
        for directory, fmt in rules_dirs(ctx).items():
            for name in ctx.selected("rules"):
                files[directory / f"{name}.md"] = render_rule(name, ctx.manifest["rules"][name], fmt).encode()
    if "agents" in components:
        for directory, source in agents_dirs(ctx).items():
            for name in ctx.selected("agents"):
                matches = list((KIT / source).glob(f"{name}.*"))
                if matches:  # Codex 版を持たない agent (library-research) は飛ばす
                    files[directory / matches[0].name] = matches[0].read_bytes()
    return files


# ---------------------------------------------------------------- 書き込みと所有の記録

def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def relative(ctx: Context, path: Path) -> str:
    try:
        return path.relative_to(ctx.root).as_posix()
    except ValueError:
        return path.as_posix()  # CODEX_HOME が root の外にある場合


def load_state(ctx: Context) -> dict:
    try:
        return json.loads(ctx.state_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"schema": 1, "files": {}}


def apply_files(ctx: Context, files: dict[Path, bytes], state: dict) -> None:
    """kit が置いて変更されていないファイルだけを更新する。利用者が変えたファイルは --force まで残す。"""
    recorded = state["files"]
    for path, data in sorted(files.items()):
        key, new = relative(ctx, path), digest(data)
        current = digest(path.read_bytes()) if path.is_file() else None
        if current == new:
            action = "UNCHANGED"
        elif current is None:
            action = "INSTALL"
        elif recorded.get(key) == current or ctx.force:
            action = "UPDATE"
        else:
            print(f"SKIP (kit 以外の変更あり、--force で上書き): {path}")
            continue
        if action != "UNCHANGED":
            print(f"{action}: {path}")
            if not ctx.dry_run:
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(data)
        recorded[key] = new


def apply_index(ctx: Context, components: set[str], state: dict) -> None:
    target = index_file(ctx)
    rules = ctx.selected("rules") if "rules" in components else []
    if target is None or not rules:
        return
    block = render_index(ctx, rules, target)
    text = target.read_text(encoding="utf-8") if target.is_file() else ""
    if BLOCK.search(text):
        updated = BLOCK.sub(lambda _: block, text, count=1)
    else:
        updated = (text.rstrip("\n") + "\n\n" if text.strip() else "") + block
    if updated != text:
        print(f"{'UPDATE' if text else 'INSTALL'} (agent-kit 区画): {target}")
        if not ctx.dry_run:
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(updated, encoding="utf-8", newline="\n")
    state["index"] = relative(ctx, target)
    if ctx.scope == "project" and "claude" in ctx.harnesses and any(
            (ctx.root / name).is_file() for name in ("CLAUDE.md", ".claude/CLAUDE.md")):
        print("NOTE: CLAUDE.md がある repository では Claude Code は AGENTS.md を読まない。"
              "rules は .claude/rules/ から読み込まれる。")


def skill_source(explicit: str | None) -> str:
    if explicit:
        return str(Path(explicit).resolve()) if Path(explicit).is_dir() else explicit
    try:
        tag = subprocess.check_output(["git", "-C", str(KIT), "describe", "--tags", "--exact-match", "HEAD"],
                                      text=True, stderr=subprocess.DEVNULL).strip()
        origin = subprocess.check_output(["git", "-C", str(KIT), "remote", "get-url", "origin"],
                                         text=True, stderr=subprocess.DEVNULL).strip()
    except (subprocess.CalledProcessError, FileNotFoundError) as error:
        raise KitError("skills はリリースタグの checkout から導入する。未公開の変更を使う場合は"
                       " --skill-source <kit のローカルパス> を指定する") from error
    match = re.fullmatch(r"(?:https://github\.com/|git@github\.com:)([^/]+)/(.+?)(?:\.git)?", origin)
    if not match:
        raise KitError("GitHub origin が無い。--skill-source <github:owner/repo#ref またはローカルパス> を指定する")
    return f"github:{match[1]}/{match[2]}#{tag}"


def install_skills(ctx: Context, source: str | None, state: dict) -> None:
    wanted = ctx.selected("skills")
    canonical = ctx.root / ".agents/skills"
    names = [name for name in wanted if ctx.force or not (canonical / name).exists()]
    for name in sorted(set(wanted) - set(names)):
        print(f"SKIP (exists): skill {name}")
    if not names:
        return
    command = ["npx", "--yes", "skills@1", "add", skill_source(source), "--skill", *names,
               "--agent", *skill_agents(ctx), "-y"]
    if ctx.scope == "global":
        command.append("-g")
    print("RUN: " + " ".join(command))
    if ctx.dry_run:
        return
    if shutil.which("npx") is None:
        raise KitError("skills の導入には Node.js (npx) が必要。--components で skills を外すか Node.js を導入する")
    env = dict(os.environ)
    if ctx.scope == "global":
        env["HOME"] = env["USERPROFILE"] = str(ctx.root)
    subprocess.run(command, cwd=ctx.root, env=env, check=True)
    state["skills"] = sorted(set(state.get("skills", [])) | set(names))


def install_hooks(ctx: Context) -> None:
    if ctx.scope != "project":
        raise KitError("hooks は project scope 専用 (runtime を checkout ごとに固定するため)")
    if not {"claude", "codex"} & set(ctx.harnesses):
        print("NOTE: hooks の配線は claude / codex のみ。他のハーネスは docs/harness-matrix.md を参照")
        return
    sys.path.insert(0, str(KIT / "scripts"))
    import install_harness
    try:
        install_harness.require_git_checkout(ctx.root)
        if ctx.dry_run:
            print(f"RUN: install_harness.install({ctx.root})")
            return
        wiring = install_harness.install(ctx.root, ctx.force)
    except (ValueError, RuntimeError, FileExistsError) as error:
        raise KitError(str(error)) from error
    if "claude" in ctx.harnesses:
        print("Merge this hooks object into .claude/settings.json:")
        print(json.dumps(wiring, indent=2))


# ---------------------------------------------------------------- コマンド

def detect_harnesses(root: Path, home: Path) -> tuple[str, ...]:
    found = [name for name, (cli, directory) in DETECT.items()
             if shutil.which(cli) or (home / directory).is_dir() or (root / directory).is_dir()]
    return tuple(found)


def detect_profiles(root: Path) -> tuple[str, ...]:
    profiles = ["core"]
    pyproject = root / "pyproject.toml"
    if pyproject.is_file() or (root / "setup.py").is_file():
        profiles.append("python")
        text = pyproject.read_text(encoding="utf-8", errors="replace").lower() if pyproject.is_file() else ""
        profiles += [name for name, needle in (("qt", "pyside"), ("sql", "sqlalchemy")) if needle in text]
    if (root / "package.json").is_file() or (root / "tsconfig.json").is_file():
        profiles.append("typescript")
    return tuple(profiles)


def build_context(args: argparse.Namespace) -> Context:
    manifest = load_manifest()
    home = (args.home or Path.home()).resolve()
    if args.scope == "project":
        if args.target is None or not args.target.is_dir():
            raise KitError("--scope project には --target <既存のディレクトリ> が必要")
        root = args.target.resolve()
    else:
        root = home
    if args.harness == "auto":
        harnesses = detect_harnesses(root, home)
        if not harnesses and args.command == "install":
            raise KitError("ハーネスを検出できない。--harness claude,codex,antigravity,openclaw から指定する")
        harnesses = harnesses or HARNESSES
    else:
        harnesses = tuple(dict.fromkeys(args.harness.split(",")))
        unknown = set(harnesses) - set(HARNESSES)
        if unknown:
            raise KitError(f"未対応のハーネス: {', '.join(sorted(unknown))}")
    if args.profile == "auto":
        profiles = detect_profiles(root) if args.scope == "project" else ("core",)
    elif args.profile == "all":
        profiles = tuple(manifest["profiles"])
    else:
        profiles = tuple(dict.fromkeys(["core", *args.profile.split(",")]))
        unknown = set(profiles) - set(manifest["profiles"])
        if unknown:
            raise KitError(f"未定義の profile: {', '.join(sorted(unknown))}")
    codex_home = None
    if args.home is None and os.environ.get("CODEX_HOME"):
        codex_home = Path(os.environ["CODEX_HOME"]).resolve()
    return Context(args.scope, root, harnesses, profiles, standalone=args.standalone, force=args.force,
                   dry_run=args.dry_run, codex_home=codex_home, manifest=manifest)


def parse_components(value: str, scope: str) -> set[str]:
    if value == "all":
        return set(COMPONENTS) - ({"hooks"} if scope == "global" else set())
    components = set(value.split(","))
    unknown = components - set(COMPONENTS)
    if unknown:
        raise KitError(f"未対応の component: {', '.join(sorted(unknown))}")
    return components


def command_install(args: argparse.Namespace) -> None:
    ctx = build_context(args)
    components = parse_components(args.components, ctx.scope)
    print(f"scope={ctx.scope} root={ctx.root} harness={','.join(ctx.harnesses)} profile={','.join(ctx.profiles)}")
    if "python" in ctx.profiles and shutil.which("uv") is None:
        print("WARN: python profile の rules / hooks は uv を前提にしているが、uv が PATH に無い")
    state = load_state(ctx)
    apply_files(ctx, plan_files(ctx, components), state)
    apply_index(ctx, components, state)
    if "skills" in components:
        install_skills(ctx, args.skill_source, state)
    if "hooks" in components:
        install_hooks(ctx)
    state.update(version=kit_version(), scope=ctx.scope, harnesses=list(ctx.harnesses), profiles=list(ctx.profiles))
    if not ctx.dry_run:
        ctx.state_path.parent.mkdir(parents=True, exist_ok=True)
        ctx.state_path.write_text(json.dumps(state, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print("DONE (dry-run)" if ctx.dry_run else "DONE")


def resolve(ctx: Context, key: str) -> Path:
    return Path(key) if Path(key).is_absolute() else ctx.root / key


def command_uninstall(args: argparse.Namespace) -> None:
    ctx = build_context(args)
    state = load_state(ctx)
    for key, recorded in sorted(state["files"].items()):
        path = resolve(ctx, key)
        if not path.is_file():
            continue
        if digest(path.read_bytes()) != recorded and not ctx.force:
            print(f"KEEP (変更あり): {path}")
            continue
        print(f"REMOVE: {path}")
        if not ctx.dry_run:
            path.unlink()
    if state.get("index"):
        target = resolve(ctx, state["index"])
        text = target.read_text(encoding="utf-8") if target.is_file() else ""
        if BLOCK.search(text):
            print(f"REMOVE (agent-kit 区画): {target}")
            if not ctx.dry_run:
                remaining = BLOCK.sub("", text, count=1).rstrip("\n")
                target.write_text(remaining + "\n", encoding="utf-8", newline="\n") if remaining else target.unlink()
    if state.get("skills"):
        print("NOTE: skills は skills.sh の管理下。削除は `npx skills remove "
              + ("-g " if ctx.scope == "global" else "") + " ".join(state["skills"]) + "`")
    if not ctx.dry_run and ctx.state_path.is_file():
        ctx.state_path.unlink()
    print("DONE (dry-run)" if ctx.dry_run else "DONE")


def command_status(args: argparse.Namespace) -> None:
    ctx = build_context(args)
    state = load_state(ctx)
    print(f"scope={ctx.scope} root={ctx.root}")
    print(f"detected harnesses: {', '.join(detect_harnesses(ctx.root, (args.home or Path.home()).resolve())) or '-'}")
    if not state["files"] and "version" not in state:
        print("agent-kit: 未導入")
        return
    print(f"installed: kit {state.get('version')} (current {kit_version()})"
          f" harness={','.join(state.get('harnesses', []))} profile={','.join(state.get('profiles', []))}")
    counts = {"ok": 0, "modified": 0, "missing": 0}
    for key, recorded in sorted(state["files"].items()):
        path = resolve(ctx, key)
        kind = "missing" if not path.is_file() else "ok" if digest(path.read_bytes()) == recorded else "modified"
        counts[kind] += 1
        if kind != "ok":
            print(f"  {kind}: {path}")
    print("files: " + ", ".join(f"{kind}={count}" for kind, count in counts.items()))
    for name in state.get("skills", []):
        if not (ctx.root / ".agents/skills" / name / "SKILL.md").is_file():
            print(f"  missing skill: {name}")


def command_list(_: argparse.Namespace) -> None:
    manifest = load_manifest()
    for kind in ("skills", "rules", "agents"):
        print(f"[{kind}]")
        for name, meta in sorted(manifest[kind].items(), key=lambda item: (item[1]["scope"], item[1]["profile"], item[0])):
            print(f"  {meta['scope']:<8} {meta['profile']:<7} {name}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    commands = parser.add_subparsers(dest="command", required=True)
    for name, handler in (("install", command_install), ("uninstall", command_uninstall), ("status", command_status)):
        sub = commands.add_parser(name)
        sub.set_defaults(handler=handler)
        sub.add_argument("--scope", choices=("project", "global"), required=True)
        sub.add_argument("--target", type=Path, help="project scope の導入先 repository")
        sub.add_argument("--home", type=Path, help="home ディレクトリを差し替える (検証用)")
        sub.add_argument("--harness", default="auto", help="auto または claude,codex,antigravity,openclaw")
        sub.add_argument("--profile", default="auto", help="auto / all / python,typescript,qt,sql (core は常に含む)")
        sub.add_argument("--standalone", action="store_true",
                         help="project scope で global 向けの部品も repository に入れる (global 導入の無い環境向け)")
        sub.add_argument("--force", action="store_true", help="利用者が変更したファイル・既存 skill も上書きする")
        sub.add_argument("--dry-run", action="store_true", help="書き込まずに予定だけ表示する")
        if name == "install":
            sub.add_argument("--components", default="rules,agents,skills",
                             help="rules,agents,skills,hooks から選ぶ。all は scope で使えるものすべて")
            sub.add_argument("--skill-source", help="skill の導入元 (github:owner/repo#ref または kit のローカルパス)")
    commands.add_parser("list").set_defaults(handler=command_list)
    args = parser.parse_args(argv)
    try:
        args.handler(args)
    except KitError as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 1
    except subprocess.CalledProcessError as error:
        print(f"ERROR: {' '.join(map(str, error.cmd))} が失敗した (exit {error.returncode})", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
