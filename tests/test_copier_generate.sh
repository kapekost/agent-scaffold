#!/usr/bin/env bash
set -euo pipefail

# Runs `copier copy` against this repo and asserts the rendered output is
# correct. Extended by later tasks — do not create a second test file.

export PATH="$HOME/.local/bin:$PATH"
root="$(git rev-parse --show-toplevel)"
tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT

copier copy --defaults --trust \
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

assert_file ".github/ISSUE_TEMPLATE/config.yml"
assert_file ".github/ISSUE_TEMPLATE/bug.yml"
assert_file ".github/ISSUE_TEMPLATE/feature.yml"
assert_file ".github/ISSUE_TEMPLATE/chore.yml"
assert_file ".github/PULL_REQUEST_TEMPLATE.md"
assert_file ".github/CODEOWNERS"
assert_contains ".github/CODEOWNERS" "@testowner"
assert_file ".github/labels.yml"
assert_contains ".github/labels.yml" 'name: "effort:L"'
assert_file ".github/dependabot.yml"
assert_file ".github/workflows/ci.yml"
assert_contains ".github/workflows/ci.yml" "branches: [main]"
assert_contains ".github/workflows/ci.yml" '${{ github.ref }}'

assert_file "docs/orchestration/PLAYBOOK.md"
assert_file "docs/orchestration/GUARDRAILS.md"
assert_contains "docs/orchestration/GUARDRAILS.md" "more than 40 files"
assert_file "docs/orchestration/STATE.md"
assert_contains "docs/orchestration/STATE.md" "**Project:** Test Project"
assert_file "docs/orchestration/DECISIONS.md"
assert_file "docs/orchestration/IMPROVEMENTS.md"
assert_contains "docs/orchestration/IMPROVEMENTS.md" "last-reviewed-count: 0"

if [[ "$fail" -eq 0 ]]; then
  echo "PASS: test_copier_generate.sh"
else
  exit 1
fi
