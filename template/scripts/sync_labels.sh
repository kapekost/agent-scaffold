#!/usr/bin/env bash
set -euo pipefail

# Applies .github/labels.yml to the current repo via `gh label create`.
# Usage: sync_labels.sh [--dry-run]

dry_run=false
if [[ "${1:-}" == "--dry-run" ]]; then
  dry_run=true
fi

root="$(git rev-parse --show-toplevel)"
labels_file="$root/.github/labels.yml"

# Minimal parser for this repo's own labels.yml format (avoids a yq
# dependency): each entry is "- name: X" then "  color: Y" then
# "  description: Z", in that order.
name=""
color=""
description=""

apply_label() {
  local n="$1" c="$2" d="$3"
  if $dry_run; then
    echo "gh label create \"$n\" --color \"$c\" --description \"$d\" --force"
    return
  fi
  gh label create "$n" --color "$c" --description "$d" --force
}

while IFS= read -r line; do
  if [[ "$line" =~ ^-\ name:\ \"?([^\"]*)\"?$ ]]; then
    if [[ -n "$name" ]]; then
      apply_label "$name" "$color" "$description"
    fi
    name="${BASH_REMATCH[1]}"
    color=""
    description=""
  elif [[ "$line" =~ ^\ \ color:\ \"?([^\"]*)\"?$ ]]; then
    color="${BASH_REMATCH[1]}"
  elif [[ "$line" =~ ^\ \ description:\ \"?([^\"]*)\"?$ ]]; then
    description="${BASH_REMATCH[1]}"
  fi
done < "$labels_file"

if [[ -n "$name" ]]; then
  apply_label "$name" "$color" "$description"
fi
