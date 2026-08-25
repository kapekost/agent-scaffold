#!/usr/bin/env bash
set -euo pipefail

# Moves the last-reviewed cursor forward. Usage: advance_improvements_cursor.sh <new-count>

new_count="${1:?Usage: advance_improvements_cursor.sh <new-count>}"

if ! [[ "$new_count" =~ ^[0-9]+$ ]]; then
  echo "error: <new-count> must be a non-negative integer" >&2
  exit 1
fi

file="$(git rev-parse --show-toplevel)/docs/orchestration/IMPROVEMENTS.md"

sed -i.bak -E "s/(<!-- last-reviewed-count: )[0-9]+( -->)/\1${new_count}\2/" "$file"
rm -f "${file}.bak"
