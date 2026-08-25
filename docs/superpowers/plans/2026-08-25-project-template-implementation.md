# Project Template (Copier Scaffold) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the `project-template` Copier scaffold — the GitHub repo scaffolding, `.claude/` baseline, generalized orchestration docs (Issues-backed task backbone, context-budget decomposition, two-tier feedback loop) — as a self-contained, locally testable deliverable, without touching any other live repo or GitHub hosting.

**Architecture:** A [Copier](https://copier.readthedocs.io/) template repo. `template/` holds the files that get copied into a generated repo (some Jinja-rendered via a `.jinja` suffix, some copied verbatim); `copier.yml` defines the prompted variables; `tests/` holds bash scripts that exercise `copier copy`/`copier update` end to end plus unit tests for the two custom bash script sets (`improvements_*` and `sync_labels`).

**Tech Stack:** Copier (Python, installed via `pipx`), Bash tests (no test framework — plain `set -euo pipefail` scripts with `mktemp -d` scratch dirs), GitHub Actions YAML, GitHub CLI (`gh`).

**Spec:** `docs/superpowers/specs/2026-08-25-project-template-design.md`

## Global Constraints

- Default branch name in generated repos: `main` (spec: "Decisions locked for v1").
- Context-budget decomposition thresholds: >40 files or ~150k tokens per task triggers mandatory split/checkpoint (spec Component 3 / Decisions locked for v1).
- Feedback review runs automatically at the end of any tick that logged a new `IMPROVEMENTS.md` entry; skipped entirely otherwise (spec Component 5 / Decisions locked for v1).
- Never auto-merge, never force-push, never push directly to the default branch — in this repo, in the template's own docs, and in every doc the template generates (spec Guardrails section).
- No live MCP servers or credentials committed anywhere — `.mcp.json.example` only, env-var references (spec Component 6).
- Dev machine is macOS (Darwin) — all bash must be BSD-compatible (e.g. `sed -i.bak` with explicit suffix, not GNU-only `sed -i`).
- This plan builds and locally tests the template only. Pushing it to GitHub, marking it a template, and piloting it on `kapekost-web` is a separate follow-up plan (spec: "Rollout Plan" steps 2+), written after this one lands.

---

### Task 1: Copier scaffold + smoke test

**Files:**
- Create: `copier.yml`
- Create: `template/AGENTS.md.jinja`
- Create: `tests/test_copier_generate.sh`

**Interfaces:**
- Produces: copier variables `project_name`, `project_slug`, `description`, `github_owner`, `default_branch` — every later templated file consumes these exact names.
- Produces: `tests/test_copier_generate.sh` — every later task appends assertions to this same file rather than creating a new one, so there's one canonical "does `copier copy` produce a correct tree" test.

- [ ] **Step 1: Confirm Copier is installed**

Run: `copier --version`
Expected: prints a version (e.g. `9.x.x`). If missing: `pipx install copier`, then re-run.

- [ ] **Step 2: Write `copier.yml`**

```yaml
# Copier configuration for project-template.
# https://copier.readthedocs.io/en/stable/configuring/

_subdirectory: template
_envops:
  keep_trailing_newline: true

project_name:
  type: str
  help: "Human-readable project name (e.g. 'Photo Cull')"

project_slug:
  type: str
  help: "Repo/slug name, lowercase-with-dashes"
  default: "{{ project_name.lower().replace(' ', '-') }}"

description:
  type: str
  help: "One-sentence description of the project"
  default: ""

github_owner:
  type: str
  help: "GitHub username or org that owns this repo"
  default: "kapekost"

default_branch:
  type: str
  help: "Default branch name"
  default: "main"
```

- [ ] **Step 3: Write the first templated file, `template/AGENTS.md.jinja`**

```markdown
# {{ project_name }}

Orchestration state and rules live in `docs/orchestration/`:
- `STATE.md` — current cursor, what to do next.
- `PLAYBOOK.md` — how `/orchestrate` runs.
- `GUARDRAILS.md` — hard rules; wins on conflict with anything else.
- `DECISIONS.md` — owner decisions already made; don't relitigate.
- `IMPROVEMENTS.md` — friction log, reviewed automatically per tick.

Tasks live as GitHub Issues (`type`/`priority`/`effort` labels), ranked in
the repo's Project board. `/orchestrate` reads and writes them via `gh`.

MCP servers: copy `.mcp.json.example` to `.mcp.json` and fill in what this
repo actually needs. Start new servers at local scope, promote to project
scope only once reviewed — never commit a real credential; reference an
env var instead.
```

- [ ] **Step 4: Write the smoke test**

```bash
#!/usr/bin/env bash
set -euo pipefail

# Runs `copier copy` against this repo and asserts the rendered output is
# correct. Extended by later tasks — do not create a second test file.

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

if [[ "$fail" -eq 0 ]]; then
  echo "PASS: test_copier_generate.sh"
else
  exit 1
fi
```

- [ ] **Step 5: Run it and verify it passes**

Run: `chmod +x tests/test_copier_generate.sh && bash tests/test_copier_generate.sh`
Expected: `PASS: test_copier_generate.sh`

- [ ] **Step 6: Commit**

```bash
git add copier.yml template/AGENTS.md.jinja tests/test_copier_generate.sh
git commit -m "Add copier scaffold with AGENTS.md and generation smoke test"
```

---

### Task 2: GitHub scaffolding (`.github/`)

**Files:**
- Create: `template/.github/ISSUE_TEMPLATE/config.yml`
- Create: `template/.github/ISSUE_TEMPLATE/bug.yml`
- Create: `template/.github/ISSUE_TEMPLATE/feature.yml`
- Create: `template/.github/ISSUE_TEMPLATE/chore.yml`
- Create: `template/.github/PULL_REQUEST_TEMPLATE.md`
- Create: `template/.github/CODEOWNERS.jinja`
- Create: `template/.github/labels.yml`
- Create: `template/.github/dependabot.yml`
- Create: `template/.github/workflows/ci.yml.jinja`
- Modify: `tests/test_copier_generate.sh` (append assertions)

**Interfaces:**
- Consumes: copier variables from Task 1 (`github_owner`, `default_branch`).
- Produces: the `type:*`/`priority:*`/`effort:*`/`ready`/`approved`/`needs-clarification`/`blocked` label set that `docs/orchestration/PLAYBOOK.md` (Task 3) and `scripts/sync_labels.sh` (Task 5) both reference by exact name.

- [ ] **Step 1: Write the issue template config**

`template/.github/ISSUE_TEMPLATE/config.yml`:
```yaml
blank_issues_enabled: false
```

- [ ] **Step 2: Write the bug report form**

`template/.github/ISSUE_TEMPLATE/bug.yml`:
```yaml
name: Bug report
description: Something is broken.
title: "[bug]: "
labels: ["type:bug", "needs-clarification"]
body:
  - type: textarea
    id: what-happened
    attributes:
      label: What happened?
      description: What did you expect instead?
    validations:
      required: true
  - type: textarea
    id: repro
    attributes:
      label: Steps to reproduce
    validations:
      required: true
  - type: dropdown
    id: effort
    attributes:
      label: Estimated effort (owner fills in during triage)
      options: ["XS", "S", "M", "L", "XL"]
    validations:
      required: false
```

- [ ] **Step 3: Write the feature request form**

`template/.github/ISSUE_TEMPLATE/feature.yml`:
```yaml
name: Feature request
description: A new capability, sized per INVEST before it's marked ready.
title: "[feature]: "
labels: ["type:feature", "needs-clarification"]
body:
  - type: textarea
    id: problem
    attributes:
      label: What problem does this solve?
    validations:
      required: true
  - type: textarea
    id: proposal
    attributes:
      label: Proposed approach
    validations:
      required: false
  - type: dropdown
    id: priority
    attributes:
      label: Priority (owner fills in during triage)
      options: ["P0", "P1", "P2", "P3"]
    validations:
      required: false
  - type: dropdown
    id: effort
    attributes:
      label: Estimated effort (owner fills in during triage)
      options: ["XS", "S", "M", "L", "XL"]
    validations:
      required: false
```

- [ ] **Step 4: Write the chore form**

`template/.github/ISSUE_TEMPLATE/chore.yml`:
```yaml
name: Chore
description: Maintenance work with no behavior change.
title: "[chore]: "
labels: ["type:chore"]
body:
  - type: textarea
    id: what
    attributes:
      label: What needs doing, and why now?
    validations:
      required: true
```

- [ ] **Step 5: Write the PR template**

`template/.github/PULL_REQUEST_TEMPLATE.md`:
```markdown
## Summary

<!-- What changed and why. Link the Issue: Closes #N -->

## Test plan

- [ ] Verification commands from the task/plan were run and passed
- [ ] CI is green

## Guardrails checklist

- [ ] Not a direct push to the default branch
- [ ] No destructive operation without an `approved` label on its Issue
- [ ] No secret/credential added to a tracked file
```

- [ ] **Step 6: Write CODEOWNERS**

`template/.github/CODEOWNERS.jinja`:
```
# These paths always require review from the repo owner.
/.github/ @{{ github_owner }}
/.claude/ @{{ github_owner }}
/.mcp.json* @{{ github_owner }}

# Add project-specific paths below, e.g.:
# /src/auth/ @{{ github_owner }}
```

- [ ] **Step 7: Write labels.yml**

`template/.github/labels.yml`:
```yaml
# Label definitions applied via `scripts/sync_labels.sh`.
# Three independent axes: type, priority, effort — see docs/orchestration/PLAYBOOK.md.

- name: "type:feature"
  color: "1D76DB"
  description: "New capability"
- name: "type:bug"
  color: "D73A4A"
  description: "Something broken"
- name: "type:chore"
  color: "CFD3D7"
  description: "Maintenance, no behavior change"
- name: "priority:P0"
  color: "B60205"
  description: "Drop everything"
- name: "priority:P1"
  color: "D93F0B"
  description: "Next up"
- name: "priority:P2"
  color: "FBCA04"
  description: "Normal"
- name: "priority:P3"
  color: "0E8A16"
  description: "Someday"
- name: "effort:XS"
  color: "C2E0C6"
  description: "Trivial, single subagent tick"
- name: "effort:S"
  color: "C2E0C6"
  description: "Small, single subagent tick"
- name: "effort:M"
  color: "FEF2C0"
  description: "Standard task size"
- name: "effort:L"
  color: "F9D0C4"
  description: "Must be split before dispatch (GUARDRAILS)"
- name: "effort:XL"
  color: "F9D0C4"
  description: "Must be split before dispatch (GUARDRAILS)"
- name: "ready"
  color: "0E8A16"
  description: "Triaged and ready for /orchestrate to pick up"
- name: "approved"
  color: "5319E7"
  description: "Owner approved a destructive task"
- name: "needs-clarification"
  color: "E4E669"
  description: "Failed the INVEST gate, needs owner input"
- name: "blocked"
  color: "000000"
  description: "Waiting on a dependency"
```

- [ ] **Step 8: Write dependabot.yml**

`template/.github/dependabot.yml`:
```yaml
version: 2
updates:
  - package-ecosystem: "github-actions"
    directory: "/"
    schedule:
      interval: "weekly"
```

- [ ] **Step 9: Write the baseline CI workflow**

`template/.github/workflows/ci.yml.jinja`:
```yaml
name: CI

on:
  pull_request:
    branches: [{{ default_branch }}]
  workflow_dispatch:

permissions:
  contents: read

concurrency:
  # Copier renders this file as Jinja; {% raw %} stops it from parsing
  # GitHub Actions' own {{ }} syntax as a Jinja expression.
  group: ci-{% raw %}${{ github.ref }}{% endraw %}
  cancel-in-progress: true

jobs:
  sanity:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v5

      - name: Validate YAML config files
        run: |
          for f in .github/labels.yml .github/dependabot.yml; do
            python3 -c "import sys, yaml; yaml.safe_load(open(sys.argv[1]))" "$f"
          done

      - name: Check for committed secrets in .mcp.json
        run: |
          if [ -f .mcp.json ]; then
            if grep -EIq '(sk-[A-Za-z0-9]{20,}|ghp_[A-Za-z0-9]{30,}|AKIA[0-9A-Z]{16})' .mcp.json; then
              echo "::error::Possible secret committed in .mcp.json -- use env var references instead."
              exit 1
            fi
          fi
```

- [ ] **Step 10: Append assertions to the generation test**

Add before the final `if [[ "$fail" -eq 0 ]]` block in `tests/test_copier_generate.sh`:

```bash
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
```

- [ ] **Step 11: Run the test and verify it passes**

Run: `bash tests/test_copier_generate.sh`
Expected: `PASS: test_copier_generate.sh`

- [ ] **Step 12: Commit**

```bash
git add template/.github tests/test_copier_generate.sh
git commit -m "Add GitHub scaffolding: issue forms, PR template, CODEOWNERS, labels, CI"
```

---

### Task 3: Orchestration docs (`docs/orchestration/`)

**Files:**
- Create: `template/docs/orchestration/PLAYBOOK.md.jinja` (contains `{{ default_branch }}` — needs the `.jinja` suffix to render; Copier strips it on output, so the generated file is still `docs/orchestration/PLAYBOOK.md`)
- Create: `template/docs/orchestration/GUARDRAILS.md.jinja` (same reason — contains `{{ default_branch }}` twice)
- Create: `template/docs/orchestration/STATE.md.jinja`
- Create: `template/docs/orchestration/DECISIONS.md` (no Jinja variables — plain file, copied verbatim)
- Create: `template/docs/orchestration/IMPROVEMENTS.md` (no Jinja variables — plain file, copied verbatim)
- Modify: `tests/test_copier_generate.sh` (append assertions)

**Interfaces:**
- Consumes: copier variables from Task 1 (`project_name`, `default_branch`).
- Produces: `IMPROVEMENTS.md`'s `<!-- last-reviewed-count: N -->` cursor format and its `## Log` heading, which `scripts/improvements_since_cursor.sh` and `scripts/advance_improvements_cursor.sh` (Task 4) parse by exact string match — do not change the heading text or comment format without updating Task 4's scripts.
- Produces: `GUARDRAILS.md`'s "Task sizing" section (>40 files / ~150k tokens) and "Cross-repo writes" section, referenced by name from `PLAYBOOK.md` step 3 and step 8.

- [ ] **Step 1: Write GUARDRAILS.md.jinja**

`template/docs/orchestration/GUARDRAILS.md.jinja`:
```markdown
# Orchestration Guardrails

> The autonomous runner (`/orchestrate`, scheduled or manual) MUST obey this file. When GUARDRAILS and
> any other doc conflict, GUARDRAILS wins. Linked decisions live in `DECISIONS.md`.

## Merge & branch rules
- **Never auto-merge to `{{ default_branch }}`.** Open PRs only; a human (or an owner-approved green-CI gate) merges.
- **Never force-push.** Never push directly to `{{ default_branch }}`.
- Feature branch → PR. No direct commits to `{{ default_branch }}`.

## Destructive operations (require an in-doc APPROVE flag)
A task is **destructive** if it does any of:
- Drops/renames DB tables or columns, or runs a migration with data loss.
- Deletes more than 10 tracked files in one task.
- Changes auth, session, secret, or token handling.
- Any other irreversible action (history rewrite, remote branch deletion).

**Flow:** a destructive task stays blocked until its Issue has the `approved` label (or, for
orchestrator-level tasks, `STATE.md` has its `- [x] APPROVE <task-id>` box checked). Unattended: flag
present → execute; flag absent → queue + report; **never guess**.

## Task sizing & context-budget decomposition
- Before dispatch, any task labeled `effort:L` or `effort:XL` MUST be split into linked sub-Issues at
  planning time, each sized `effort:M` or smaller, before any code changes start.
- If a dispatched subagent's context grows past the per-task budget below mid-task anyway, it MUST
  checkpoint progress to the Issue and `STATE.md`, then hand the remainder to a **fresh subagent**
  rather than continuing. Never push through a bloated context to "just finish."
- Default thresholds (tune per repo in `DECISIONS.md` if needed): a single task touching **more than
  40 files**, or costing **more than ~150k tokens**, must checkpoint and split/hand off.

## Cross-repo writes (template feedback)
- A `[template]`-tagged `IMPROVEMENTS.md` entry may only become a PR against the template repo using a
  named, explicit credential set up for that purpose — never implied by this repo's own `gh` auth.
- Template PRs are never auto-merged, exactly like destructive operations above.

## Hard stops (always halt + notify — no flag overrides these)
- CI is red.
- A merge conflict needs human judgment.
- The per-tick token budget is exceeded.
- A single task would change more than 40 files.
- A force-push, or a direct push to `{{ default_branch }}`, is attempted (also forbidden by the branch rules above).
- Any secret/credential would be written to a tracked file.
- The requirement is ambiguous or contradicts an Issue's description / `DECISIONS.md`.
- A `copier update` produces a conflict — resolve manually, never auto-resolve.

On a hard stop: write the blocker under `STATE.md` → "Needs owner", notify, halt that thread cleanly.

## Budgets (lean contract)
- **Per-tick token budget:** ~150k tokens of work, then checkpoint cleanly even mid-task.
- Reload **docs, not the repo**. Fan execution to subagents; one task = one subagent with a scoped
  file list. `/orchestrate status` must do zero execution.
```

- [ ] **Step 2: Write PLAYBOOK.md.jinja**

`template/docs/orchestration/PLAYBOOK.md.jinja`:
```markdown
# Orchestration Playbook

> How `/orchestrate` runs. Obey `GUARDRAILS.md` (it wins on conflict). Source of truth for tasks is
> GitHub Issues + Projects (see below); this file is *how* to drive them. Reuse superpowers skills —
> do not reinvent.

## Command variants (dispatch on the argument)
- `/orchestrate` (no arg) — run the next tick.
- `/orchestrate status` — reconstruct + report only. **No execution, no writes.** Cheapest path.
- `/orchestrate approve <issue-number>` — add the `approved` label to the given Issue, comment why, stop.
- `/orchestrate plan <issue-number>` — write the detailed plan for an Issue lacking one, via
  `superpowers:writing-plans`, then stop.
- `/orchestrate review-feedback` — run only step 8 below (feedback review), then stop. Also runs
  automatically at the end of any tick that logged a new `IMPROVEMENTS.md` entry.
- `/orchestrate stop` — set `STATE.md` → Stop-condition to "owner stop", commit, stop.

## The tick (for `/orchestrate` with no arg)
1. **Read** `STATE.md`, `GUARDRAILS.md`, `DECISIONS.md`. Do not read source files yet.
2. **Reconcile reality:** `git status`, `gh pr list`, `gh issue list --label ready --state open`
   (sorted by the Project's manual rank). If reality diverged from `STATE.md`, correct `STATE.md` and
   continue.
3. **Pick the next action** = highest-ranked open Issue with the `ready` label and no unresolved
   `blocked-by` dependency. Then:
   - If it has no linked plan and is `effort:M` or larger → run the `/orchestrate plan` flow and stop.
   - If it is `effort:L`/`XL` and has no sub-Issues yet → split it per GUARDRAILS "Task sizing" and stop.
   - If it is **destructive** (per GUARDRAILS) and lacks the `approved` label → skip to the next ready
     Issue; if none, stop + notify.
   - Else → execute.
4. **Execute** via `superpowers:subagent-driven-development`. Lean: dispatch one subagent per task; it
   reads only the Issue + its plan doc + the named files, never the whole tree. If context bloats
   mid-task per GUARDRAILS, checkpoint and hand off to a fresh subagent rather than pushing through.
5. **Gate:** run the task's verification commands; then `superpowers:requesting-code-review` (spec +
   code quality). At a deploy/milestone checkpoint, also run `/security-review`.
6. **PR:** open a PR referencing the Issue (`Closes #N`), then wait for CI; treat a red CI as a hard
   stop (do not merge). Never auto-merge to `{{ default_branch }}`.
7. **Write state back:** comment progress on the Issue; update `STATE.md`'s cursor/next-action only
   when on the orchestration home branch, never on a feature branch; append to `DECISIONS.md` if a
   decision was made.
8. **Feedback review:** if this tick appended any `IMPROVEMENTS.md` entries, run
   `scripts/improvements_since_cursor.sh`, classify each (`[local]` → PR in this repo; `[template]` →
   PR against the template repo per GUARDRAILS "Cross-repo writes"; `[unsure]` → `STATE.md` → Needs
   owner), then run `scripts/advance_improvements_cursor.sh` with the new total entry count. Skip this
   step entirely if nothing new was logged this tick.
9. **Close the tick:** print a one-screen summary (position, what you did, next action, anything
   needing the owner).

## Budget & checkpointing
Track work against the GUARDRAILS per-tick token budget. When near the limit, finish the current
step, write `STATE.md`, and stop with a clean resume note rather than starting a new task.

## Lean rules (always)
- Prefer `git`/`gh`/grep over reading files. Read a file only when about to change it.
- One subagent per task with an explicit file list. Summarize subagent results into STATE; do not
  pull their full transcripts into the controller context.
```

- [ ] **Step 3: Write STATE.md.jinja**

`template/docs/orchestration/STATE.md.jinja`:
```markdown
# Orchestration State

> Single-owner cursor for `/orchestrate`. Only the orchestration home branch may edit the sections
> below; a feature branch must never touch this file.

## Cursor
- **Project:** {{ project_name }}
- **Current focus:** (none yet — run `/orchestrate` to pick the first ready Issue)
- **Next action:** Triage the backlog: label open Issues with `type`/`priority`/`effort`, mark ready
  ones with `ready`.

## Stop-condition
(none — runner proceeds normally)

## In-flight
(no branches in flight)

## Needs owner
(nothing pending)

## Tick log
(no ticks yet)
```

- [ ] **Step 4: Write DECISIONS.md**

`template/docs/orchestration/DECISIONS.md`:
```markdown
# Orchestration Decisions

> Append-only log of owner decisions made during `/orchestrate` runs, so the runner never relitigates
> them. Newest at the top. Format: `## <date> — <short title>` then 1-3 sentences of the decision + why.

(No decisions logged yet.)
```

- [ ] **Step 5: Write IMPROVEMENTS.md**

`template/docs/orchestration/IMPROVEMENTS.md`:
```markdown
# Improvements Log

<!-- last-reviewed-count: 0 -->

Append one line per entry via `scripts/append_improvement.sh <local|template|unsure> "<note>"` — do
not edit this file by hand except to resolve a conflict. Reviewed automatically at the end of any
`/orchestrate` tick that added a new entry (see `PLAYBOOK.md` step 8); entries before the
`last-reviewed-count` marker above are never re-scanned.

## Log
```

- [ ] **Step 6: Append assertions to the generation test**

Add before the final `if [[ "$fail" -eq 0 ]]` block in `tests/test_copier_generate.sh`:

```bash
assert_file "docs/orchestration/PLAYBOOK.md"
assert_file "docs/orchestration/GUARDRAILS.md"
assert_contains "docs/orchestration/GUARDRAILS.md" "more than 40 files"
assert_file "docs/orchestration/STATE.md"
assert_contains "docs/orchestration/STATE.md" "**Project:** Test Project"
assert_file "docs/orchestration/DECISIONS.md"
assert_file "docs/orchestration/IMPROVEMENTS.md"
assert_contains "docs/orchestration/IMPROVEMENTS.md" "last-reviewed-count: 0"
```

- [ ] **Step 7: Run the test and verify it passes**

Run: `bash tests/test_copier_generate.sh`
Expected: `PASS: test_copier_generate.sh`

- [ ] **Step 8: Commit**

```bash
git add template/docs tests/test_copier_generate.sh
git commit -m "Add generalized orchestration docs: PLAYBOOK, GUARDRAILS, STATE, DECISIONS, IMPROVEMENTS"
```

---

### Task 4: Improvements log scripts

**Files:**
- Create: `template/scripts/append_improvement.sh`
- Create: `template/scripts/improvements_since_cursor.sh`
- Create: `template/scripts/advance_improvements_cursor.sh`
- Create: `tests/test_improvements_scripts.sh`

**Interfaces:**
- Consumes: `docs/orchestration/IMPROVEMENTS.md`'s exact cursor comment format and `## Log` heading from Task 3, Step 5.
- Produces: `append_improvement.sh <local|template|unsure> "<note>"`, `improvements_since_cursor.sh` (prints unreviewed lines to stdout, one per line), `advance_improvements_cursor.sh <count>` — exact names `PLAYBOOK.md` step 8 (Task 3) already references.

- [ ] **Step 1: Write the failing test first**

`tests/test_improvements_scripts.sh`:
```bash
#!/usr/bin/env bash
set -euo pipefail

# Unit tests for the three improvements-log scripts. Runs them inside an
# isolated scratch git repo (the scripts resolve paths via `git rev-parse
# --show-toplevel`, so they must run inside *some* git repo, and a scratch
# one avoids mutating this repo's own IMPROVEMENTS.md).

root="$(git rev-parse --show-toplevel)"
tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT

git -C "$tmp" init -q
mkdir -p "$tmp/docs/orchestration" "$tmp/scripts"
cp "$root/template/scripts/append_improvement.sh" "$tmp/scripts/"
cp "$root/template/scripts/improvements_since_cursor.sh" "$tmp/scripts/"
cp "$root/template/scripts/advance_improvements_cursor.sh" "$tmp/scripts/"
cp "$root/template/docs/orchestration/IMPROVEMENTS.md" "$tmp/docs/orchestration/"

fail=0
assert_eq() {
  if [[ "$1" != "$2" ]]; then
    echo "FAIL: expected [$2], got [$1]" >&2
    fail=1
  fi
}

cd "$tmp"

# No entries yet: since_cursor prints nothing.
out="$(bash scripts/improvements_since_cursor.sh)"
assert_eq "$out" ""

# Append two entries; both should show up as unreviewed.
bash scripts/append_improvement.sh local "first note"
bash scripts/append_improvement.sh template "second note"
out="$(bash scripts/improvements_since_cursor.sh)"
count="$(printf '%s\n' "$out" | grep -c '^- \[' || true)"
assert_eq "$count" "2"

# Advance the cursor to 2; since_cursor now prints nothing new.
bash scripts/advance_improvements_cursor.sh 2
out="$(bash scripts/improvements_since_cursor.sh)"
assert_eq "$out" ""

# Append a third entry; only the new one should show up.
bash scripts/append_improvement.sh unsure "third note"
out="$(bash scripts/improvements_since_cursor.sh)"
assert_eq "$out" "- [unsure] $(date +%Y-%m-%d): third note"

# Reject an invalid tag.
if bash scripts/append_improvement.sh bogus "bad" 2>/dev/null; then
  echo "FAIL: expected append_improvement.sh to reject an invalid tag" >&2
  fail=1
fi

if [[ "$fail" -eq 0 ]]; then
  echo "PASS: test_improvements_scripts.sh"
else
  exit 1
fi
```

- [ ] **Step 2: Run it to verify it fails**

Run: `chmod +x tests/test_improvements_scripts.sh && bash tests/test_improvements_scripts.sh`
Expected: FAIL — `cp: .../template/scripts/append_improvement.sh: No such file or directory` (scripts don't exist yet).

- [ ] **Step 3: Write append_improvement.sh**

`template/scripts/append_improvement.sh`:
```bash
#!/usr/bin/env bash
set -euo pipefail

# Appends one line to docs/orchestration/IMPROVEMENTS.md's Log section.
# Usage: append_improvement.sh <local|template|unsure> "<note>"

tag="${1:?Usage: append_improvement.sh <local|template|unsure> \"<note>\"}"
note="${2:?Usage: append_improvement.sh <local|template|unsure> \"<note>\"}"

case "$tag" in
  local|template|unsure) ;;
  *) echo "error: tag must be one of local, template, unsure" >&2; exit 1 ;;
esac

file="$(git rev-parse --show-toplevel)/docs/orchestration/IMPROVEMENTS.md"
date_str="$(date +%Y-%m-%d)"

printf -- '- [%s] %s: %s\n' "$tag" "$date_str" "$note" >> "$file"
```

- [ ] **Step 4: Write improvements_since_cursor.sh**

`template/scripts/improvements_since_cursor.sh`:
```bash
#!/usr/bin/env bash
set -euo pipefail

# Prints IMPROVEMENTS.md log entries appended since the last-reviewed cursor.

file="$(git rev-parse --show-toplevel)/docs/orchestration/IMPROVEMENTS.md"

cursor="$(grep -o 'last-reviewed-count: [0-9]*' "$file" | grep -o '[0-9]*')"

mapfile -t log_lines < <(awk '/^## Log$/{found=1; next} found && /^- \[/{print}' "$file")

total="${#log_lines[@]}"

if (( cursor >= total )); then
  exit 0
fi

for ((i=cursor; i<total; i++)); do
  printf '%s\n' "${log_lines[$i]}"
done
```

- [ ] **Step 5: Write advance_improvements_cursor.sh**

`template/scripts/advance_improvements_cursor.sh`:
```bash
#!/usr/bin/env bash
set -euo pipefail

# Moves the last-reviewed cursor forward. Usage: advance_improvements_cursor.sh <new-count>

new_count="${1:?Usage: advance_improvements_cursor.sh <new-count>}"

if ! [[ "$new_count" =~ ^[0-9]+$ ]]; then
  echo "error: <new-count> must be a non-negative integer" >&2
  exit 1
fi

file="$(git rev-parse --show-toplevel)/docs/orchestration/IMPROVEMENTS.md"

sed -i.bak -E "s/last-reviewed-count: [0-9]+/last-reviewed-count: ${new_count}/" "$file"
rm -f "${file}.bak"
```

- [ ] **Step 6: Make all three executable and run the test**

Run: `chmod +x template/scripts/*.sh && bash tests/test_improvements_scripts.sh`
Expected: `PASS: test_improvements_scripts.sh`

- [ ] **Step 7: Append a generation-test assertion for the scripts' presence**

Add to `tests/test_copier_generate.sh` before the final `if` block:

```bash
assert_file "scripts/append_improvement.sh"
assert_file "scripts/improvements_since_cursor.sh"
assert_file "scripts/advance_improvements_cursor.sh"
```

Run: `bash tests/test_copier_generate.sh`
Expected: `PASS: test_copier_generate.sh`

- [ ] **Step 8: Commit**

```bash
git add template/scripts tests/test_improvements_scripts.sh tests/test_copier_generate.sh
git commit -m "Add improvements-log scripts (append/since-cursor/advance) with unit tests"
```

---

### Task 5: Label sync script

**Files:**
- Create: `template/scripts/sync_labels.sh`
- Create: `tests/test_sync_labels.sh`

**Interfaces:**
- Consumes: `.github/labels.yml`'s exact `- name: / color: / description:` format from Task 2, Step 7.
- Produces: `sync_labels.sh [--dry-run]`, invoked manually by the owner (not from `orchestrate.md` — labels are a one-time-per-repo setup step, not a per-tick action).

- [ ] **Step 1: Write the failing test first**

`tests/test_sync_labels.sh`:
```bash
#!/usr/bin/env bash
set -euo pipefail

root="$(git rev-parse --show-toplevel)"
tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT

git -C "$tmp" init -q
mkdir -p "$tmp/.github" "$tmp/scripts"
cp "$root/template/scripts/sync_labels.sh" "$tmp/scripts/"
cp "$root/template/.github/labels.yml" "$tmp/.github/"

cd "$tmp"
out="$(bash scripts/sync_labels.sh --dry-run)"

fail=0
assert_contains() {
  if ! grep -qF -- "$1" <<<"$out"; then
    echo "FAIL: dry-run output missing: $1" >&2
    fail=1
  fi
}

assert_contains 'gh label create "type:bug" --color "D73A4A" --description "Something broken" --force'
assert_contains 'gh label create "ready" --color "0E8A16" --description "Triaged and ready for /orchestrate to pick up" --force'

line_count="$(printf '%s\n' "$out" | wc -l | tr -d ' ')"
if [[ "$line_count" -ne 16 ]]; then
  echo "FAIL: expected 16 label commands, got $line_count" >&2
  fail=1
fi

if [[ "$fail" -eq 0 ]]; then
  echo "PASS: test_sync_labels.sh"
else
  exit 1
fi
```

- [ ] **Step 2: Run it to verify it fails**

Run: `chmod +x tests/test_sync_labels.sh && bash tests/test_sync_labels.sh`
Expected: FAIL — `cp: .../template/scripts/sync_labels.sh: No such file or directory`.

- [ ] **Step 3: Write sync_labels.sh**

`template/scripts/sync_labels.sh`:
```bash
#!/usr/bin/env bash
set -euo pipefail

# Applies .github/labels.yml to the current repo via `gh label create`.
# Usage: sync_labels.sh [--dry-run]

dry_run=false
if [[ "${1:-}" == "--dry-run" ]]; then
  dry_run=true
fi

root="$(git rev-parse --show-toplevel)"
labels_file="$root/.github/labels.yml"

# Minimal parser for this repo's own labels.yml format (avoids a yq
# dependency): each entry is "- name: X" then "  color: Y" then
# "  description: Z", in that order.
name=""
color=""
description=""

apply_label() {
  local n="$1" c="$2" d="$3"
  if $dry_run; then
    echo "gh label create \"$n\" --color \"$c\" --description \"$d\" --force"
    return
  fi
  gh label create "$n" --color "$c" --description "$d" --force
}

while IFS= read -r line; do
  if [[ "$line" =~ ^-\ name:\ \"?([^\"]*)\"?$ ]]; then
    if [[ -n "$name" ]]; then
      apply_label "$name" "$color" "$description"
    fi
    name="${BASH_REMATCH[1]}"
    color=""
    description=""
  elif [[ "$line" =~ ^\ \ color:\ \"?([^\"]*)\"?$ ]]; then
    color="${BASH_REMATCH[1]}"
  elif [[ "$line" =~ ^\ \ description:\ \"?([^\"]*)\"?$ ]]; then
    description="${BASH_REMATCH[1]}"
  fi
done < "$labels_file"

if [[ -n "$name" ]]; then
  apply_label "$name" "$color" "$description"
fi
```

- [ ] **Step 4: Run the test and verify it passes**

Run: `chmod +x template/scripts/sync_labels.sh && bash tests/test_sync_labels.sh`
Expected: `PASS: test_sync_labels.sh`

- [ ] **Step 5: Append a generation-test assertion**

Add to `tests/test_copier_generate.sh` before the final `if` block:

```bash
assert_file "scripts/sync_labels.sh"
```

Run: `bash tests/test_copier_generate.sh`
Expected: `PASS: test_copier_generate.sh`

- [ ] **Step 6: Commit**

```bash
git add template/scripts/sync_labels.sh tests/test_sync_labels.sh tests/test_copier_generate.sh
git commit -m "Add label sync script with dry-run unit test"
```

---

### Task 6: `.claude/` baseline

**Files:**
- Create: `template/.claude/settings.json`
- Create: `template/.mcp.json.example`
- Modify: `tests/test_copier_generate.sh` (append assertions)

**Interfaces:**
- Produces: `.claude/settings.json` permission baseline and `.mcp.json.example` — both standalone, consumed by nothing else in this plan (a human copies `.mcp.json.example` to `.mcp.json` manually per repo, per `AGENTS.md`, Task 1).

- [ ] **Step 1: Write .claude/settings.json**

`template/.claude/settings.json`:
```json
{
  "permissions": {
    "allow": [
      "Bash(git status)",
      "Bash(git diff:*)",
      "Bash(git log:*)",
      "Bash(gh issue list:*)",
      "Bash(gh issue view:*)",
      "Bash(gh pr list:*)",
      "Bash(gh pr view:*)",
      "Bash(gh label list:*)"
    ]
  }
}
```

- [ ] **Step 2: Write .mcp.json.example**

`template/.mcp.json.example`:
```json
{
  "mcpServers": {
    "github": {
      "command": "docker",
      "args": ["run", "-i", "--rm", "-e", "GITHUB_PERSONAL_ACCESS_TOKEN", "ghcr.io/github/github-mcp-server"],
      "env": {
        "GITHUB_PERSONAL_ACCESS_TOKEN": "${GITHUB_PERSONAL_ACCESS_TOKEN}"
      }
    }
  }
}
```

- [ ] **Step 3: Append assertions to the generation test**

Add before the final `if` block in `tests/test_copier_generate.sh`:

```bash
assert_file ".claude/settings.json"
assert_file ".mcp.json.example"
assert_contains ".mcp.json.example" "GITHUB_PERSONAL_ACCESS_TOKEN"

# .mcp.json.example must never contain a real-looking credential.
if grep -Eq '(sk-[A-Za-z0-9]{20,}|ghp_[A-Za-z0-9]{30,})' "$tmp/.mcp.json.example"; then
  echo "FAIL: .mcp.json.example appears to contain a real credential" >&2
  fail=1
fi
```

- [ ] **Step 4: Run the test and verify it passes**

Run: `bash tests/test_copier_generate.sh`
Expected: `PASS: test_copier_generate.sh`

- [ ] **Step 5: Commit**

```bash
git add template/.claude template/.mcp.json.example tests/test_copier_generate.sh
git commit -m "Add .claude/settings.json baseline and .mcp.json.example"
```

---

### Task 7: `/orchestrate` command

**Files:**
- Create: `template/.claude/commands/orchestrate.md.jinja` (contains `{{ project_name }}` and `{{ default_branch }}` — needs the `.jinja` suffix to render; Copier strips it on output, so the generated file is `.claude/commands/orchestrate.md`)
- Modify: `tests/test_copier_generate.sh` (append assertions)

**Interfaces:**
- Consumes: `PLAYBOOK.md`/`GUARDRAILS.md`/`STATE.md`/`DECISIONS.md` (Task 3) by exact filename reference; `default_branch`/`project_name` copier variables (Task 1).

- [ ] **Step 1: Write orchestrate.md.jinja**

`template/.claude/commands/orchestrate.md.jinja`:
```markdown
---
description: Run one tick of the project orchestrator (or status/approve/plan/stop/review-feedback).
argument-hint: "[status | approve <issue> | plan <issue> | review-feedback | stop]"
allowed-tools: Bash, Read, Edit, Write, Grep, Glob, Agent, Skill
---

You are the {{ project_name }} orchestration controller. Drive work per the playbook.

**Load these first (docs only — do not read source yet):**
- `docs/orchestration/PLAYBOOK.md` — the tick algorithm and command variants.
- `docs/orchestration/GUARDRAILS.md` — the policy you MUST obey (it wins on conflict).
- `docs/orchestration/STATE.md` — the live cursor; resume from here.
- `docs/orchestration/DECISIONS.md` — owner decisions; do not relitigate.

**Argument:** $ARGUMENTS

Dispatch per PLAYBOOK "Command variants":
- empty → run one full tick.
- `status` → reconstruct + report only; make NO writes and NO code changes.
- `approve <issue-number>` → add the `approved` label via
  `gh issue edit <issue-number> --add-label approved`, comment why, stop.
- `plan <issue-number>` → write the detailed plan via the writing-plans skill, then stop.
- `review-feedback` → run only PLAYBOOK step 8 (feedback review), then stop.
- `stop` → set STATE.md Stop-condition to "owner stop", commit, stop.

Honor the lean contract: reload docs not the repo, dispatch one subagent per task with a scoped file
list, checkpoint at task/context-budget boundaries per GUARDRAILS "Task sizing", and never auto-merge
to `{{ default_branch }}`. Finish by writing STATE.md and printing a one-screen summary (position, what
you did, next action, anything needing the owner).
```

- [ ] **Step 2: Append assertions to the generation test**

Add before the final `if` block in `tests/test_copier_generate.sh`:

```bash
assert_file ".claude/commands/orchestrate.md"
assert_contains ".claude/commands/orchestrate.md" "You are the Test Project orchestration controller."
assert_contains ".claude/commands/orchestrate.md" "review-feedback"
assert_contains ".claude/commands/orchestrate.md" "never auto-merge"
```

- [ ] **Step 3: Run the test and verify it passes**

Run: `bash tests/test_copier_generate.sh`
Expected: `PASS: test_copier_generate.sh`

- [ ] **Step 4: Commit**

```bash
git add template/.claude/commands tests/test_copier_generate.sh
git commit -m "Add generalized /orchestrate command"
```

---

### Task 8: Template repo README

**Files:**
- Create: `README.md` (repo root — for people using this template, not a generated file)

**Interfaces:** none — standalone documentation.

- [ ] **Step 1: Write README.md**

`README.md`:
```markdown
# project-template

A [Copier](https://copier.readthedocs.io/) template for new and existing
projects: GitHub scaffolding (issue forms, PR template, CODEOWNERS,
labels, baseline CI), a `.claude/` baseline, and a generalized
orchestration pattern (`/orchestrate` + `docs/orchestration/`) with a
GitHub Issues-backed task backbone, context-budget task decomposition,
and a two-tier improvement feedback loop.

Design rationale: `docs/superpowers/specs/2026-08-25-project-template-design.md`.

## Create a new project

```bash
pipx install copier   # once per machine
copier copy gh:kapekost/project-template <destination-dir>
```

## Pull template updates into an existing project

```bash
cd <existing-project>
copier update
```

This diffs your repo's `.copier-answers.yml` (written the first time you
ran `copier copy`) against the template's current state and applies
changes as a local, reviewable diff. Conflicts are never auto-resolved —
resolve them by hand, same as any merge conflict.

## Applying labels

After creating or updating a project, sync its GitHub labels once:

```bash
scripts/sync_labels.sh          # applies .github/labels.yml via `gh`
scripts/sync_labels.sh --dry-run   # preview without touching GitHub
```

## Running the tests

```bash
bash tests/test_copier_generate.sh
bash tests/test_improvements_scripts.sh
bash tests/test_sync_labels.sh
bash tests/test_copier_update.sh
```
```

- [ ] **Step 2: Commit**

```bash
git add README.md
git commit -m "Add template repo README"
```

---

### Task 9: Full end-to-end generation test

**Files:**
- Modify: `tests/test_copier_generate.sh` (final consolidation pass — no new source files)

**Interfaces:** none — this task only strengthens the existing test's coverage.

- [ ] **Step 1: Add a full-tree assertion to catch anything not yet covered**

Add before the final `if` block in `tests/test_copier_generate.sh`:

```bash
# Full-tree sanity: every file under template/ must appear in the
# generated output with its .jinja suffix stripped, and nothing else
# but Copier's own .copier-answers.yml (which it writes automatically
# and is not part of template/).
expected_count="$(find "$root/template" -type f | wc -l | tr -d ' ')"
actual_count="$(find "$tmp" -type f -not -path '*/.git/*' -not -name '.copier-answers.yml' | wc -l | tr -d ' ')"
if [[ "$expected_count" != "$actual_count" ]]; then
  echo "FAIL: expected $expected_count generated files, got $actual_count" >&2
  fail=1
fi
```

- [ ] **Step 2: Run the full test suite**

Run:
```bash
bash tests/test_copier_generate.sh
bash tests/test_improvements_scripts.sh
bash tests/test_sync_labels.sh
```
Expected: all three print their `PASS:` line.

- [ ] **Step 3: Commit**

```bash
git add tests/test_copier_generate.sh
git commit -m "Add full-tree file-count assertion to generation test"
```

---

### Task 10: `copier update` propagation test

**Files:**
- Create: `tests/test_copier_update.sh`

**Interfaces:**
- Consumes: the full template tree built by Tasks 1-8.

- [ ] **Step 1: Write the failing test first**

`tests/test_copier_update.sh`:
```bash
#!/usr/bin/env bash
set -euo pipefail

# Proves the propagation story from the spec: a change made to the
# template after a project was generated can be pulled in later via
# `copier update`, and the update leaves a `.copier-answers.yml` pointer
# behind so future updates keep working.

root="$(git rev-parse --show-toplevel)"
work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT

# 1. Make an isolated, git-committed copy of the template to update against
#    (copier update needs the source to be a clean git repo with commits).
template_copy="$work/template-src"
cp -R "$root" "$template_copy"
rm -rf "$template_copy/.git"
git -C "$template_copy" init -q
git -C "$template_copy" add -A
git -C "$template_copy" commit -q -m "v1"

# 2. Generate a project from it.
dest="$work/generated"
copier copy --defaults --trust \
  --data project_name="Update Test" \
  --data project_slug="update-test" \
  --data description="" \
  --data github_owner="testowner" \
  --data default_branch="main" \
  "$template_copy" "$dest"

fail=0
if [[ ! -f "$dest/.copier-answers.yml" ]]; then
  echo "FAIL: .copier-answers.yml was not written" >&2
  fail=1
fi

# 3. Change the template (simulate a template-level improvement) and commit.
echo "- name: \"type:docs\"" >> "$template_copy/template/.github/labels.yml"
echo '  color: "0075CA"' >> "$template_copy/template/.github/labels.yml"
echo '  description: "Documentation only"' >> "$template_copy/template/.github/labels.yml"
git -C "$template_copy" add -A
git -C "$template_copy" commit -q -m "v2: add type:docs label"

# 4. Pull the update into the generated project.
git -C "$dest" init -q
git -C "$dest" add -A
git -C "$dest" commit -q -m "initial generation"
(cd "$dest" && copier update --defaults --trust)

if ! grep -qF 'type:docs' "$dest/.github/labels.yml"; then
  echo "FAIL: copier update did not propagate the new label" >&2
  fail=1
fi

if [[ "$fail" -eq 0 ]]; then
  echo "PASS: test_copier_update.sh"
else
  exit 1
fi
```

- [ ] **Step 2: Run it to verify it fails or passes for the right reason**

Run: `chmod +x tests/test_copier_update.sh && bash tests/test_copier_update.sh`
Expected: this test doesn't require new source files (Tasks 1-8 already provide everything), so it
should pass on first run. If it fails, the error will point at a real gap (e.g. `copier update` prompts
interactively without `--defaults --trust`, or the generated repo isn't a valid copier destination) —
fix the test invocation, not the template, unless the failure reveals a genuine template bug.

- [ ] **Step 3: Confirm it passes**

Run: `bash tests/test_copier_update.sh`
Expected: `PASS: test_copier_update.sh`

- [ ] **Step 4: Commit**

```bash
git add tests/test_copier_update.sh
git commit -m "Add copier update propagation test"
```

---

## After this plan

This plan stops at a fully-tested local template — nothing has been pushed to GitHub, and no other
repo has been touched. The follow-up plan (written after this one is reviewed and merged) covers spec
"Rollout Plan" steps 2+: pushing this repo to GitHub as a private template, and piloting it on
`kapekost-web` via `copier copy`/`copier link`, reconciling its existing `AGENTS.md`, and running one
real `/orchestrate` tick end to end.
