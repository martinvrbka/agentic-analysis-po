#!/usr/bin/env bash
# Launch the grooming pipeline in an interactive Claude Code session.
# Interactive on purpose: stage 0/1 may ask you questions (slug, clarifications), which headless `-p` cannot do.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"

if [ $# -ne 1 ]; then
  echo "usage: $0 <requirement-file.md>" >&2; exit 1
fi
if [ ! -f "$1" ]; then
  echo "Requirement file not found: $1" >&2; exit 1
fi
if ! command -v claude >/dev/null; then
  echo "The 'claude' CLI is not on PATH. Install it (npm i -g @anthropic-ai/claude-code) or run /groom $1 inside Claude Code." >&2
  exit 1
fi

REQ="$(realpath --relative-to="$ROOT" "$1")"
cd "$ROOT"
exec claude "/groom $REQ"
