"""scripts/agent_kit.py (マルチハーネス installer) のテスト。

確かめる契約:
- 各ハーネスが実際に読む場所へ、その形式で置く (Claude: paths frontmatter / Antigravity: trigger frontmatter)
- rules を自動で読まないハーネス (Codex / OpenClaw) には AGENTS.md の管理区画で索引を渡す
- global は scope=global の部品だけ、project は profile で選んだ scope=project の部品だけ
- kit が置いて未変更のファイルだけを更新・削除し、利用者の変更と既存の AGENTS.md 本文は残す
- kit.json は kit 内の skills / rules / agents と過不足なく一致する
"""

import json
import os
import stat
import sys
from pathlib import Path

import pytest

KIT = Path(__file__).parent.parent
sys.path.insert(0, str(KIT / "scripts"))

import agent_kit  # noqa: E402

ALL = "claude,codex,antigravity,openclaw"


def run(*args: str) -> int:
    return agent_kit.main(list(args))


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    target = tmp_path / "repo"
    target.mkdir()
    (target / "pyproject.toml").write_text('[project]\nname = "x"\ndependencies = ["sqlalchemy"]\n', encoding="utf-8")
    return target


@pytest.fixture
def home(tmp_path: Path) -> Path:
    directory = tmp_path / "home"
    directory.mkdir()
    return directory


def project(repo: Path, home: Path, *extra: str, harness: str = ALL, components: str = "rules,agents") -> int:
    return run("install", "--scope", "project", "--target", str(repo), "--home", str(home),
               "--harness", harness, "--components", components, *extra)


def test_manifest_matches_kit_contents():
    manifest = agent_kit.load_manifest()
    assert set(manifest["skills"]) == {path.parent.name for path in (KIT / "skills").glob("*/SKILL.md")}
    assert set(manifest["rules"]) == {path.stem for path in (KIT / "rules").glob("*.md")}
    assert set(manifest["agents"]) == {path.stem for path in (KIT / "agents").glob("*.md")}
    for kind in ("skills", "rules", "agents"):
        for name, meta in manifest[kind].items():
            assert meta["profile"] in manifest["profiles"], name
            assert meta["scope"] in ("global", "project"), name
            # 特定スタック向けの部品を全プロジェクトへ効く global に置かない
            assert meta["scope"] == "project" or meta["profile"] == "core", name
    for name, meta in manifest["rules"].items():
        assert meta["activation"] in ("always", "on-demand", "glob"), name
        assert meta["description"], name
        assert (meta["activation"] == "glob") == bool(meta.get("globs")), name


def test_project_install_uses_each_harness_native_location_and_format(repo, home):
    assert project(repo, home) == 0

    claude = (repo / ".claude/rules/coding-style.md").read_text(encoding="utf-8")
    assert claude.startswith('---\npaths:\n  - "**/*.py"\n  - "pyproject.toml"\n---\n')
    # paths を持たない rule は Claude Code には原文のまま (frontmatter なし)
    assert (repo / ".claude/rules/parallel-execution.md").read_text(encoding="utf-8") == \
        (KIT / "rules/parallel-execution.md").read_text(encoding="utf-8")

    canonical = repo / ".agents/rules"
    assert (canonical / "coding-style.md").read_text(encoding="utf-8").startswith(
        '---\ntrigger: glob\ndescription: "')
    assert 'globs: "**/*.py, pyproject.toml"' in (canonical / "coding-style.md").read_text(encoding="utf-8")
    assert (canonical / "parallel-execution.md").read_text(encoding="utf-8").startswith("---\ntrigger: always_on\n")
    assert (canonical / "testing.md").read_text(encoding="utf-8").startswith("---\ntrigger: model_decision\n")

    assert (repo / ".claude/agents/code-reviewer.md").is_file()
    assert (repo / ".codex/agents/code-reviewer.toml").is_file()
    assert (repo / ".agents/agents/code-reviewer.md").read_text(encoding="utf-8") == \
        (KIT / "antigravity/agents/code-reviewer.md").read_text(encoding="utf-8")
    # sql profile は pyproject の sqlalchemy から検出される
    assert (repo / ".claude/agents/query-analyzer.md").is_file()


def test_project_install_skips_global_scope_parts_unless_standalone(repo, home):
    assert project(repo, home) == 0
    assert not (repo / ".agents/rules/problem-solving.md").exists()
    assert not (repo / ".claude/agents/investigation.md").exists()

    assert project(repo, home, "--standalone") == 0
    assert (repo / ".agents/rules/problem-solving.md").is_file()
    assert (repo / ".claude/agents/investigation.md").is_file()


def test_profile_limits_stack_specific_parts(tmp_path, home):
    plain = tmp_path / "plain"
    plain.mkdir()
    assert project(plain, home) == 0
    assert (plain / ".agents/rules/planning-memory.md").is_file()
    # Issue から merge までの流れ (git-workflow) は言語非依存なので global に置き、project には重ねない
    assert not (plain / ".agents/rules/git-workflow.md").exists()
    assert not (plain / ".agents/rules/coding-style.md").exists()
    assert not (plain / ".claude/agents/code-reviewer.md").exists()

    assert project(plain, home, "--profile", "python") == 0
    assert (plain / ".agents/rules/coding-style.md").is_file()
    assert not (plain / ".claude/agents/query-analyzer.md").exists()


def test_typescript_profile_is_detected_from_package_json(tmp_path, home):
    web = tmp_path / "web"
    web.mkdir()
    (web / "package.json").write_text('{"name": "web"}\n', encoding="utf-8")
    assert project(web, home) == 0
    style = (web / ".agents/rules/typescript-style.md").read_text(encoding="utf-8")
    assert style.startswith("---\ntrigger: glob\n") and '"**/*.ts, **/*.tsx, ' in style
    assert (web / ".claude/rules/typescript-style.md").read_text(encoding="utf-8").startswith(
        '---\npaths:\n  - "**/*.ts"\n')
    assert (web / ".agents/rules/typescript-dependencies.md").is_file()
    # Python 向けの rule は入らない
    assert not (web / ".agents/rules/coding-style.md").exists()
    assert "typescript-testing.md" in (web / "AGENTS.md").read_text(encoding="utf-8")


def test_index_block_keeps_existing_instructions_and_is_replaced_in_place(repo, home):
    (repo / "AGENTS.md").write_text("# My project\n\nExisting notes.\n", encoding="utf-8")
    assert project(repo, home) == 0
    assert project(repo, home) == 0
    text = (repo / "AGENTS.md").read_text(encoding="utf-8")
    assert text.startswith("# My project\n\nExisting notes.\n\n" + agent_kit.BEGIN)
    assert text.count(agent_kit.BEGIN) == 1 and text.count(agent_kit.END) == 1
    assert "[.agents/rules/parallel-execution.md](.agents/rules/parallel-execution.md)" in text
    always, _, on_demand = text.partition("該当する作業の前に読む:")
    assert "parallel-execution.md" in always and "testing.md" in on_demand


def test_no_index_when_every_harness_loads_rules_natively(repo, home):
    assert project(repo, home, harness="claude,antigravity") == 0
    assert not (repo / "AGENTS.md").exists()


def test_openclaw_only_project_gets_shared_locations_only(repo, home):
    assert project(repo, home, harness="openclaw") == 0
    assert (repo / ".agents/rules/planning-memory.md").is_file()
    assert agent_kit.BEGIN in (repo / "AGENTS.md").read_text(encoding="utf-8")
    for foreign in (".claude", ".codex", ".agents/agents"):
        assert not (repo / foreign).exists()


def test_global_install_stays_inside_home_and_takes_only_global_parts(repo, home, tmp_path):
    before = sorted(path for path in tmp_path.rglob("*") if home not in path.parents and path != home)
    assert run("install", "--scope", "global", "--home", str(home), "--harness", ALL,
               "--components", "rules,agents") == 0
    assert sorted(path for path in tmp_path.rglob("*") if home not in path.parents and path != home) == before

    assert (home / ".claude/rules/problem-solving.md").is_file()
    # Issue → worktree → PR → merge の流れは言語・プロジェクトを問わないので global
    assert (home / ".claude/rules/git-workflow.md").is_file()
    assert "`~/.agents/rules/git-workflow.md`" in (home / ".codex/AGENTS.md").read_text(encoding="utf-8")
    assert (home / ".gemini/config/rules/problem-solving.md").read_text(encoding="utf-8").startswith(
        "---\ntrigger: always_on\n")
    assert (home / ".agents/rules/problem-solving.md").is_file()
    assert "`~/.agents/rules/problem-solving.md`" in (home / ".codex/AGENTS.md").read_text(encoding="utf-8")
    assert (home / ".gemini/config/agents/investigation.md").is_file()
    assert (home / ".codex/agents/investigation.toml").is_file()
    # project 向け (スタック依存) の部品は global に入れない
    assert not (home / ".claude/rules/coding-style.md").exists()
    assert not (home / ".claude/agents/code-reviewer.md").exists()
    # OpenClaw の agent workspace と設定には触れない
    assert not (home / ".openclaw").exists()


def test_user_modified_file_is_kept_until_force(repo, home, capsys):
    assert project(repo, home, harness="claude") == 0
    edited = repo / ".claude/rules/testing.md"
    edited.write_text("my own rule\n", encoding="utf-8")

    assert project(repo, home, harness="claude") == 0
    assert edited.read_text(encoding="utf-8") == "my own rule\n"
    assert "SKIP" in capsys.readouterr().out

    assert project(repo, home, "--force", harness="claude") == 0
    assert edited.read_text(encoding="utf-8") == (KIT / "rules/testing.md").read_text(encoding="utf-8")


def test_preexisting_unowned_file_is_not_overwritten(repo, home):
    existing = repo / ".claude/rules/testing.md"
    existing.parent.mkdir(parents=True)
    existing.write_text("consumer rule\n", encoding="utf-8")
    assert project(repo, home, harness="claude") == 0
    assert existing.read_text(encoding="utf-8") == "consumer rule\n"


def test_uninstall_removes_only_unmodified_kit_files_and_the_block(repo, home):
    (repo / "AGENTS.md").write_text("# My project\n", encoding="utf-8")
    assert project(repo, home) == 0
    edited = repo / ".claude/rules/testing.md"
    edited.write_text("my own rule\n", encoding="utf-8")

    assert run("uninstall", "--scope", "project", "--target", str(repo), "--home", str(home)) == 0
    assert edited.read_text(encoding="utf-8") == "my own rule\n"
    assert not (repo / ".claude/rules/parallel-execution.md").exists()
    assert not (repo / ".agents/rules/parallel-execution.md").exists()
    assert (repo / "AGENTS.md").read_text(encoding="utf-8") == "# My project\n"
    assert not (repo / ".agent-kit/install.json").exists()


def test_dry_run_writes_nothing(repo, home):
    before = sorted(repo.rglob("*"))
    assert project(repo, home, "--dry-run", "--skill-source", str(KIT), components="rules,agents,skills") == 0
    assert sorted(repo.rglob("*")) == before


def test_unknown_harness_and_missing_target_fail_before_writing(repo, home, capsys):
    assert project(repo, home, harness="claude,cursor") == 1
    assert "未対応のハーネス" in capsys.readouterr().err
    assert run("install", "--scope", "project", "--home", str(home), "--harness", "claude") == 1
    assert not (repo / ".claude").exists()


@pytest.mark.skipif(os.name == "nt", reason="shell script の npx 代役は POSIX のみ")
def test_skills_are_delegated_to_skills_sh_with_scope_and_agents(repo, home, tmp_path, monkeypatch):
    log = tmp_path / "npx.log"
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    fake = bin_dir / "npx"
    fake.write_text(f'#!/bin/sh\nprintf "%s\\n" "$PWD|$HOME|$*" >> "{log}"\n', encoding="utf-8")
    fake.chmod(fake.stat().st_mode | stat.S_IEXEC)
    monkeypatch.setenv("PATH", f"{bin_dir}{os.pathsep}{os.environ['PATH']}")
    (repo / ".agents/skills/lazy-import-refactor").mkdir(parents=True)  # 既存 skill は置き換えない

    assert project(repo, home, "--skill-source", str(KIT), components="skills") == 0
    assert run("install", "--scope", "global", "--home", str(home), "--harness", ALL,
               "--components", "skills", "--skill-source", str(KIT)) == 0

    project_call, global_call = log.read_text(encoding="utf-8").splitlines()
    cwd, _, arguments = project_call.split("|")
    assert Path(cwd) == repo
    assert arguments == f"--yes skills@1 add {KIT} --skill sqlalchemy-query-patterns --agent codex claude-code -y"
    _, used_home, arguments = global_call.split("|")
    assert Path(used_home) == home
    assert arguments.endswith("--agent codex claude-code antigravity -y -g")
    assert "--skill check-existing " in arguments and "pytest-qt-bdd" not in arguments
    # Issue から merge までの流れを担う skill は、どのプロジェクトでも使えるよう global に入る
    for name in ("issue-create", "issue-to-merge", "goal-prompt-crafter", "worktree-workflow",
                 "pr-maintainer", "pr-autoloop"):
        assert f" {name} " in arguments, name
    state = json.loads((repo / ".agent-kit/install.json").read_text(encoding="utf-8"))
    assert state["skills"] == ["sqlalchemy-query-patterns"]


def canonical_skill(root: Path, name: str) -> Path:
    directory = root / ".agents/skills" / name
    directory.mkdir(parents=True)
    (directory / "SKILL.md").write_text(f"---\nname: {name}\ndescription: x\n---\n", encoding="utf-8")
    return directory


@pytest.mark.skipif(os.name == "nt", reason="symlink の作成に権限が要る")
def test_existing_canonical_skills_get_missing_harness_links_without_force(repo, home, tmp_path, monkeypatch):
    # Codex 向けに導入済み (canonical だけがある) の状態へ、後から Claude Code / Antigravity を足す。
    monkeypatch.setenv("PATH", str(tmp_path))  # npx は呼ばれない (入れる skill が無い)
    for name in ("lazy-import-refactor", "sqlalchemy-query-patterns"):
        canonical_skill(repo, name)
    foreign = repo / ".claude/skills/lazy-import-refactor"
    foreign.parent.mkdir(parents=True)
    foreign.symlink_to("../../elsewhere")  # 利用者が張った別の link は切れていても触らない

    assert project(repo, home, "--skill-source", str(KIT), components="skills") == 0
    link = repo / ".claude/skills/sqlalchemy-query-patterns"
    assert link.is_symlink() and os.readlink(link) == "../../.agents/skills/sqlalchemy-query-patterns"
    assert (link / "SKILL.md").is_file()
    assert os.readlink(foreign) == "../../elsewhere"

    wanted = agent_kit.Context("global", home, ("claude", "antigravity"), ("core",),
                               manifest=agent_kit.load_manifest()).selected("skills")
    for name in wanted:
        canonical_skill(home, name)
    assert run("install", "--scope", "global", "--home", str(home), "--harness", "claude,antigravity",
               "--components", "skills", "--skill-source", str(KIT)) == 0
    assert os.readlink(home / ".gemini/config/skills/issue-to-merge") == "../../../.agents/skills/issue-to-merge"
    assert (home / ".claude/skills/pr-autoloop/SKILL.md").is_file()


def test_missing_npx_fails_before_anything_is_written(repo, home, tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("PATH", str(tmp_path))
    before = sorted(repo.rglob("*"))
    assert project(repo, home, "--skill-source", str(KIT), components="rules,agents,skills") == 1
    assert "npx" in capsys.readouterr().err
    assert sorted(repo.rglob("*")) == before


@pytest.mark.skipif(os.name == "nt", reason="shell script の npx 代役は POSIX のみ")
def test_ownership_is_recorded_when_a_later_step_fails(repo, home, tmp_path, monkeypatch):
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    fake = bin_dir / "npx"
    fake.write_text("#!/bin/sh\nexit 7\n", encoding="utf-8")
    fake.chmod(fake.stat().st_mode | stat.S_IEXEC)
    monkeypatch.setenv("PATH", f"{bin_dir}{os.pathsep}{os.environ['PATH']}")

    assert project(repo, home, "--skill-source", str(KIT), components="rules,agents,skills") == 1
    assert (repo / ".claude/rules/testing.md").is_file()
    state = json.loads((repo / ".agent-kit/install.json").read_text(encoding="utf-8"))
    assert ".claude/rules/testing.md" in state["files"] and state["index"] == "AGENTS.md"

    # 失敗した導入の後でも、書かれたものは uninstall で取り除ける
    assert run("uninstall", "--scope", "project", "--target", str(repo), "--home", str(home)) == 0
    assert not (repo / ".claude/rules/testing.md").exists()
    assert not (repo / "AGENTS.md").exists()


def git_repo(path: Path) -> Path:
    import subprocess
    path.mkdir()
    subprocess.run(["git", "init", "-q", str(path)], check=True)
    return path


def test_hooks_are_recorded_and_removed_by_uninstall(tmp_path, home):
    repo = git_repo(tmp_path / "hooked")
    assert project(repo, home, harness="codex", components="hooks") == 0
    state = json.loads((repo / ".agent-kit/install.json").read_text(encoding="utf-8"))
    assert set(state["files"]) == {".agent-kit/hooks.lock.json", ".codex/hooks.json"}
    runtimes = list((repo / ".agent-kit/runtimes").iterdir())
    assert runtimes

    assert run("uninstall", "--scope", "project", "--target", str(repo), "--home", str(home)) == 0
    assert not (repo / ".codex/hooks.json").exists()
    assert not (repo / ".agent-kit/hooks.lock.json").exists()
    assert list((repo / ".agent-kit/runtimes").iterdir()) == runtimes  # 共有 runtime は残す


def test_hooks_for_claude_only_do_not_register_codex(tmp_path, home):
    repo = git_repo(tmp_path / "claude-only")
    assert project(repo, home, harness="claude", components="hooks") == 0
    assert (repo / ".agent-kit/hooks.lock.json").is_file()
    assert not (repo / ".codex").exists()


def test_uninstall_keeps_lock_while_claude_wiring_remains(tmp_path, home, capsys):
    repo = git_repo(tmp_path / "wired")
    assert project(repo, home, harness="claude,codex", components="hooks") == 0
    wiring = capsys.readouterr().out.split("Merge this hooks object into .claude/settings.json:\n")[1]
    wiring = wiring[:wiring.rindex("}") + 1]
    settings = repo / ".claude/settings.json"
    settings.parent.mkdir()
    settings.write_text(wiring, encoding="utf-8")

    assert run("uninstall", "--scope", "project", "--target", str(repo), "--home", str(home)) == 0
    # lock を消すと残った配線が起動に失敗し、全ての tool 呼び出しを拒否する
    assert (repo / ".agent-kit/hooks.lock.json").is_file()
    assert not (repo / ".codex/hooks.json").exists()
    assert "settings.json" in capsys.readouterr().out

    settings.unlink()
    assert run("uninstall", "--scope", "project", "--target", str(repo), "--home", str(home)) == 0
    assert not (repo / ".agent-kit/hooks.lock.json").exists()
    assert not (repo / ".agent-kit/install.json").exists()


def test_modified_codex_hooks_are_kept_by_uninstall(tmp_path, home):
    repo = git_repo(tmp_path / "edited")
    assert project(repo, home, harness="codex", components="hooks") == 0
    hooks = repo / ".codex/hooks.json"
    hooks.write_text(hooks.read_text(encoding="utf-8") + "\n", encoding="utf-8")
    assert run("uninstall", "--scope", "project", "--target", str(repo), "--home", str(home)) == 0
    assert hooks.is_file()
