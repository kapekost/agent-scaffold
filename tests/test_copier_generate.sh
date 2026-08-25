#!/usr/bin/env bash
set -euo pipefail

# Runs `copier copy` against this repo and asserts the rendered output is
# correct. Extended by later tasks — do not create a second test file.

root="$(git rev-parse --show-toplevel)"
tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT

~/.local/bin/copier copy --defaults --trust \
  --data project_name="Test Project" \
  --data project_slug="test-project" \
  --data description="A test project" \
  --data github_owner="testowner" \
  --data default_branch="main" \
  "$root" "$tmp"

fail=0
assert_file() {
  if [[ ! -f "$tmp/$1" ]]; then
    echo "FAIL: missing $1" >&2
    fail=1
  fi
}
assert_contains() {
  if ! grep -qF -- "$2" "$tmp/$1" 2>/dev/null; then
    echo "FAIL: $1 does not contain: $2" >&2
    fail=1
  fi
}

assert_file "AGENTS.md"
assert_contains "AGENTS.md" "# Test Project"

if [[ "$fail" -eq 0 ]]; then
  echo "PASS: test_copier_generate.sh"
else
  exit 1
fi
