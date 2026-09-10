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
- **#125** — claimed 2026-09-10T03:54:12Z, **paused** (owner-requested checkpoint for a laptop
  restart, not abandoned).

## Needs owner
(nothing pending)
'

in_flight="$(extract_section "$state_doc" "In-flight")"
assert_eq "$(count_top_bullets "$in_flight")" "1"

needs_owner="$(extract_section "$state_doc" "Needs owner")"
assert_eq "$(count_top_bullets "$needs_owner")" "0"

# --- summarize_bullets: joins wrapped continuation lines, one summary per bullet ---

summary="$(summarize_bullets "$in_flight")"
assert_eq "$summary" "**#125** — claimed 2026-09-10T03:54:12Z, **paused** (owner-requested checkpoint for a laptop restart, not abandoned)."

multi='- first item, short
- second item, also short'
assert_eq "$(summarize_bullets "$multi")" "first item, short; second item, also short"

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

if [[ "$fail" -eq 0 ]]; then
  echo "PASS: test_orchestrate_status.sh"
else
  exit 1
fi
