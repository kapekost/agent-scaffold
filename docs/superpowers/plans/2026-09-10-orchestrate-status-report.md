# `/orchestrate status` Report Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give `/orchestrate status` a fixed, computed-live report (READY / IN PROGRESS / BLOCKED
/ NEEDS OWNER / INTAKE / IMPROVEMENTS) that reads only from sources already kept accurate for
other reasons, so nothing new can go stale the way the Project board's `Status` field did.

**Architecture:** All computation lives in one new, dependency-free bash script,
`scripts/orchestrate_status.sh`, split into small functions: the ones that parse `STATE.md`/
`IMPROVEMENTS.md` text are pure (no `gh`, no network) and get real unit tests against fixture
files in an isolated scratch repo, matching this repo's own `tests/test_improvements_scripts.sh`
pattern. The `gh`-dependent functions (READY/BLOCKED/INTAKE, which need a live Issue list) are
not unit-tested — this repo has no existing precedent for faking `gh`, and the design's own
philosophy is "verify empirically against the real thing," so their correctness is confirmed in
Task 4 against a real repo (`workout-tracker`) instead. `PLAYBOOK.md.jinja` and
`orchestrate.md.jinja` are updated to document the format and point at the script; neither file
duplicates the script's logic in prose.

**Tech Stack:** bash (`set -euo pipefail`), `gh` CLI (`gh project item-list`, `gh issue list`),
`git show`, `awk`/`grep`/`date`. No new dependency — matches every other script in
`template/scripts/`.

**Spec:** `docs/superpowers/specs/2026-09-10-orchestrate-status-report-design.md`

## Global Constraints

- **No new dependency.** Pure POSIX-ish bash + `gh` + `git`, same as every existing script in
  `template/scripts/`.
- **Date arithmetic must work on both BSD date (macOS, the owner's actual machine) and GNU date**
  (Linux CI / cloud agents) — try GNU syntax first, fall back to BSD, per the portable pattern
  below. Do not assume one or the other.
- **Every `grep -c`/`grep -m1` call that might match zero lines must be guarded** (`|| true`,
  and default the captured variable with `${var:-0}`) — under `set -euo pipefail` an unmatched
  `grep -c` exits non-zero and would kill the whole script on the empty-state case, which is
  the *common* case for a fresh repo (see `STATE.md.jinja`'s own "(nothing pending)"/"(no
  branches in flight)" placeholders).
- **`scripts/orchestrate_status.sh` ships with no `.jinja` extension** — it takes `--owner` and
  `--project` as CLI flags rather than baking in template variables, matching
  `scripts/create_board_view.sh`'s already-established precedent (also flag-driven, also plain
  bash with no jinja substitution).
- **`STATE.md.jinja`'s ~250-line budget (see its own header) must not blow out** from the two new
  header fields added in Task 1 — they add 2 lines, not a new section, by design.
- **Every existing template test must still pass**: `bash tests/test_copier_generate.sh` (full
  file-tree + no-leftover-Jinja sanity) and `bash tests/test_improvements_scripts.sh` (unaffected,
  but a regression here would mean something else broke).
- **Non-Goals, from the spec — do not implement these:** no writing to the Project board's
  `Status` field, no rendered dashboard/Artifact, no new `/orchestrate triage-improvements`
  command. This plan is read-only reporting plus two doc fixes.

---

## File Structure

- **Create:** `template/scripts/orchestrate_status.sh` — the whole report: pure parsing functions
  (Task 1) + `gh`-dependent functions and `main()` (Task 2), one file, matching this template's
  existing one-script-per-concern layout (`append_improvement.sh`, `sync_labels.sh`, etc. are each
  a single file with a handful of functions or one linear script).
- **Create:** `tests/test_orchestrate_status.sh` — unit tests for the pure parsing functions,
  modeled directly on `tests/test_improvements_scripts.sh`'s scratch-repo pattern.
- **Modify:** `template/docs/orchestration/STATE.md.jinja` — two new header fields (Task 1).
- **Modify:** `template/docs/orchestration/PLAYBOOK.md.jinja` — expand the `status` command
  variant, add a "Status report" subsection documenting the format, add the bypass-closing
  sentence to step 7 (Task 3).
- **Modify:** `template/.claude/commands/orchestrate.md.jinja` — expand the `status` dispatch line
  (Task 3).

---

## Task 1: `STATE.md.jinja` header fields + pure parsing functions + unit tests

**Files:**
- Modify: `template/docs/orchestration/STATE.md.jinja`
- Create: `template/scripts/orchestrate_status.sh`
- Create: `tests/test_orchestrate_status.sh`

**Interfaces:**
- Produces (used by Task 2): `parse_home_branch <state_content>`, `parse_project_number
  <state_content>`, `extract_section <content> <heading>`, `count_top_bullets <section_text>`,
  `summarize_bullets <section_text>`, `parse_improvements <improvements_content>` (prints
  `<total>|<unsure_count>|<oldest_unsure_date_or_empty>`), `days_since <YYYY-MM-DD>`. All are pure
  bash functions taking file *content* as a string argument (not a path) — this is what makes them
  testable without `git show`/network, and what Task 2's `main()` will call after doing its own
  `git show`/`cat` to get that content.

- [ ] **Step 1: Add two header fields to `STATE.md.jinja`.** Insert them right after the existing
  blockquote's first paragraph, before the "This file keeps no Tick log" paragraph:

  ```markdown
  > **Home branch:** (none — this repo commits orchestration docs straight to `{{ default_branch }}`)
  > **Project number:** (none yet — create one with `gh project create`, then run
  > `scripts/create_board_view.sh <owner> <number>`)
  ```

  A repo that adopts a separate orchestration home branch (like `workout-tracker`'s
  `claude/workout-tracker-backlog-bu9qnw`) fills these in by hand once, e.g.:
  ```markdown
  > **Home branch:** `claude/workout-tracker-backlog-bu9qnw`
  > **Project number:** 3
  ```

- [ ] **Step 2: Write the failing tests** in `tests/test_orchestrate_status.sh`:

  ```bash
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
  ```

- [ ] **Step 3:** Run `bash tests/test_orchestrate_status.sh` — expect FAIL (`orchestrate_status.sh`
  doesn't exist yet, `source` fails).

- [ ] **Step 4: Implement the pure functions** in `template/scripts/orchestrate_status.sh`:

  ```bash
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
    grep -m1 -oE '\*\*Home branch:\*\* `[^`]+`' <<<"$1" | sed -E 's/.*`([^`]+)`.*/\1/'
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
  ```

- [ ] **Step 5:** Run `bash tests/test_orchestrate_status.sh` — expect PASS, all assertions.

- [ ] **Step 6:** Run `bash tests/test_copier_generate.sh` — expect PASS (the new `STATE.md.jinja`
  lines and the new `orchestrate_status.sh` file must render/copy cleanly with no leftover Jinja
  syntax and the file-count sanity check must still balance).

- [ ] **Step 7:** Commit:
  ```
  git add template/docs/orchestration/STATE.md.jinja template/scripts/orchestrate_status.sh tests/test_orchestrate_status.sh
  git commit -m "feat: home-branch/project header fields + pure status-report parsing functions"
  ```

## Task 2: `gh`-dependent report lines + `main()`

**Files:**
- Modify: `template/scripts/orchestrate_status.sh`

**Interfaces:**
- Consumes: every function from Task 1 (same file, already sourced/defined above `main`).
- Produces: `main "$@"` — the full report to stdout. Guarded so sourcing the file (as
  `tests/test_orchestrate_status.sh` already does) never executes it.

- [ ] **Step 1: Append the `gh`-dependent line-builders and `main()`** to the end of
  `template/scripts/orchestrate_status.sh` (after the Task 1 functions, same file):

  ```bash
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
  ```

- [ ] **Step 2:** Run `bash tests/test_orchestrate_status.sh` again — expect PASS still (the new
  code is guarded by the `BASH_SOURCE` check, so sourcing the file for tests still never calls
  `main` or touches `gh`).

- [ ] **Step 3: Manual smoke test against this repo itself** (agent-scaffold has no Project/Issues
  of its own set up the way workout-tracker does, so this only proves the script *runs* without
  crashing on a repo with no home branch and no project number set):
  ```bash
  bash template/scripts/orchestrate_status.sh
  ```
  Expected: prints six lines, `READY (unknown — no Project number set in STATE.md)` for the first
  since this repo's own `docs/orchestration/STATE.md` (not `.jinja`) has no such header field
  today, and `(0)` for the rest since there's no real Issue/label data here. This is expected and
  fine — the real verification is Task 4, against workout-tracker.

- [ ] **Step 4:** Commit:
  ```
  git add template/scripts/orchestrate_status.sh
  git commit -m "feat: gh-backed status-report lines and main() entry point"
  ```

## Task 3: Document the format in `PLAYBOOK.md.jinja` and `orchestrate.md.jinja`

**Files:**
- Modify: `template/docs/orchestration/PLAYBOOK.md.jinja`
- Modify: `template/.claude/commands/orchestrate.md.jinja`

**Interfaces:**
- Consumes: `scripts/orchestrate_status.sh` from Task 2 (referenced by path, not re-described).

- [ ] **Step 1: Replace the `status` line in `PLAYBOOK.md.jinja`'s "Command variants" section.**
  Find:
  ```
  - `/orchestrate status` — reconstruct + report only. **No execution, no writes.** Cheapest path.
  ```
  Replace with:
  ```
  - `/orchestrate status` — run `scripts/orchestrate_status.sh` and print its output verbatim.
    **No execution, no writes.** Cheapest path. See "Status report" below for the exact format.
  ```

- [ ] **Step 2: Add a new "Status report" subsection**, placed directly after "Command variants"
  and before "Triage / INVEST gate":
  ```markdown
  ## Status report

  `scripts/orchestrate_status.sh` prints exactly this shape:
  ```
  READY (3): #127, #138, #137
  IN PROGRESS (1): #125 — claimed 2026-09-10T03:54Z, paused (owner go-ahead pending)
  BLOCKED (0)
  NEEDS OWNER (2): #30/#32 spec skim; 2 [template] items open in agent-scaffold
  INTAKE (2): #152, #148
  IMPROVEMENTS: 25 logged, 5 [unsure] open (oldest: 11 days)
  ```
  Every line is empty-safe — `BLOCKED (0)` prints plainly, absence of blocked work is itself
  useful information, not an omitted line.

  Every number and list comes from a source already kept accurate for other reasons, never from
  new stored state:
  - **READY** — `gh project item-list`, ranked (the Project's manual drag order — the same source
    step 2/3 use to pick the next Issue; deliberately not `gh issue list`, which cannot sort by
    that rank at all).
  - **IN PROGRESS** / **NEEDS OWNER** — the orchestration home branch's own `STATE.md`
    `## In-flight` / `## Needs owner` sections, read via `git show origin/<home-branch>:...`, never
    the working tree's copy (which is deliberately not kept current — see that file's own header).
    A repo with no distinct home branch (`STATE.md`'s "Home branch" field left at its default)
    reads the working tree directly instead.
  - **BLOCKED** / **INTAKE** — `gh issue list --label blocked`/`--label intake`, open only.
  - **IMPROVEMENTS** — parsed from the home branch's `IMPROVEMENTS.md`: total entries, how many
    are `[unsure]`, and the oldest `[unsure]` entry's age in days.

  Requires `STATE.md`'s "Home branch"/"Project number" header fields to be filled in for the
  READY/IN PROGRESS/NEEDS OWNER lines to resolve — a fresh scaffold with neither set still runs,
  reporting `READY (unknown — no Project number set in STATE.md)` and reading the working tree for
  the rest.
  ```

- [ ] **Step 3: Add the bypass-closing sentence to step 7 ("Write state back")**, immediately after
  the existing `DECISIONS.md` sentence and before the "`STATE.md` keeps no Tick log" paragraph:
  ```markdown
  **Any direct edit to `PLAYBOOK.md` or `GUARDRAILS.md` made mid-tick to correct something
  wrong** — not a new feature, an actual fix to a wrong instruction — **also gets an
  `append_improvement.sh` entry in the same commit**, `[template]` if the template's own copy of
  this file carries the same bug, `[local]` if it's specific to this repo's rendering of it. This
  is the step that was skipped when `blocked-by` tracking was fixed locally in one repo and the
  fix never reached the template — see `IMPROVEMENTS.md`'s log for the entry this rule would have
  produced, had it existed then.
  ```

- [ ] **Step 4: Update `orchestrate.md.jinja`'s `status` dispatch line.** Find:
  ```
  - `status` → reconstruct + report only; make NO writes and NO code changes.
  ```
  Replace with:
  ```
  - `status` → run `scripts/orchestrate_status.sh` and print its output verbatim. No writes, no
    code changes. See `PLAYBOOK.md`'s "Status report" section for the exact format and sources.
  ```

- [ ] **Step 5:** Run `bash tests/test_copier_generate.sh` — expect PASS (new doc text renders with
  no leftover Jinja, file-tree count still balances since no files were added/removed here).

- [ ] **Step 6:** Commit:
  ```
  git add template/docs/orchestration/PLAYBOOK.md.jinja template/.claude/commands/orchestrate.md.jinja
  git commit -m "docs(playbook): document the status report format and close the fix-bypass gap"
  ```

## Task 4: Real-repo verification, review, PR

This is the manual-verification task per this project's own established convention (see
`workout-tracker`'s Task 4 pattern for #125: code review and green tests are not enough on their
own for something whose correctness depends on live external state).

- [ ] **Step 1: Copy the script into `workout-tracker` directly** (no `copier update` needed yet —
  that's the real rollout mechanism per the spec, but a direct copy is enough to verify the script
  itself before asking `copier update` to also merge every other template drift):
  ```bash
  cp /Users/kapekost/dev/agent-scaffold/template/scripts/orchestrate_status.sh \
     /Users/kapekost/dev/workout-tracker/scripts/orchestrate_status.sh
  chmod +x /Users/kapekost/dev/workout-tracker/scripts/orchestrate_status.sh
  ```

- [ ] **Step 2: Add the two header fields to workout-tracker's real `STATE.md`** on its
  orchestration home branch (`claude/workout-tracker-backlog-bu9qnw`), filled in with real values:
  ```markdown
  > **Home branch:** `claude/workout-tracker-backlog-bu9qnw`
  > **Project number:** 3
  ```
  Commit directly to that branch per this repo's own "push orchestration doc commits directly to
  the home branch" rule (`PLAYBOOK.md` step 7) — do not open a PR for this.

- [ ] **Step 3: Run it for real** from a workout-tracker checkout on the home branch (or a worktree
  of it):
  ```bash
  cd /Users/kapekost/dev/workout-tracker
  git checkout claude/workout-tracker-backlog-bu9qnw
  bash scripts/orchestrate_status.sh --owner kapekost
  ```
  Expected: six real lines. Compare the READY line's Issue numbers and order against
  `gh project item-list 3 --owner kapekost --query "status:Todo label:ready"` run directly — they
  must match exactly. Compare the IN PROGRESS line against `STATE.md`'s actual `## In-flight`
  section by eye — the summarized text should recognizably match what's there (truncation/joining
  is expected and fine; dropped or wrong Issue numbers are not).

- [ ] **Step 4: Fix anything real found during Step 3** directly in
  `agent-scaffold/template/scripts/orchestrate_status.sh` (not in the copied-out workout-tracker
  file — that copy was only for this verification step and does not get committed there), per this
  project's own "fix anything real before requesting review" convention. Re-run Step 3 after any
  fix until it's clean. Delete the temporary copy from workout-tracker afterward:
  ```bash
  rm /Users/kapekost/dev/workout-tracker/scripts/orchestrate_status.sh
  ```
  (workout-tracker picks up the real script later via its own `copier update`, per the spec's
  Rollout section — this task only verifies the template's copy is correct.)

- [ ] **Step 5:** `superpowers:requesting-code-review` against the full branch diff (spec + code
  quality). No `/security-review` — this touches no auth/session/secret/token/migration path, and
  the script only reads public-to-the-owner GitHub data.

- [ ] **Step 6: PR** against `agent-scaffold`'s `main`, referencing the design spec. `gh pr checks
  <PR> --watch --fail-fast` (this repo has no CI workflow of its own today — confirm that's still
  true, `ls .github/workflows/`, before assuming this step is a no-op), then confirm `gh pr view
  <PR> --json headRefOid,statusCheckRollup` shows the commit just pushed before merging. Merge
  (`gh pr merge <PR> --squash --delete-branch`) once green or once confirmed there is genuinely no
  CI to wait on.

## Issue coverage

Spec Goal 1 (fixed, live-computed table) → Tasks 1-2. Goal 2 (`IMPROVEMENTS.md` visibility) →
Task 1's `parse_improvements`/`days_since`, wired into the report in Task 2. Goal 3 (`blocked-by`
fix) → already shipped in PR #3, not part of this plan. Goal 4 (close the `append_improvement.sh`
bypass) → Task 3 Step 3. Design Section 6 (command-file changes) → Task 3 Step 4.
