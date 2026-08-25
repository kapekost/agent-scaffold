#!/usr/bin/env bash
set -euo pipefail

root="$(git rev-parse --show-toplevel)"
tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT

git -C "$tmp" init -q
mkdir -p "$tmp/.github" "$tmp/scripts"
cp "$root/template/scripts/sync_labels.sh" "$tmp/scripts/"
cp "$root/template/.github/labels.yml" "$tmp/.github/"

cd "$tmp"
out="$(bash scripts/sync_labels.sh --dry-run)"

fail=0
assert_contains() {
  if ! grep -qF -- "$1" <<<"$out"; then
    echo "FAIL: dry-run output missing: $1" >&2
    fail=1
  fi
}

assert_contains 'gh label create "type:bug" --color "D73A4A" --description "Something broken" --force'
assert_contains 'gh label create "ready" --color "0E8A16" --description "Triaged and ready for /orchestrate to pick up" --force'

line_count="$(printf '%s\n' "$out" | wc -l | tr -d ' ')"
if [[ "$line_count" -ne 16 ]]; then
  echo "FAIL: expected 16 label commands, got $line_count" >&2
  fail=1
fi

if [[ "$fail" -eq 0 ]]; then
  echo "PASS: test_sync_labels.sh"
else
  exit 1
fi
