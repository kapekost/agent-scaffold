#!/usr/bin/env bash
set -euo pipefail

# Creates a Kanban board view on a GitHub Projects v2 board, grouped by the
# Status field. Idempotent: if a BOARD_LAYOUT view already exists, prints its
# URL and exits rather than creating a duplicate.
#
# Usage: create_board_view.sh <owner> <project-number> [view-name]
#
# GitHub's public GraphQL API has no way to set a view's group-by field
# directly (ProjectV2ViewConfigurationInput only exposes visibleFieldIds) —
# but a freshly created BOARD_LAYOUT view groups by the Status single-select
# field automatically, with no manual step required. Verified empirically
# 2026-09-10: a view created by this exact mutation immediately showed real
# Todo/In Progress/Done columns matching each item's actual Status value.

owner="${1:?Usage: create_board_view.sh <owner> <project-number> [view-name]}"
project_number="${2:?Usage: create_board_view.sh <owner> <project-number> [view-name]}"
view_name="${3:-Board}"

project_id="$(gh api graphql -f query='
  query($owner: String!, $number: Int!) {
    user(login: $owner) { projectV2(number: $number) { id } }
  }' -f owner="$owner" -F number="$project_number" --jq '.data.user.projectV2.id')"

if [[ -z "$project_id" || "$project_id" == "null" ]]; then
  echo "error: no project #$project_number found for owner $owner" >&2
  exit 1
fi

existing_view_number="$(gh api graphql -f query='
  query($owner: String!, $number: Int!) {
    user(login: $owner) {
      projectV2(number: $number) {
        views(first: 20) { nodes { number layout } }
      }
    }
  }' -f owner="$owner" -F number="$project_number" \
  --jq '.data.user.projectV2.views.nodes[] | select(.layout == "BOARD_LAYOUT") | .number' | head -1)"

if [[ -n "$existing_view_number" ]]; then
  echo "Board view already exists: https://github.com/users/$owner/projects/$project_number/views/$existing_view_number"
  exit 0
fi

new_view_number="$(gh api graphql -f query='
  mutation($projectId: ID!, $name: String!) {
    createProjectV2View(input: {projectId: $projectId, name: $name, layout: BOARD_LAYOUT}) {
      projectV2View { number }
    }
  }' -f projectId="$project_id" -f name="$view_name" \
  --jq '.data.createProjectV2View.projectV2View.number')"

echo "Created board view: https://github.com/users/$owner/projects/$project_number/views/$new_view_number"
