#!/usr/bin/env bash
set -euo pipefail

# Unit tests for the three improvements-log scripts. Runs them inside an
# isolated scratch git repo (the scripts resolve paths via `git rev-parse
# --show-toplevel`, so they must run inside *some* git repo, and a scratch
# one avoids mutating this repo's own IMPROVEMENTS.md).

root="$(git rev-parse --show-toplevel)"
tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT

git -C "$tmp" init -q
mkdir -p "$tmp/docs/orchestration" "$tmp/scripts"
cp "$root/template/scripts/append_improvement.sh" "$tmp/scripts/"
cp "$root/template/scripts/improvements_since_cursor.sh" "$tmp/scripts/"
cp "$root/template/scripts/advance_improvements_cursor.sh" "$tmp/scripts/"
cp "$root/template/docs/orchestration/IMPROVEMENTS.md" "$tmp/docs/orchestration/"

fail=0
assert_eq() {
  if [[ "$1" != "$2" ]]; then
    echo "FAIL: expected [$2], got [$1]" >&2
    fail=1
  fi
}

cd "$tmp"

# No entries yet: since_cursor prints nothing.
out="$(bash scripts/improvements_since_cursor.sh)"
assert_eq "$out" ""

# Append two entries; both should show up as unreviewed.
bash scripts/append_improvement.sh local "first note"
bash scripts/append_improvement.sh template "second note"
out="$(bash scripts/improvements_since_cursor.sh)"
count="$(printf '%s\n' "$out" | grep -c '^- \[' || true)"
assert_eq "$count" "2"

# Advance the cursor to 2; since_cursor now prints nothing new.
bash scripts/advance_improvements_cursor.sh 2
out="$(bash scripts/improvements_since_cursor.sh)"
assert_eq "$out" ""

# Append a third entry; only the new one should show up.
bash scripts/append_improvement.sh unsure "third note"
out="$(bash scripts/improvements_since_cursor.sh)"
assert_eq "$out" "- [unsure] $(date +%Y-%m-%d): third note"

# Reject an invalid tag.
if bash scripts/append_improvement.sh bogus "bad" 2>/dev/null; then
  echo "FAIL: expected append_improvement.sh to reject an invalid tag" >&2
  fail=1
fi

if [[ "$fail" -eq 0 ]]; then
  echo "PASS: test_improvements_scripts.sh"
else
  exit 1
fi
