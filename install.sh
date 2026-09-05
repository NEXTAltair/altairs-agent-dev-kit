#!/usr/bin/env bash
# altairs-agent-dev-kit installer: rules / agents / hooks / codex を導入先へ展開する
set -euo pipefail
shopt -s nullglob

KIT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TARGET="" ; DO_RULES=0 ; DO_AGENTS=0 ; DO_HOOKS=0 ; DO_CODEX=0 ; DO_SKILLS=0 ; FORCE=0

while [[ $# -gt 0 ]]; do
  case "$1" in
    --target) TARGET="$2"; shift 2 ;;
    --rules) DO_RULES=1; shift ;;
    --agents) DO_AGENTS=1; shift ;;
    --hooks) DO_HOOKS=1; shift ;;
    --codex) DO_CODEX=1; shift ;;
    --skills) DO_SKILLS=1; shift ;;
    --all) DO_RULES=1; DO_AGENTS=1; DO_HOOKS=1; DO_CODEX=1; DO_SKILLS=1; shift ;;
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
  hook_args=(--target "$TARGET")
  [[ "$FORCE" -eq 0 ]] || hook_args+=(--force)
  python3 -X utf8 "$KIT_DIR/scripts/install_harness.py" "${hook_args[@]}"
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

if [[ "$DO_SKILLS" -eq 1 ]]; then
  command -v npx >/dev/null 2>&1 || {
    echo "ERROR: --skills には Node.js (npx) が必要です。https://nodejs.org からインストールするか、Node 導入後に再実行してください" >&2
    exit 1
  }
  # skill の導入は skills.sh CLI (npx skills) に一本化する。npx は初回実行時に CLI を
  # 自動取得するため事前の npm install は不要。CLI はメジャーバージョンを固定する
  # (フラグ互換が予告なく変わるのを防ぐ)。追従が必要になったらこのピンを明示的に上げる。
  #
  # canonical レイアウトを生成する: 実体は .agents/skills/ に置き (Codex/Copilot/OpenCode が
  # 共有する canonical dir。--agent codex で universal 配置)、各 skill の .claude/skills/<name>
  # はそこへの相対 symlink にする (Claude Code は .claude/skills を読む)。これは skills.sh 既定
  # (canonical コピー + 各 agent の symlink) と、.claude/skills/<name> が symlink であることを
  # 要求する検証 (validate_harness 等) の期待に一致する。source はコピーされ実体になる
  # (ローカル source でも同じ。source へ live link するモードは skills.sh に存在しない)。
  (cd "$TARGET" && npx --yes skills@1 add "$KIT_DIR" --skill '*' --agent codex -y)

  # .claude/skills/<name> → ../../.agents/skills/<name> の相対 symlink を張る。
  # skills.sh は --agent codex では .claude 側を作らないため、ここで明示生成する。
  # symlink 非対応環境 (Windows で開発者モード無効など) では実体コピーにフォールバックする。
  if [[ -d "$TARGET/.agents/skills" ]]; then
    mkdir -p "$TARGET/.claude/skills"
    for skill_dir in "$TARGET"/.agents/skills/*/; do
      [[ -f "${skill_dir}SKILL.md" ]] || continue
      name="$(basename "$skill_dir")"
      link="$TARGET/.claude/skills/$name"
      [[ -e "$link" || -L "$link" ]] && rm -rf "$link"
      if ln -s "../../.agents/skills/$name" "$link" 2>/dev/null; then
        echo "LINK: .claude/skills/$name -> ../../.agents/skills/$name"
      else
        cp -r "${skill_dir%/}" "$link"
        echo "COPY (symlink 非対応環境): .claude/skills/$name"
      fi
    done
  fi
fi

echo "DONE"
