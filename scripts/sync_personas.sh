#!/usr/bin/env bash
# Refresh the persona snapshots from the Claude.ai-synced skills folder.
# Snapshots are copied byte-for-byte; SOURCES.sha256 records exactly what each run used.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SYNC_DIR="${SKILLS_SYNC_DIR:-$(ls -d "$HOME"/.claude/skills/synced/*/ 2>/dev/null | head -1)}"
SKILLS=(prd-development design-analysis-debate user-story user-story-mapping)

[ -d "$SYNC_DIR" ] || { echo "Synced skills folder not found. Set SKILLS_SYNC_DIR." >&2; exit 1; }

for s in "${SKILLS[@]}"; do
  [ -f "$SYNC_DIR/$s/SKILL.md" ] || { echo "Missing $SYNC_DIR/$s/SKILL.md" >&2; exit 1; }
  rm -rf "$ROOT/personas/$s"
  cp -r "$SYNC_DIR/$s" "$ROOT/personas/$s"
done

cd "$ROOT/personas"
find . -type f ! -name SOURCES.sha256 -print0 | sort -z | xargs -0 sha256sum > SOURCES.sha256
echo "Synced from: $SYNC_DIR"
echo "Snapshot checksums: personas/SOURCES.sha256"
