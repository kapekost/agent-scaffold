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

assert_file "scripts/append_improvement.sh"
assert_file "scripts/improvements_since_cursor.sh"
assert_file "scripts/advance_improvements_cursor.sh"
assert_file "scripts/sync_labels.sh"

assert_file ".claude/settings.json"
assert_file ".mcp.json.example"
assert_contains ".mcp.json.example" "GITHUB_PERSONAL_ACCESS_TOKEN"

# .mcp.json.example must never contain a real-looking credential.
if grep -Eq '(sk-[A-Za-z0-9]{20,}|ghp_[A-Za-z0-9]{30,})' "$tmp/.mcp.json.example"; then
  echo "FAIL: .mcp.json.example appears to contain a real credential" >&2
  fail=1
fi

assert_file ".claude/commands/orchestrate.md"
assert_contains ".claude/commands/orchestrate.md" "You are the Test Project orchestration controller."
assert_contains ".claude/commands/orchestrate.md" "review-feedback"
assert_contains ".claude/commands/orchestrate.md" "never auto-merge"

# Full-tree sanity: every file under template/ must appear in the
# generated output with its .jinja suffix stripped, and nothing else.
# template/{{ _copier_conf.answers_file }}.jinja renders to
# .copier-answers.yml, so that file is counted on both sides — no
# exclusion needed.
expected_count="$(find "$root/template" -type f | wc -l | tr -d ' ')"
actual_count="$(find "$tmp" -type f -not -path '*/.git/*' | wc -l | tr -d ' ')"
if [[ "$expected_count" != "$actual_count" ]]; then
  echo "FAIL: expected $expected_count generated files, got $actual_count" >&2
  fail=1
fi

assert_file ".copier-answers.yml"
assert_contains ".copier-answers.yml" "_src_path"

if [[ "$fail" -eq 0 ]]; then
  echo "PASS: test_copier_generate.sh"
else
  exit 1
fi
