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
0. Stop handles `last_assistant_message` and the recursive-stop flag. Codex does
not document WorktreeCreate; this installer only registers PreToolUse and Stop.
Continue creating Codex worktrees through Git/agent workflows.

Generated project registrations use `python` on Windows and `python3` on Linux.
Regenerate these registrations when moving to a different OS. A shared project
may explicitly use `python` on both if both environments provide that alias.
The plugin's `python_command` user configuration defaults to `python3` for Linux.
On Windows, configure it as `python` or an absolute Python executable path when
enabling the plugin. Claude substitutes this setting directly into the exec command;
no shell wrapper or optional Linux `python` alias is required.
Git is also required.
Neither hook startup nor installation syncs the application's virtual environment.
`--codex` also renders a local config using the installation target's `.venv`;
use a separate local config per OS and point worktrees to the main checkout's
environment. A copied Linux environment path is not a valid Windows environment.

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
it requests trust. Do not bypass hook trust.

CI executes portable installation and runtime regression tests on Windows and
Linux. The existing shell-installer test suite remains Linux-specific.

Sources:

- https://code.claude.com/docs/en/hooks
- https://code.claude.com/docs/en/plugins-reference
- https://learn.chatgpt.com/ja-JP/docs/hooks
