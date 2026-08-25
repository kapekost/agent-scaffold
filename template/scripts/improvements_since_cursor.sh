#!/usr/bin/env bash
set -euo pipefail

# Prints IMPROVEMENTS.md log entries appended since the last-reviewed cursor.

file="$(git rev-parse --show-toplevel)/docs/orchestration/IMPROVEMENTS.md"

cursor="$(grep -o '<!-- last-reviewed-count: [0-9]* -->' "$file" | head -1 | grep -o '[0-9]*')"

# Use awk to extract log entries and print only those after cursor position
awk -v cursor="$cursor" '
  /^## Log$/ { found=1; next }
  found && /^- \[/ {
    if (count >= cursor) print
    count++
  }
' "$file"

