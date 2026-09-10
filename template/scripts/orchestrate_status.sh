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
