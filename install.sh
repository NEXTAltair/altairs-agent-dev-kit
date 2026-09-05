#!/usr/bin/env bash
# altairs-agent-dev-kit installer: rules / agents / hooks / codex を導入先へ展開する
set -euo pipefail
shopt -s nullglob

KIT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TARGET="" ; DO_RULES=0 ; DO_AGENTS=0 ; DO_HOOKS=0 ; DO_CODEX=0 ; DO_SKILLS=0 ; FORCE=0
SKILL_SOURCE=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --target) TARGET="$2"; shift 2 ;;
    --rules) DO_RULES=1; shift ;;
    --agents) DO_AGENTS=1; shift ;;
    --hooks) DO_HOOKS=1; shift ;;
    --codex) DO_CODEX=1; shift ;;
    --skills) DO_SKILLS=1; shift ;;
    --skill-source) SKILL_SOURCE="$2"; shift 2 ;;
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

if [[ "$DO_SKILLS" -eq 1 ]]; then
  command -v npx >/dev/null 2>&1 || {
    echo "ERROR: --skills には Node.js (npx) が必要です。https://nodejs.org からインストールするか、Node 導入後に再実行してください" >&2
    exit 1
  }
  # Determine exactly which kit-owned names may be written before invoking npx.
  # Its non-interactive mode overwrites existing skills and lock entries.
  selected_skills=()
  link_skills=()
  for skill_dir in "$KIT_DIR"/skills/*/; do
    [[ -f "${skill_dir}SKILL.md" ]] || continue
    name="$(basename "$skill_dir")"
    canonical="$TARGET/.agents/skills/$name"
    link="$TARGET/.claude/skills/$name"
    owned_dangling_link=0
    if [[ -L "$link" && ! -e "$link" && "$(readlink "$link")" == "../../.agents/skills/$name" ]]; then
      owned_dangling_link=1
    fi
    if [[ "$FORCE" -eq 0 && ( -e "$canonical" || -L "$canonical" || -e "$link" || ( -L "$link" && "$owned_dangling_link" -eq 0 ) ) ]]; then
      echo "SKIP (exists): skill $name"
      if [[ -f "$canonical/SKILL.md" && ! -e "$link" && ! -L "$link" ]]; then
        link_skills+=("$name")
      fi
    else
      selected_skills+=("$name")
    fi
  done

  if [[ ${#selected_skills[@]} -gt 0 ]]; then
    if [[ -n "$SKILL_SOURCE" && -d "$SKILL_SOURCE" ]]; then
      SKILL_SOURCE="$(cd "$SKILL_SOURCE" && pwd)"
    elif [[ -n "$SKILL_SOURCE" && ! "$SKILL_SOURCE" =~ ^github:[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+#[^[:space:]]+$ ]]; then
      echo "ERROR: --skill-source は存在するローカルディレクトリか github:owner/repo#ref を指定してください" >&2
      exit 1
    fi
    # Published installs must keep a portable release tag in skills-lock.json.
    # Local/unpublished sources require an explicit --skill-source override.
    if [[ -z "$SKILL_SOURCE" ]]; then
      origin="$(git -C "$KIT_DIR" remote get-url origin)"
      revision="$(git -C "$KIT_DIR" describe --tags --exact-match HEAD 2>/dev/null)" || {
        echo "ERROR: --skills はリリースタグの checkout が必要です。未公開の変更を使う場合は --skill-source <ローカルパス> を明示してください" >&2
        exit 1
      }
      if [[ "$origin" =~ ^https://github\.com/([^/]+)/([^/]+)$ || "$origin" =~ ^git@github\.com:([^/]+)/([^/]+)$ ]]; then
        owner="${BASH_REMATCH[1]}"
        repository="${BASH_REMATCH[2]%.git}"
        SKILL_SOURCE="github:$owner/$repository#$revision"
      else
        echo "ERROR: GitHub origin がありません。--skill-source <github:owner/repo#ref または開発用ローカルパス> を指定してください" >&2
        exit 1
      fi
    fi
    if [[ "$FORCE" -eq 0 && -f "$TARGET/skills-lock.json" ]]; then
      # A fresh checkout can retain a pin without its ignored skill directory.
      # Do not silently change that pin just because there is no file to skip.
      python3 - "$TARGET/skills-lock.json" "$SKILL_SOURCE" "${selected_skills[@]}" <<'PYEOF'
import json
import re
import sys
from pathlib import Path
lock_path = Path(sys.argv[1])
source = sys.argv[2]
skills = json.loads(lock_path.read_text(encoding="utf-8"))["skills"]
github = re.fullmatch(r"github:([^#]+)#(.+)", source)
for name in sys.argv[3:]:
    entry = skills.get(name)
    if entry is None:
        continue
    matches = bool(github and entry.get("sourceType") == "github"
                   and entry.get("source") == github[1] and entry.get("ref") == github[2])
    if not github and entry.get("sourceType") == "local":
        matches = (lock_path.parent / entry.get("source", "")).resolve() == Path(source).resolve()
    if not matches:
        raise SystemExit(f"ERROR: {name} の既存 pin と導入元が異なります。固定版から復元するか、意図的な更新に --force を指定してください")
PYEOF
    fi
  fi
fi

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
  python3 -X utf8 - "$KIT_DIR" "$TARGET" "$FORCE" <<'PYEOF'
import sys
from pathlib import Path
sys.path.insert(0, str(Path(sys.argv[1]) / "scripts"))
from install_harness import install_codex
install_codex(Path(sys.argv[2]), force=bool(int(sys.argv[3])))
PYEOF
fi

if [[ "$DO_SKILLS" -eq 1 && ${#selected_skills[@]} -gt 0 ]]; then
    (cd "$TARGET" && npx --yes skills@1 add "$SKILL_SOURCE" --skill "${selected_skills[@]}" --agent codex -y)

    link_skills+=("${selected_skills[@]}")
fi

if [[ "$DO_SKILLS" -eq 1 && ${#link_skills[@]} -gt 0 ]]; then
    # Restore missing links without reinstalling or changing canonical skills/pins.
    mkdir -p "$TARGET/.claude/skills"
    for name in "${link_skills[@]}"; do
      skill_dir="$TARGET/.agents/skills/$name"
      [[ -f "$skill_dir/SKILL.md" ]] || { echo "ERROR: skill が導入されていません: $name" >&2; exit 1; }
      link="$TARGET/.claude/skills/$name"
      [[ -e "$link" || -L "$link" ]] && rm -rf "$link"
      if ln -s "../../.agents/skills/$name" "$link" 2>/dev/null; then
        echo "LINK: .claude/skills/$name -> ../../.agents/skills/$name"
      else
        cp -r "$skill_dir" "$link"
        echo "COPY (symlink 非対応環境): .claude/skills/$name"
      fi
    done
fi

echo "DONE"
