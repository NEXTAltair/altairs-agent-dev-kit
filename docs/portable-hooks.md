# Portable hooks

Common hook policy belongs to this kit. Consuming repositories keep their own
override JSON and event registrations, not independent copies maintained by hand.

The plugin template uses Claude exec-form commands (`python`, `args`) and native
timeout fields. The installer renders the plugin root placeholder into the project
root placeholder. Explicit UTF-8 handles non-ASCII repository names on Windows.

Codex adapters select the provider and reuse shared policy. The current PreToolUse
contract accepts structured `hookSpecificOutput.permissionDecision=deny` with exit
0. Stop handles `last_assistant_message` and the recursive-stop flag. Codex does
not document WorktreeCreate; this installer only registers PreToolUse and Stop.
Continue creating Codex worktrees through Git/agent workflows.

Windows requires Python on PATH; the container requires Python/Python3 and Git.
Neither hook startup nor installation syncs the application's virtual environment.
`--codex` also renders a local config using the installation target's `.venv`;
use a separate local config per OS and point worktrees to the main checkout's
environment. A copied Linux environment path is not a valid Windows environment.

Existing runtime files are skipped unless `--force` is given. Existing generated
Codex config is preserved and a `.new` proposal is created. If that proposal also
exists, installation fails rather than silently replacing it. `--force` replaces
kit files and generated Codex config; review local customizations first.
Only `*.default.json` rules are installed, so project override rules remain intact.

After migration, check user-level and project-local hook settings for duplicate
registrations. Restart the agent and review changed Codex hooks in `/hooks` when
it requests trust. Do not bypass hook trust.

CI executes portable installation and runtime regression tests on Windows and
Linux. The existing shell-installer test suite remains Linux-specific.

Sources:

- https://code.claude.com/docs/en/hooks
- https://learn.chatgpt.com/ja-JP/docs/hooks
