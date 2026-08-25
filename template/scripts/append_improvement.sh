#!/usr/bin/env bash
set -euo pipefail

# Appends one line to docs/orchestration/IMPROVEMENTS.md's Log section.
# Usage: append_improvement.sh <local|template|unsure> "<note>"

tag="${1:?Usage: append_improvement.sh <local|template|unsure> \"<note>\"}"
note="${2:?Usage: append_improvement.sh <local|template|unsure> \"<note>\"}"

case "$tag" in
  local|template|unsure) ;;
  *) echo "error: tag must be one of local, template, unsure" >&2; exit 1 ;;
esac

file="$(git rev-parse --show-toplevel)/docs/orchestration/IMPROVEMENTS.md"
date_str="$(date +%Y-%m-%d)"

printf -- '- [%s] %s: %s\n' "$tag" "$date_str" "$note" >> "$file"
