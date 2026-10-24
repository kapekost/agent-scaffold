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
assert_file ".github/workflows/scaffold-sanity.yml"
assert_contains ".github/workflows/scaffold-sanity.yml" "branches: [main]"
assert_contains ".github/workflows/scaffold-sanity.yml" '${{ github.ref }}'

assert_file "docs/orchestration/PLAYBOOK.md"
assert_contains "docs/orchestration/PLAYBOOK.md" "gh pr checks"
assert_file "docs/orchestration/GUARDRAILS.md"
assert_contains "docs/orchestration/GUARDRAILS.md" "more than 40 files"
assert_file "docs/orchestration/README.md"
assert_contains "docs/orchestration/README.md" "# Test Project — Orchestration: who does what"
assert_contains "docs/orchestration/README.md" "PushNotification"
assert_file "docs/orchestration/STATE.md"
assert_contains "docs/orchestration/STATE.md" "**Project:** Test Project"
assert_contains "docs/orchestration/STATE.md" "Hard budget"
assert_file "docs/orchestration/HISTORY.md"
assert_contains "docs/orchestration/HISTORY.md" "No tick reads this file"
assert_file "docs/orchestration/DECISIONS.md"
assert_file "docs/orchestration/IMPROVEMENTS.md"
assert_contains "docs/orchestration/IMPROVEMENTS.md" "last-reviewed-count: 0"

assert_file "scripts/append_improvement.sh"
assert_file "scripts/improvements_since_cursor.sh"
assert_file "scripts/advance_improvements_cursor.sh"
assert_file "scripts/sync_labels.sh"
assert_file "scripts/orchestrate_status.sh"
assert_file "scripts/create_board_view.sh"
assert_file "scripts/create_issue.sh"

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
expected_count="$(find "$root/template" -type f -not -path '*/tests/reviewer/*' -not -name 'post_review.py' \
  -not -name 'review_input.py.jinja' -not -name 'resolve_review_threads.sh' -not -name 'opencode-review.yml.jinja' | wc -l | tr -d ' ')"
actual_count="$(find "$tmp" -type f -not -path '*/.git/*' | wc -l | tr -d ' ')"
if [[ "$expected_count" != "$actual_count" ]]; then
  echo "FAIL: expected $expected_count generated files, got $actual_count" >&2
  fail=1
fi

assert_file ".copier-answers.yml"
assert_contains ".copier-answers.yml" "_src_path"

# No leftover Jinja syntax should survive rendering anywhere in the output
# tree. GitHub Actions' own ${{ ... }} expressions are legitimate and must
# not trip this check; a bare {{ ... }} (no leading $) or any {% ... %} tag
# means a .jinja file failed to render or a raw block leaked.
if grep -rn '{%' "$tmp" --include='*' 2>/dev/null | grep -v '/.copier-answers.yml:'; then
  echo "FAIL: unrendered Jinja tag syntax ({% %}) found in generated output" >&2
  fail=1
fi
if grep -rn '{{' "$tmp" --include='*' 2>/dev/null | grep -vF '${{' | grep -v '/.copier-answers.yml:'; then
  echo "FAIL: unrendered Jinja expression syntax ({{ }}) found in generated output" >&2
  fail=1
fi

# The reviewer is opt-in: absent by default, present and testable when asked for.
for f in .github/workflows/opencode-review.yml scripts/post_review.py scripts/review_input.py \
         scripts/resolve_review_threads.sh tests/reviewer; do
  if [[ -e "$tmp/$f" ]]; then
    echo "FAIL: $f exists although include_reviewer defaults to false" >&2
    fail=1
  fi
done

render_reviewer() {  # $1 = public|private, $2 = output dir
  copier copy --defaults --trust \
    --data project_name="Test Project" --data project_slug="test-project" \
    --data github_owner="testowner" --data include_reviewer=true --data repo_visibility="$1" \
    --data 'reviewer_source_prefixes=["app/"]' --data 'reviewer_lockfiles=["package-lock.json"]' \
    "$root" "$2" >/dev/null 2>&1
}
for vis in public private; do
  out="$(mktemp -d)"
  render_reviewer "$vis" "$out"
  wf="$out/.github/workflows/opencode-review.yml"
  [[ -f "$wf" ]] || { echo "FAIL: no reviewer workflow rendered ($vis)" >&2; fail=1; continue; }
  python3 -c "import sys, yaml; yaml.safe_load(open(sys.argv[1]))" "$wf" || { echo "FAIL: $vis workflow is not YAML" >&2; fail=1; }
  if grep -rn '{%' "$out" | grep -v '/.copier-answers.yml:'; then echo "FAIL: stray Jinja tag ($vis)" >&2; fail=1; fi
  if grep -rn '{{' "$out" | grep -vF '${{' | grep -v '/.copier-answers.yml:'; then echo "FAIL: stray Jinja expression ($vis)" >&2; fail=1; fi
  if [[ "$vis" == public ]]; then
    grep -qF 'permissions: {}' "$wf" || { echo "FAIL: public review job should hold no token scopes" >&2; fail=1; }
    grep -qF 'repository_owner' "$wf" || { echo "FAIL: public repo should review owner PRs only" >&2; fail=1; }
  else
    grep -qF 'persist-credentials: false' "$wf" || { echo "FAIL: private checkout should not persist credentials" >&2; fail=1; }
    ! grep -qF 'repository_owner' "$wf" || { echo "FAIL: private repo should not gate on owner" >&2; fail=1; }
    ! grep -qF 'open/' "$wf" || { echo "FAIL: private repo must not fall back to models without data_collection deny" >&2; fail=1; }
  fi
  grep -qF 'OPENCODE_DISABLE_PROJECT_CONFIG' "$wf" || { echo "FAIL: project config not disabled ($vis)" >&2; fail=1; }
  grep -qF '"app/"' "$out/scripts/review_input.py" || { echo "FAIL: source prefixes not rendered ($vis)" >&2; fail=1; }
  for s in post_review.py resolve_review_threads.sh; do
    cmp -s "$root/template/scripts/$s" "$out/scripts/$s" || { echo "FAIL: scripts/$s is not byte-identical ($vis)" >&2; fail=1; }
  done
  command -v actionlint >/dev/null && { actionlint "$wf" || { echo "FAIL: actionlint ($vis)" >&2; fail=1; }; }
  (cd "$out" && PYTHONDONTWRITEBYTECODE=1 python3 -m pytest tests/reviewer -q -p no:cacheprovider >/dev/null 2>&1) \
    || { echo "FAIL: the shipped reviewer tests fail ($vis)" >&2; fail=1; }
done

if [[ "$fail" -eq 0 ]]; then
  echo "PASS: test_copier_generate.sh"
else
  exit 1
fi
