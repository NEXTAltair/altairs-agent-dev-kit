---
type: Guide
title: Portable hooks
description: kit が hook の共通ポリシーを持ち、導入先は override JSON とイベント登録だけを保持する配布モデルと、Claude / Codex 向け配線の説明
timestamp: 2026-10-06
---
# Portable hooks

Common hook policy belongs to this kit. Consuming repositories keep their own
override JSON and event registrations, not independent copies maintained by hand.

The plugin template uses Claude exec-form commands (`command`, `args`) and native
timeout fields. Installed project registrations resolve the active Git root and
select the runtime pinned by that checkout's `.agent-kit/hooks.lock.json`, including
the matching version in the shared checkout. Policy overrides still come from the
active checkout. Explicit UTF-8 handles
non-ASCII repository names on Windows.

Codex adapters select the provider and reuse shared policy. The current PreToolUse
contract accepts structured `hookSpecificOutput.permissionDecision=deny` with exit
0. Codex reports every shell call as `tool_name: "Bash"` with `tool_input.command`
and file edits as `tool_name: "apply_patch"` with the patch text in
`tool_input.command`. The installer registers the command policy for `Bash` and the
shared-checkout edit gate for `apply_patch`; the gate reads the `*** Add File:` /
`*** Update File:` / `*** Delete File:` / `*** Move to:` headers relative to the
payload `cwd`. Stop handles `last_assistant_message` and the recursive-stop flag.
Codex has no WorktreeCreate/WorktreeRemove; continue creating Codex worktrees
through Git/agent workflows.

Claude Code registers WorktreeCreate together with WorktreeRemove. With only
WorktreeCreate, Claude Code keeps every worktree the hook created. The remove hook
deletes only linked worktrees of the same repository directly under
`.agents/worktree/`, and never passes `--force`: worktrees with uncommitted or
untracked files, locks, or initialized submodules stay in place, and so do worktrees
whose HEAD no branch, remote-tracking ref or tag contains (WorktreeCreate starts them
detached, so commits made before creating a branch would otherwise be lost). The edit gate also
covers `NotebookEdit`, which passes `tool_input.notebook_path`.

Codex hooks are enabled by default (feature key `hooks`; `codex_hooks` is a
deprecated alias), but project `.codex/hooks.json` loads only in trusted projects.
A hook with a failed run, a timeout, or invalid JSON output does not block the tool
call in either client.

Generated project registrations use `python` on Windows and `python3` on Linux.
Regenerate these registrations when moving to a different OS. A shared project
may explicitly use `python` on both if both environments provide that alias.
The plugin's `python_command` user configuration defaults to `python3` for Linux.
On Windows, configure it as `python` or an absolute Python executable path when
enabling the plugin. Claude substitutes this setting directly into the exec command;
no shell wrapper or optional Linux `python` alias is required.
Git is also required.
Neither hook startup nor installation syncs the application's virtual environment.
`--codex` writes config into the installation target while pointing its environment
at the shared checkout's `.venv`, including when the target is a linked worktree.
Use a separate local config per OS. A copied Linux environment path is not a valid
Windows environment.

Runtime files are verified and published under a content hash. Existing versions
are never overwritten, including with `--force`; that flag permits changing the
checkout's pin and replacing generated config. Existing generated Codex config is
otherwise preserved and a `.new` proposal is created. If that proposal also exists,
installation fails rather than silently replacing it. Project override rules remain
intact. Track the lock and registrations in Git; ignore runtime directories.
Plugins also require a branch lock before enabling hooks. See the
[runtime contract](hook-runtime.md) for setup, consumer hook integration, and recovery.

After migration, check user-level and project-local hook settings for duplicate
registrations. Restart the agent and review changed Codex hooks in `/hooks` when
it requests trust. Codex records trust per hook position and command hash, so every
regenerated `.codex/hooks.json` (each kit update embeds new startup code) and every
new group needs review again; until then Codex skips those hooks. Do not bypass hook trust.

CI executes portable installation and runtime regression tests on Windows and
Linux. The existing shell-installer test suite remains Linux-specific.

Sources:

- https://code.claude.com/docs/en/hooks
- https://code.claude.com/docs/en/plugins-reference
- https://learn.chatgpt.com/ja-JP/docs/hooks
