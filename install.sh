#!/usr/bin/env bash
# altairs-agent-dev-kit installer: rules / agents / hooks / codex を導入先へ展開する
set -euo pipefail
shopt -s nullglob

KIT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TARGET="" ; DO_RULES=0 ; DO_AGENTS=0 ; DO_HOOKS=0 ; DO_CODEX=0 ; FORCE=0

while [[ $# -gt 0 ]]; do
  case "$1" in
    --target) TARGET="$2"; shift 2 ;;
    --rules) DO_RULES=1; shift ;;
    --agents) DO_AGENTS=1; shift ;;
    --hooks) DO_HOOKS=1; shift ;;
    --codex) DO_CODEX=1; shift ;;
    --all) DO_RULES=1; DO_AGENTS=1; DO_HOOKS=1; DO_CODEX=1; shift ;;
    --force) FORCE=1; shift ;;
    *) echo "unknown option: $1" >&2; exit 1 ;;
  esac
done

[[ -n "$TARGET" && -d "$TARGET" ]] || { echo "--target <existing repo> が必要" >&2; exit 1; }
TARGET="$(cd "$TARGET" && pwd)"

copy_file() {  # copy_file <src> <dest>
  local src="$1" dest="$2"
  if [[ -e "$dest" && "$FORCE" -eq 0 ]]; then
    echo "SKIP (exists): $dest"
  else
    mkdir -p "$(dirname "$dest")"
    cp "$src" "$dest"
    echo "INSTALL: $dest"
  fi
}

if [[ "$DO_RULES" -eq 1 ]]; then
  for f in "$KIT_DIR"/rules/*.md; do copy_file "$f" "$TARGET/.claude/rules/$(basename "$f")"; done
fi

if [[ "$DO_AGENTS" -eq 1 ]]; then
  for f in "$KIT_DIR"/agents/*.md; do copy_file "$f" "$TARGET/.claude/agents/$(basename "$f")"; done
fi

if [[ "$DO_HOOKS" -eq 1 ]]; then
  for f in "$KIT_DIR"/hooks/scripts/*.py; do copy_file "$f" "$TARGET/.claude/hooks/$(basename "$f")"; done
  for f in "$KIT_DIR"/hooks/rules/*.default.json; do copy_file "$f" "$TARGET/.claude/hooks/rules/$(basename "$f")"; done
  chmod +x "$TARGET"/.claude/hooks/hook_*.py
  echo ""
  echo "== settings.json へ以下の hooks 配線を手動追加してください =="
  cat "$KIT_DIR/hooks/hooks.json"
fi

if [[ "$DO_CODEX" -eq 1 ]]; then
  mkdir -p "$TARGET/.codex/agents"
  dest="$TARGET/.codex/config.toml"
  [[ -e "$dest" && "$FORCE" -eq 0 ]] && dest="$dest.new"
  python3 - "$KIT_DIR/codex/config.toml.template" "$TARGET" > "$dest" <<'PYEOF'
import sys
from pathlib import Path
template, target = sys.argv[1], sys.argv[2]
print(Path(template).read_text(encoding="utf-8").replace("{{PROJECT_ROOT}}", target), end="")
PYEOF
  echo "INSTALL: $dest"
  for f in "$KIT_DIR"/codex/agents/*.toml; do copy_file "$f" "$TARGET/.codex/agents/$(basename "$f")"; done
fi

echo "DONE"
