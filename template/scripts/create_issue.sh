#!/usr/bin/env bash
set -euo pipefail

# The one sanctioned way to create an Issue that /orchestrate or a human should ever
# see -- a bare `gh issue create` has caused two distinct classes of invisible-Issue
# bug in this repo's history, because it bypasses both things this script does
# atomically:
#   1. No state label (`ready`/`intake`/`needs-clarification`) -- IMPROVEMENTS.md
#      2026-09-02: a child created during an intake split landed with type/priority/
#      effort but no state label, invisible to every label-filtered query for 3 days.
#   2. Not added to the Project board -- discovered 2026-09-13: 9 newly filed
#      `intake` Issues (plus 7 pre-existing open ones, including 3 already `ready`)
#      existed only as bare Issues, invisible to /orchestrate's actual picking query
#      (`gh project item-list ... --query "status:Todo label:ready"`), which reads
#      the board, never `gh issue list`.
#
# This script makes both mandatory in one call: create -> label with a required
# state -> add to the Project board -> set Status. Never call `gh issue create`
# directly for a Feature Intake capture or a triaged Issue (GUARDRAILS.md).
#
# Usage:
#   create_issue.sh <intake|ready|needs-clarification> --title "..." \
#     --body-file <path> [--label "type:feature,priority:P2,..."] \
#     [--project N] [--owner LOGIN] [--status "Todo|In Progress|Done"]
#
# --project/--owner default to STATE.md's "Project number"/"Project owner" header
# fields (working-tree copy -- cheap, no `git show` needed, same convention
# orchestrate_status.sh uses). --status defaults to "Todo" -- a freshly created
# Issue is, by definition, not yet in progress or done.

state_label="${1:?Usage: create_issue.sh <intake|ready|needs-clarification> --title ... --body-file ...}"
shift
case "$state_label" in
  intake|ready|needs-clarification) ;;
  *) echo "error: first argument must be one of intake, ready, needs-clarification (got '$state_label')" >&2; exit 1 ;;
esac

title=""
body_file=""
extra_labels=""
project_number=""
owner=""
status="Todo"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --title) title="$2"; shift 2 ;;
    --body-file) body_file="$2"; shift 2 ;;
    --label) extra_labels="$2"; shift 2 ;;
    --project) project_number="$2"; shift 2 ;;
    --owner) owner="$2"; shift 2 ;;
    --status) status="$2"; shift 2 ;;
    *) echo "error: unknown argument '$1'" >&2; exit 1 ;;
  esac
done

[[ -n "$title" ]] || { echo "error: --title is required" >&2; exit 1; }
[[ -n "$body_file" ]] || { echo "error: --body-file is required" >&2; exit 1; }

state_file="$(git rev-parse --show-toplevel)/docs/orchestration/STATE.md"

if [[ -z "$project_number" && -f "$state_file" ]]; then
  project_number="$(grep -m1 -oE '\*\*Project number:\*\* [0-9]+' "$state_file" | grep -oE '[0-9]+' || true)"
fi
if [[ -z "$owner" && -f "$state_file" ]]; then
  owner="$(grep -m1 -oE '\*\*Project owner:\*\* @?[A-Za-z0-9][A-Za-z0-9_.-]*' "$state_file" | sed -E 's/.*\*\* //' || true)"
fi
owner="${owner:-@me}"

[[ -n "$project_number" ]] || { echo "error: no --project given and no Project number found in STATE.md" >&2; exit 1; }

labels="$state_label"
[[ -n "$extra_labels" ]] && labels="$labels,$extra_labels"

issue_url="$(gh issue create --title "$title" --body-file "$body_file" --label "$labels")"
issue_number="${issue_url##*/}"

project_id="$(gh project view "$project_number" --owner "$owner" --format json -q '.id')"
field_json="$(gh project field-list "$project_number" --owner "$owner" --format json)"
status_field_id="$(jq -r '.fields[] | select(.name=="Status") | .id' <<<"$field_json")"
status_option_id="$(jq -r --arg s "$status" '.fields[] | select(.name=="Status") | .options[] | select(.name==$s) | .id' <<<"$field_json")"

if [[ -z "$status_field_id" || -z "$status_option_id" ]]; then
  echo "warning: Issue #$issue_number created ($issue_url) but Status field/option '$status' not found on project #$project_number -- add it to the board manually" >&2
  exit 1
fi

item_id="$(gh project item-add "$project_number" --owner "$owner" --url "$issue_url" --format json -q '.id')"
gh project item-edit --id "$item_id" --project-id "$project_id" --field-id "$status_field_id" --single-select-option-id "$status_option_id" >/dev/null

echo "$issue_url"
