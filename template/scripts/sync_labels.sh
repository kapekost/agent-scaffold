#!/usr/bin/env bash
set -euo pipefail

# Applies .github/labels.yml to the current repo via `gh label create`.
# Usage: sync_labels.sh [--dry-run]
#
# Parses labels.yml with PyYAML rather than a hand-rolled regex, so a
# reformat or a description containing a colon/quote can't silently
# desync this script's idea of the label set from the file CI validates.

dry_run=false
if [[ "${1:-}" == "--dry-run" ]]; then
  dry_run=true
fi

root="$(git rev-parse --show-toplevel)"
labels_file="$root/.github/labels.yml"

python3 -c "import yaml" 2>/dev/null || {
  echo "sync_labels.sh needs PyYAML: pip install pyyaml (or: pip install -r <(echo pyyaml))" >&2
  exit 1
}

python3 - "$labels_file" <<'PY' | while IFS=$'\t' read -r name color description; do
import sys, yaml

with open(sys.argv[1]) as f:
    labels = yaml.safe_load(f)

for label in labels:
    # Tab-separated: name/color/description must not contain a literal tab.
    print(f"{label['name']}\t{label['color']}\t{label.get('description', '')}")
PY
  if [[ "$dry_run" == true ]]; then
    echo "gh label create \"$name\" --color \"$color\" --description \"$description\" --force"
  else
    gh label create "$name" --color "$color" --description "$description" --force
  fi
done
