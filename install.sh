#!/usr/bin/env bash
# install.sh - put CLEAR-100 wherever this machine's agents read from.
# Idempotent: every write happens between markers, so running twice changes nothing.
set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BEGIN="<!-- CLEAR-100 begin -->"
END="<!-- CLEAR-100 end -->"
DRY=0
TOUCHED=0

for arg in "$@"; do
  case "$arg" in
    --dry-run) DRY=1 ;;
    -h|--help) sed -n '2,6p' "$0"; exit 0 ;;
    *) echo "unknown flag: $arg" >&2; exit 2 ;;
  esac
done

say() { printf '  %-9s %s\n' "$1" "$2"; }

do_write() {
  # do_write <destination> <content-file>
  local dest="$1" src="$2"
  if [ "$DRY" = 1 ]; then say "would" "$dest"; return; fi
  mkdir -p "$(dirname "$dest")"
  cp "$src" "$dest"
  TOUCHED=$((TOUCHED + 1))
  say "wrote" "$dest"
}

inject() {
  # inject <target-md> : replace the block between markers, or append it
  local dest="$1"
  if [ "$DRY" = 1 ]; then say "would" "$dest (block)"; return; fi
  python3 "$REPO/scripts/inject_block.py" "$dest" | sed 's/^/  /'
  TOUCHED=$((TOUCHED + 1))
}

echo "clearmode installer"
echo "repo: $REPO"
echo

# 1. Claude Code skill, user scope
if [ -d "$HOME/.claude" ]; then
  DEST="$HOME/.claude/skills/clearmode"
  if [ "$DRY" = 0 ]; then
    mkdir -p "$DEST/references" "$DEST/scripts" "$DEST/rules"
    cp "$REPO/SKILL.md" "$DEST/SKILL.md"
    cp "$REPO/references/"*.md "$DEST/references/"
    cp "$REPO/scripts/clearcheck.py" "$DEST/scripts/"
    cp "$REPO/rules/clear-100.json" "$DEST/rules/"
    TOUCHED=$((TOUCHED + 1))
    say "wrote" "$DEST (skill + checker)"
  else
    say "would" "$DEST"
  fi
  if [ -d "$HOME/.claude/commands" ]; then
    for c in "$REPO"/commands/*.md; do
      do_write "$HOME/.claude/commands/$(basename "$c")" "$c"
    done
  fi
fi

# 2. Codex CLI, user scope
if [ -d "$HOME/.codex" ]; then
  inject "$HOME/.codex/AGENTS.md"
fi

# 3. Cursor rules, this project
if [ -d ".cursor" ] || [ -d ".cursor/rules" ]; then
  do_write ".cursor/rules/clearmode.mdc" "$REPO/targets/cursor/clearmode.mdc"
fi

# 4. AGENTS.md in this project
if [ -f "AGENTS.md" ]; then
  inject "AGENTS.md"
fi

# 5. Vale, this project
if [ -f ".vale.ini" ]; then
  if [ "$DRY" = 0 ]; then
    STYLES="$(awk -F'=' '/StylesPath/ {gsub(/ /,"",$2); print $2}' .vale.ini | head -1)"
    STYLES="${STYLES:-styles}"
    mkdir -p "$STYLES/ClearMode"
    cp "$REPO/targets/vale/ClearMode/"*.yml "$STYLES/ClearMode/"
    TOUCHED=$((TOUCHED + 1))
    say "wrote" "$STYLES/ClearMode (7 rules)"
    echo "  note      add ClearMode to BasedOnStyles in .vale.ini"
  else
    say "would" "vale styles"
  fi
fi

echo
if [ "$TOUCHED" = 0 ] && [ "$DRY" = 0 ]; then
  echo "Nothing detected. Copy a file from targets/ by hand:"
  ls "$REPO/targets"
else
  echo "$TOUCHED targets installed."
  echo "Check something: python3 $REPO/scripts/clearcheck.py <file>"
fi
