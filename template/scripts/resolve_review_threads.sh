#!/usr/bin/env bash
# Resolve this bot's own review threads on a PR — and only its own.
#
# Why: a re-review that re-reports findings a human already dealt with makes the
# reader re-read the whole thread to work out what is new. Resolving the bot's own
# finished threads leaves the open ones being exactly the outstanding work, which is
# the whole point of a re-review.
#
# This is deliberately a script and not a paragraph in the workflow prompt: prose is
# advice, and "resolve the right threads" is a rule with a destructive failure mode.
# A wrong resolution hides a comment a human still wanted, and there is no undo button
# on someone else's judgement. So the limits below are mechanical:
#
#   * only threads whose FIRST comment is authored by a bot login (default
#     github-actions[bot]; override with BOT_LOGINS=bot1,bot2)
#   * only threads not already resolved
#   * never deletes, edits, or replies to a comment
#   * --dry-run prints what it would do and touches nothing
#
# Usage:
#   bash scripts/resolve_review_threads.sh <pr-number> [--dry-run]
#
# Exit 0 = done (or nothing to do). Exit 1 = something failed; note that a failure
# after some threads resolved leaves those resolved, which is why each resolution is
# reported as it happens rather than summarised at the end.

set -uo pipefail

usage() {
  echo "usage: bash scripts/resolve_review_threads.sh <pr-number> [--dry-run]" >&2
  exit 2
}

PR=""
DRY_RUN=0
for arg in "$@"; do
  case "$arg" in
    --dry-run) DRY_RUN=1 ;;
    -h|--help) usage ;;
    *) [[ -z "$PR" ]] || usage; PR="$arg" ;;
  esac
done
[[ "$PR" =~ ^[0-9]+$ ]] || usage

command -v gh >/dev/null 2>&1 || { echo "gh not found" >&2; exit 1; }
command -v jq >/dev/null 2>&1 || { echo "jq not found" >&2; exit 1; }

full="$(gh repo view --json nameWithOwner -q .nameWithOwner 2>/dev/null)" || {
  echo "cannot determine the repository (gh repo view failed) — is this inside a clone with auth?" >&2
  exit 1
}
OWNER="${full%%/*}"
NAME="${full#*/}"

# reviewThreads is the only API that exposes the thread id that resolveReviewThread
# needs; the REST comments endpoint does not carry it, so there is no simpler call.
THREADS_QUERY='query($owner:String!,$name:String!,$number:Int!){
  repository(owner:$owner, name:$name){
    pullRequest(number:$number){
      reviewThreads(first:100){
        nodes{
          id
          isResolved
          comments(first:1){ nodes{ author{login} path } }
        }
      }
    }
  }
}'

RESPONSE="$(gh api graphql -f query="$THREADS_QUERY" \
  -F owner="$OWNER" -F name="$NAME" -F number="$PR" 2>&1)" || {
  echo "could not read review threads:" >&2
  echo "$RESPONSE" >&2
  exit 1
}

# An error can arrive as a 200 with an `errors` array. Treating that as "no threads"
# would report success while resolving nothing, which is the one lie this script must
# not tell.
if ! printf '%s' "$RESPONSE" | jq -e '.data.repository.pullRequest' >/dev/null 2>&1; then
  echo "unexpected response shape (no pullRequest):" >&2
  echo "$RESPONSE" >&2
  exit 1
fi

# Turn BOT_LOGINS into a JSON array without an eval, so a stray shell metacharacter
# in the environment cannot become code.
BOTS_JSON="$(printf '%s\n' "${BOT_LOGINS:-github-actions[bot]}" | tr ',' '\n' \
  | jq -R . | jq -sc 'map(select(length > 0))')"

# The jq failure has to abort the script, not truncate the list: a partial list that
# reports "resolved 1 of 5" is worse than an error, because it looks like it worked.
FILTERED="$(printf '%s' "$RESPONSE" | jq -r --argjson bots "$BOTS_JSON" '
  .data.repository.pullRequest.reviewThreads.nodes[]
  | select(.isResolved == false)
  | select((.comments.nodes[0].author.login // "") as $login
           | any($bots[]; ascii_downcase == ($login | ascii_downcase)))
  | "\(.id)\t\(.comments.nodes[0].path // "?")"
')" || {
  echo "could not parse the thread list — refusing to report \"nothing to do\"" >&2
  exit 1
}

IDS=()
while IFS= read -r entry; do
  [[ -n "$entry" ]] || continue
  IDS+=("$entry")
done <<< "$FILTERED"

if [[ "${#IDS[@]}" -eq 0 ]]; then
  echo "no unresolved threads authored by $BOTS_JSON — nothing to resolve"
  exit 0
fi

RESOLVE_MUTATION='mutation($id:ID!){
  resolveReviewThread(input:{threadId:$id}){ thread{ id isResolved } }
}'

FAILED=0
for entry in "${IDS[@]}"; do
  id="${entry%%$'\t'*}"
  path="${entry#*$'\t'}"
  if [[ "$DRY_RUN" -eq 1 ]]; then
    echo "would resolve $id  ($path)"
    continue
  fi
  if out="$(gh api graphql -f query="$RESOLVE_MUTATION" -F id="$id" 2>&1)"; then
    echo "resolved $id  ($path)"
  else
    # Usually a token without pull-requests: write. Nothing else changed.
    echo "FAILED to resolve $id  ($path): $out" >&2
    FAILED=1
  fi
done

if [[ "$DRY_RUN" -eq 1 ]]; then
  echo "dry run — ${#IDS[@]} thread(s) would be resolved, nothing was"
fi
exit "$FAILED"