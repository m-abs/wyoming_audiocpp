#!/usr/bin/env bash
#
# fetch_references.sh — check out / update the development reference projects
# under ./references/. Idempotent: safe to run repeatedly.
#
# Reference projects (read-only, NOT project source — see AGENTS.md):
#   wyoming-piper          TTS reference implementation
#   wyoming-faster-whisper ASR reference implementation
#   audio.cpp              audio model HTTP service (C++; has a submodule)
#
# Usage:
#   scripts/fetch_references.sh                 # clone missing, sync existing to upstream tip
#   scripts/fetch_references.sh --branch main   # pin all repos to a branch (default: main)
#   REF_BRANCH=main scripts/fetch_references.sh # same, via env var
#

set -euo pipefail

# Resolve repo root from the script's own location (scripts/..).
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
REF_DIR="$REPO_ROOT/references"

BRANCH="main"
case "${1:-}" in
  --branch) BRANCH="${2:?--branch requires a value}";;
  --branch=*) BRANCH="${1#--branch=}";;
esac
BRANCH="${REF_BRANCH:-$BRANCH}"

declare -A REPOS=(
  [wyoming-piper]="https://github.com/OHF-Voice/wyoming-piper.git"
  [wyoming-faster-whisper]="https://github.com/OHF-Voice/wyoming-faster-whisper.git"
  [audio.cpp]="https://github.com/0xShug0/audio.cpp.git"
)

mkdir -p "$REF_DIR"

for name in "${!REPOS[@]}"; do
  url="${REPOS[$name]}"
  dir="$REF_DIR/$name"

  if [[ -d "$dir/.git" ]]; then
    # Existing checkout: sync to the upstream tip of $BRANCH.
    echo ">> updating $name"
    git -C "$dir" fetch --all --prune
    git -C "$dir" checkout -B "$BRANCH" "origin/$BRANCH"
  elif [[ -e "$dir" ]]; then
    # Dir exists but is not a git checkout; do not delete user data.
    echo "!! $dir exists but is not a git checkout; skipping (remove it to re-clone)" >&2
    continue
  else
    # Missing: clone fresh.
    echo ">> cloning $name from $url"
    git clone --branch "$BRANCH" "$url" "$dir"
  fi

  # audio.cpp pulls a submodule (server frontends); keep it in sync for all.
  if [[ -f "$dir/.gitmodules" ]]; then
    echo ">> syncing submodules for $name"
    git -C "$dir" submodule update --init --recursive
  fi
done

echo "Reference projects ready under $REF_DIR:"
for name in "${!REPOS[@]}"; do
  printf '  %-24s %s\n' "$name" "$(git -C "$REF_DIR/$name" rev-parse --short HEAD 2>/dev/null || echo '(missing)')"
done
