#!/usr/bin/env bash
set -euo pipefail

# Unit tests for orchestrate_status.sh's pure parsing functions (no gh, no
# network). Modeled on tests/test_improvements_scripts.sh's scratch-repo
# pattern, but sources the script directly to call its functions rather
# than only checking stdout from a full run.

root="$(git rev-parse --show-toplevel)"

fail=0
assert_eq() {
  if [[ "$1" != "$2" ]]; then
    echo "FAIL: expected [$2], got [$1]" >&2
    fail=1
  fi
}

# shellcheck source=/dev/null
source "$root/template/scripts/orchestrate_status.sh"

# --- parse_home_branch / parse_project_number ---

state_with_branch='> **Home branch:** `claude/foo-backlog`
> **Project number:** 7'
assert_eq "$(parse_home_branch "$state_with_branch")" "claude/foo-backlog"
assert_eq "$(parse_project_number "$state_with_branch")" "7"

state_without_branch='> **Home branch:** (none — this repo commits orchestration docs straight to `main`)
> **Project number:** (none yet — create one with `gh project create`)'
assert_eq "$(parse_home_branch "$state_without_branch")" ""
assert_eq "$(parse_project_number "$state_without_branch")" ""

# --- extract_section ---

state_doc='# Orchestration State

## Cursor
- **Project:** Foo

## In-flight
- **#125** — claimed 2026-09-10T03:54:12Z, **paused**
  (owner-requested, not abandoned).

## Needs owner
(nothing pending)
'

in_flight="$(extract_section "$state_doc" "In-flight")"
assert_eq "$(count_top_bullets "$in_flight")" "1"

needs_owner="$(extract_section "$state_doc" "Needs owner")"
assert_eq "$(count_top_bullets "$needs_owner")" "0"

# --- summarize_bullets: joins wrapped continuation lines, one summary per bullet ---

summary="$(summarize_bullets "$in_flight")"
assert_eq "$summary" "**#125** — claimed 2026-09-10T03:54:12Z, **paused** (owner-requested, not abandoned)."

multi='- first item, short
- second item, also short'
assert_eq "$(summarize_bullets "$multi")" "first item, short; second item, also short"

# --- summarize_bullets: per-bullet truncation at 110 chars (fix for the
# 572-char single line a real STATE.md entry produced) ---

long_bullet='- **#130** — claimed 2026-09-10T04:00:00Z, **blocked** (waiting on upstream API access grant
  that has been pending for several days now with no clear resolution timeline in sight at all).'
long_summary="$(summarize_bullets "$long_bullet")"
assert_eq "${#long_summary}" "110"
assert_eq "$long_summary" "**#130** — claimed 2026-09-10T04:00:00Z, **blocked** (waiting on upstream API access grant that has been pend…"

short_bullet='- short and under the limit'
assert_eq "$(summarize_bullets "$short_bullet")" "short and under the limit"

# A long bullet alongside a short one: only the long one is truncated, the
# short one is untouched (truncation is per-bullet, not on the joined string).
mixed="${long_bullet}
- short one"
mixed_summary="$(summarize_bullets "$mixed")"
assert_eq "$mixed_summary" "**#130** — claimed 2026-09-10T04:00:00Z, **blocked** (waiting on upstream API access grant that has been pend…; short one"

# --- parse_improvements ---

improvements_doc='# Improvements Log

<!-- last-reviewed-count: 1 -->

## Log
- [local] 2026-08-30: first note
- [unsure] 2026-08-31: second note
- [unsure] 2026-09-05: third note
'
result="$(parse_improvements "$improvements_doc")"
assert_eq "$result" "3|2|2026-08-31"

empty_improvements='# Improvements Log

<!-- last-reviewed-count: 0 -->

## Log
'
assert_eq "$(parse_improvements "$empty_improvements")" "0|0|"

# --- days_since ---

# Exact value is time-dependent, so just assert it is a non-negative integer
# and that a date further in the past yields a larger count than a recent one.
older="$(days_since "2020-01-01")"
newer="$(days_since "$(date -u +%Y-%m-%d)")"
if ! [[ "$older" =~ ^[0-9]+$ ]]; then
  echo "FAIL: days_since did not return an integer: [$older]" >&2
  fail=1
fi
if (( older <= newer )); then
  echo "FAIL: expected days_since(2020-01-01) > days_since(today), got $older vs $newer" >&2
  fail=1
fi

# --- end-to-end: main() from a subdirectory, no gh remote --------------------
# Covers fix #1 (cwd-relative paths break the script outside repo root) and
# fix #3 (gh failures report "unknown", not a false "(0)") together, by
# actually invoking gh and letting it fail (a real integration test, not a
# pure-function one).

e2e_tmp="$(mktemp -d)"
mkdir -p "$e2e_tmp/docs/orchestration" "$e2e_tmp/subdir"
cat > "$e2e_tmp/docs/orchestration/STATE.md" << 'STATEEOF'
# Orchestration State

> **Home branch:** (none — this repo commits orchestration docs straight to `main`)
> **Project number:** (none yet — create one with `gh project create`)
> **Project owner:** (defaults to `@me`, the authenticated `gh` user)

## Cursor
- **Project:** Test

## In-flight
(no branches in flight)

## Needs owner
(nothing pending)
STATEEOF
cat > "$e2e_tmp/docs/orchestration/IMPROVEMENTS.md" << 'IMPEOF'
# Improvements Log

<!-- last-reviewed-count: 0 -->

## Log
IMPEOF
(cd "$e2e_tmp" && git init -q .)
e2e_exit=0
# `|| e2e_exit=$?` (not a bare `e2e_exit=$?` on the next line) so a non-zero
# exit from the script under test doesn't itself trip this test file's own
# `set -e` before the exit status can be inspected below.
e2e_output="$(cd "$e2e_tmp/subdir" && bash "$root/template/scripts/orchestrate_status.sh" 2>&1)" || e2e_exit=$?
rm -rf "$e2e_tmp"

if [[ "$e2e_exit" -ne 0 ]]; then
  echo "FAIL: end-to-end run from subdirectory exited $e2e_exit, expected 0. Output: $e2e_output" >&2
  fail=1
fi
if ! grep -q "READY (unknown" <<<"$e2e_output"; then
  echo "FAIL: expected READY (unknown ...) with no project number set, got: $e2e_output" >&2
  fail=1
fi
if ! grep -qE "^BLOCKED \(unknown" <<<"$e2e_output"; then
  echo "FAIL: expected BLOCKED (unknown ...) with no gh remote, got: $e2e_output" >&2
  fail=1
fi

# --- gh project item-list failure: ready_line should report unknown, not (0) ---
# Tests that when a project number IS set but gh project item-list fails
# (auth error, no remote, etc.), the output says "unknown" not "(0)".

ready_test_tmp="$(mktemp -d)"
mkdir -p "$ready_test_tmp/docs/orchestration"
cat > "$ready_test_tmp/docs/orchestration/STATE.md" << 'STATEEOF'
# Orchestration State

> **Home branch:** (none — this repo commits orchestration docs straight to `main`)
> **Project number:** 999
> **Project owner:** (defaults to `@me`, the authenticated `gh` user)

## Cursor
- **Project:** Test

## In-flight
(no branches in flight)

## Needs owner
(nothing pending)
STATEEOF
cat > "$ready_test_tmp/docs/orchestration/IMPROVEMENTS.md" << 'IMPEOF'
# Improvements Log

<!-- last-reviewed-count: 0 -->

## Log
IMPEOF
(cd "$ready_test_tmp" && git init -q .)
ready_test_exit=0
ready_test_output="$(cd "$ready_test_tmp" && bash "$root/template/scripts/orchestrate_status.sh" 2>&1)" || ready_test_exit=$?
rm -rf "$ready_test_tmp"

if [[ "$ready_test_exit" -ne 0 ]]; then
  echo "FAIL: ready_line test exited $ready_test_exit, expected 0. Output: $ready_test_output" >&2
  fail=1
fi
if ! grep -qE "^READY \(unknown — gh project item-list failed" <<<"$ready_test_output"; then
  echo "FAIL: expected READY (unknown — gh project item-list failed...) with project number set but no gh remote, got: $ready_test_output" >&2
  fail=1
fi

if [[ "$fail" -eq 0 ]]; then
  echo "PASS: test_orchestrate_status.sh"
else
  exit 1
fi
