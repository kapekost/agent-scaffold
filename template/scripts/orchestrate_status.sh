#!/usr/bin/env bash
set -euo pipefail

# Computes /orchestrate status's report: READY, IN PROGRESS, BLOCKED, NEEDS
# OWNER, INTAKE, IMPROVEMENTS -- recomputed live every call from Issue
# labels and the orchestration home branch's own STATE.md/IMPROVEMENTS.md,
# never from stored state, so nothing here can go stale the way the
# Project board's Status field did (see the design spec this implements:
# docs/superpowers/specs/2026-09-10-orchestrate-status-report-design.md).
#
# Usage: orchestrate_status.sh [--owner OWNER]
#
# Reads docs/orchestration/STATE.md.jinja's "Home branch"/"Project number"
# header fields from the working tree first (cheap, no git show needed),
# then re-reads the live Cursor/In-flight/Needs-owner/IMPROVEMENTS content
# from that home branch if one is set, or the working tree otherwise.

# --- pure parsing functions (no gh, no network; unit-tested directly) ---

parse_home_branch() {
  grep -m1 -oE '\*\*Home branch:\*\* `[^`]+`' <<<"$1" | sed -E 's/.*`([^`]+)`.*/\1/' || true
}

parse_project_number() {
  grep -m1 -oE '\*\*Project number:\*\* [0-9]+' <<<"$1" | grep -oE '[0-9]+' || true
}

# Extracts the body between "## <heading>" and the next "## " heading (or
# EOF), exclusive of both heading lines.
extract_section() {
  local content="$1" heading="$2"
  awk -v h="## ${heading}" '
    $0 == h { found=1; next }
    found && /^## / { exit }
    found { print }
  ' <<<"$content"
}

count_top_bullets() {
  grep -c '^- ' <<<"$1" 2>/dev/null || true
}

# Joins each top-level "- " bullet's wrapped continuation lines into one
# string (undoing the source markdown's hard-wrapping), then joins multiple
# bullets with "; ". This is a glance aid, not a full-fidelity copy --
# STATE.md itself is still the place to read the whole entry.
summarize_bullets() {
  awk '
    /^- / {
      if (buf != "") { out = (out == "" ? buf : out "; " buf) }
      buf = $0
      sub(/^- /, "", buf)
      next
    }
    /^[ \t]+[^ \t]/ {
      line = $0
      sub(/^[ \t]+/, "", line)
      buf = buf " " line
      next
    }
    END {
      if (buf != "") { out = (out == "" ? buf : out "; " buf) }
      print out
    }
  ' <<<"$1"
}

# Prints "<total>|<unsure_count>|<oldest_unsure_date_or_empty>".
parse_improvements() {
  local content="$1" total unsure oldest
  total="$(grep -cE '^- \[(local|template|unsure)\] [0-9]{4}-[0-9]{2}-[0-9]{2}:' <<<"$content" 2>/dev/null || true)"
  unsure="$(grep -cE '^- \[unsure\] [0-9]{4}-[0-9]{2}-[0-9]{2}:' <<<"$content" 2>/dev/null || true)"
  oldest="$(grep -m1 -E '^- \[unsure\] [0-9]{4}-[0-9]{2}-[0-9]{2}:' <<<"$content" 2>/dev/null \
    | grep -oE '[0-9]{4}-[0-9]{2}-[0-9]{2}' || true)"
  printf '%s|%s|%s\n' "${total:-0}" "${unsure:-0}" "${oldest:-}"
}

# Portable day-count between a YYYY-MM-DD date and now: GNU date first
# (Linux CI / cloud agents), BSD date as fallback (macOS, the owner's
# actual machine) -- do not assume either alone.
days_since() {
  local date_str="$1" then_epoch now_epoch
  then_epoch="$(date -u -d "$date_str" +%s 2>/dev/null || date -u -jf '%Y-%m-%d' "$date_str" +%s 2>/dev/null)"
  now_epoch="$(date -u +%s)"
  echo $(( (now_epoch - then_epoch) / 86400 ))
}

# --- gh-dependent line builders (not unit-tested here -- no fake-gh
# precedent in this repo; verified empirically against a real repo instead,
# see the plan's Task 4) ---

# $1: label. Prints "<label-upper> (<n>): #a, #b, ..." or "<label-upper> (0)".
issue_line() {
  local label="$1" heading="$2"
  local nums
  nums="$(gh issue list --label "$label" --state open --json number \
    --jq '[.[].number] | map("#" + (. | tostring)) | join(", ")' 2>/dev/null || echo "")"
  local count=0
  [[ -n "$nums" ]] && count="$(tr ',' '\n' <<<"$nums" | wc -l | tr -d ' ')"
  if [[ "$count" -eq 0 ]]; then
    echo "${heading} (0)"
  else
    echo "${heading} (${count}): ${nums}"
  fi
}

# $1: project number, $2: owner. READY is ranked (Project manual order),
# unlike BLOCKED/INTAKE above which don't need to be -- see the design
# spec's Section 2 and the sibling fix in PLAYBOOK.md.jinja's step 2 for
# why this uses `gh project item-list`, never `gh issue list`, for rank.
ready_line() {
  local project="$1" owner="$2" nums count=0
  if [[ -z "$project" ]]; then
    echo "READY (unknown — no Project number set in STATE.md)"
    return
  fi
  nums="$(gh project item-list "$project" --owner "$owner" --format json --limit 100 \
    --query "status:Todo label:ready" \
    --jq '[.items[].content.number] | map("#" + (. | tostring)) | join(", ")' 2>/dev/null || echo "")"
  [[ -n "$nums" ]] && count="$(tr ',' '\n' <<<"$nums" | wc -l | tr -d ' ')"
  if [[ "$count" -eq 0 ]]; then
    echo "READY (0)"
  else
    echo "READY (${count}): ${nums}"
  fi
}

main() {
  local owner="@me"
  while [[ $# -gt 0 ]]; do
    case "$1" in
      --owner) owner="$2"; shift 2 ;;
      *) echo "error: unknown argument $1" >&2; return 2 ;;
    esac
  done

  local state_path="docs/orchestration/STATE.md"
  local improvements_path="docs/orchestration/IMPROVEMENTS.md"
  local working_tree_state
  working_tree_state="$(cat "$state_path")"

  local home_branch project_number
  home_branch="$(parse_home_branch "$working_tree_state")"
  project_number="$(parse_project_number "$working_tree_state")"

  local state_content improvements_content
  if [[ -n "$home_branch" ]]; then
    state_content="$(git show "origin/${home_branch}:${state_path}")"
    improvements_content="$(git show "origin/${home_branch}:${improvements_path}")"
  else
    state_content="$working_tree_state"
    improvements_content="$(cat "$improvements_path")"
  fi

  ready_line "$project_number" "$owner"
  local in_flight needs_owner
  in_flight="$(extract_section "$state_content" "In-flight")"
  needs_owner="$(extract_section "$state_content" "Needs owner")"

  local in_flight_count needs_owner_count
  in_flight_count="$(count_top_bullets "$in_flight")"
  needs_owner_count="$(count_top_bullets "$needs_owner")"

  if [[ "${in_flight_count:-0}" -eq 0 ]]; then
    echo "IN PROGRESS (0)"
  else
    echo "IN PROGRESS (${in_flight_count}): $(summarize_bullets "$in_flight")"
  fi

  issue_line "blocked" "BLOCKED"

  if [[ "${needs_owner_count:-0}" -eq 0 ]]; then
    echo "NEEDS OWNER (0)"
  else
    echo "NEEDS OWNER (${needs_owner_count}): $(summarize_bullets "$needs_owner")"
  fi

  issue_line "intake" "INTAKE"

  local imp total unsure oldest
  imp="$(parse_improvements "$improvements_content")"
  IFS='|' read -r total unsure oldest <<<"$imp"
  if [[ -z "$oldest" ]]; then
    echo "IMPROVEMENTS: ${total} logged, ${unsure} [unsure] open"
  else
    echo "IMPROVEMENTS: ${total} logged, ${unsure} [unsure] open (oldest: $(days_since "$oldest") days)"
  fi
}

if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
  main "$@"
fi
