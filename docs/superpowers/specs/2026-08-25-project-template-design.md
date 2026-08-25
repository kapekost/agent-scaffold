# Project Template & Multi-Agent Workflow System — Design Spec

Date: 2026-08-25
Status: Draft, pending owner review

## Problem

Work is spread across ~10 repos on multiple machines (dimkos, kapekost-web,
workout-tracker, photo-cull, claude/home-assistant, and others). Each has
independently reinvented a slice of the same problem — task tracking,
Claude Code config, an orchestration loop — with no shared baseline and no
way to carry an improvement from one repo into another. `dimkos` has the
most mature pattern (`/orchestrate` + `docs/orchestration/{PLAYBOOK,
GUARDRAILS,STATE,DECISIONS,IMPROVEMENTS}.md`), explicitly flagged as
"not yet proven" and currently being validated via `photo-cull`.

## Goals

- One template repo that every new project starts from, giving it
  consistent GitHub scaffolding, a proven orchestration pattern, and
  local per-repo MCP/rules config out of the box.
- A real **update path**: improvements made after a repo was created can
  be pulled in later, from any laptop, without hand-copying files.
- A **feedback path** in the other direction: learnings surfaced by
  agents doing real project work can flow back into the template, so the
  system gets better from use, not just from deliberate template edits.
- Stay cheap: nothing in the design should require agents to scan
  history or re-derive context they already have mid-task.

## Non-Goals

- **No persistent named role agents** (PM/Architect/Dev/Reviewer/QA) by
  default. Superseded by context-budget task decomposition (Component
  3). Anthropic's own guidance: multi-agent dispatch costs 3–10x the
  tokens of single-agent work and is justified only for genuine context
  isolation or parallelization — not standing personas. BMAD-METHOD
  proves named roles are a legitimate pattern elsewhere, just not the
  default here.
- **No Projen-style generated/owned config.** Too heavy and
  AWS/CDK-flavored for ~10 small solo repos.
- **No auto-merge**, anywhere, for anything. Every existing GUARDRAILS
  approval gate stays intact; template-level PRs get the same treatment.
- **Not migrating `dimkos` in this pass.** The template is proven on a
  pilot repo first (see Rollout); `dimkos` keeps its current markdown-only
  setup until the pattern is validated elsewhere.

## Architecture Overview

Two kinds of repo exist:

1. **Template repo** (this repo, `project-template`) — source of truth
   for scaffolding, parameterized via [Copier](https://copier.readthedocs.io/).
2. **Generated repos** — every project, existing or new, each carrying a
   `.copier-answers.yml` that points back to the template repo + the git
   ref it was last synced to.

Two flows connect them:

- **Forward** (creation/update) — `copier copy` scaffolds a new repo;
  `copier update` pulls later template changes into an existing one as a
  reviewable diff. Both run locally; no server, works identically from
  any laptop.
- **Reverse** (feedback) — generalizable learnings captured during real
  project work in a generated repo become PRs against the template repo.
  Human-reviewed, never auto-merged. Once merged, every other repo picks
  the change up on its own next `copier update` (pull-based — nothing
  changes on another machine without that machine asking).

```
        copier copy / copier update
   ┌───────────────────────────────────┐
   │                                     ▼
project-template (this repo)      generated repo (e.g. photo-cull)
   ▲                                     │
   └───────────────────────────────────┘
        PR from review subagent,
        human-merged, [template]-tagged
        IMPROVEMENTS.md entries only
```

## Components

### 1. Template contents

- **`.github/`** — issue forms (`ISSUE_TEMPLATE/*.yml`, one per
  `type:*`), `config.yml` with `blank_issues_enabled: false`, a PR
  template, `CODEOWNERS` gating `.claude/`, `.mcp.json`, CI config, and
  auth/secret-handling code, labels defined as config
  (`type:*`/`priority:P0-P3`/`effort:XS-XL`), a baseline CI workflow
  (path-filtered, matching dimkos's `ci.yml`), Dependabot config.
- **`.claude/`** — `settings.json` baseline (tool allowlist, hooks),
  `commands/orchestrate.md` (generalized from dimkos's version),
  `.mcp.json.example` with env-var placeholders and a scope-discipline
  comment — no live servers pre-wired; each repo opts in to what it
  needs.
- **`docs/orchestration/`** — `PLAYBOOK.md`, `GUARDRAILS.md` (existing
  dimkos hard-stops plus the sizing/decomposition rule from Component
  3), `STATE.md`, `DECISIONS.md`, `IMPROVEMENTS.md` (now with a
  `last-reviewed` cursor, Component 5).
- **Root `AGENTS.md`** — a thin pointer into `docs/orchestration/`,
  following kapekost-web's pattern rather than workout-tracker's dense
  single-file style, so the source of truth stays in one place.

### 2. Task backbone — GitHub Issues + Projects (hybrid)

- **Issues + Projects v2 are the task list.** `type`/`priority`/`effort`
  labels; a Project view holds manual execution rank, kept explicitly
  separate from priority; blockers use GitHub's native issue-dependency
  API, not comments; an INVEST gate runs before anything enters the
  queue (fails → `needs-clarification` label).
- **`STATE.md`/`GUARDRAILS.md` stay orchestrator-only** — cursor
  position, token/context budgets, hard-stop conditions, APPROVE flags
  for destructive ops. Nothing that belongs on an Issue lives here.
- `/orchestrate` reads/writes tasks via `gh`, not a markdown plan file —
  the `FABLE_PLAN.md`-style checkbox list is template-deprecated (dimkos
  keeps its own for now, per Non-Goals).

### 3. Context-budget task decomposition

Replaces named roles as the mechanism for keeping individual agent runs
small and coherent:

- Before dispatch, a task above an effort threshold (`effort:L`/`XL`
  label, or an estimated file/token count) must be split into subtasks
  at planning time, each becoming its own Issue linked via the
  dependency API.
- If a dispatched subagent's context grows past a budget mid-task
  anyway, it checkpoints progress to the Issue and `STATE.md`, then
  hands the remainder to a **fresh subagent** rather than continuing —
  the same mechanics as the existing `delegating-to-new-session` skill,
  now a standing `GUARDRAILS.md` rule instead of an ad hoc judgment
  call.
- Carries forward dimkos's existing hard stops (>40 files in one task,
  per-tick ~150k token budget) as the concrete default thresholds,
  tunable per repo.

### 4. Propagation — Copier

- `copier.yml` at the template root defines the prompted variables
  (project name, stack, which optional `.mcp.json` servers to seed,
  etc.) and Jinja-templated files under a `template/` subdirectory.
- New project: `copier copy gh:kapekost/project-template <dest>`.
- Existing project: `copier update` inside the repo — diffs the
  repo's `.copier-answers.yml` ref against the template's current
  state, applies changes as a normal reviewable local diff (conflicts
  surface for manual resolution — never auto-resolved).
- Works identically from any laptop: it's git + a local Python tool, no
  shared server or account state.

### 5. Two-tier feedback loop

- **Capture** — any subagent doing real project work that hits friction
  (a wrong guardrail, a missing MCP server, a flaky CI step, an outdated
  template file) appends one line to that repo's `IMPROVEMENTS.md`,
  tagged `[local]`, `[template]`, or `[unsure]`. This happens inline,
  using context the subagent already has loaded — no extra scan.
- **Review** — at each `/orchestrate` tick close (or a dedicated
  `/orchestrate review-feedback` variant), the orchestrator dispatches a
  scoped, one-shot review subagent that reads only entries appended
  since `IMPROVEMENTS.md`'s `last-reviewed` cursor, classifies each, and
  moves the cursor forward. It never re-scans older entries or project
  history.
- **Local application** — `[local]` entries get applied directly to that
  repo's own docs/config via a normal PR in that repo.
- **Template PRs** — `[template]` entries get a PR opened against the
  central template repo, with the concrete diff translated back into
  the template's Jinja-parameterized form. This is a cross-repo write:
  the review subagent needs `gh` access scoped to the template repo,
  which is a deliberate, named credential/permission — not implied by
  the repo's own scope.
- **Unsure** — `[unsure]` entries land under `STATE.md → Needs owner`,
  same escalation path as today's destructive-op flagging.
- **Human gate** — template PRs are never auto-merged. Same
  APPROVE-flag philosophy `GUARDRAILS.md` already applies to
  destructive project ops.
- **Fan-out** — once merged, other repos pick the change up on their own
  next `copier update`. Pull-based: nothing changes on another machine
  unless that machine's owner (or its `/orchestrate` tick) asks.

### 6. MCP conventions

- `.mcp.json.example` ships in the template with placeholder env-var
  references and a comment on scope discipline (start servers at
  *local* scope, promote to *project* scope only once reviewed).
  `CODEOWNERS` gates real `.mcp.json` changes given the tool-execution
  blast radius. No live servers are pre-wired — each repo copies the
  example and fills in what it actually needs.

## Data Flow — worked example

1. Owner runs `/orchestrate` in `photo-cull`. It reads `STATE.md`,
   `GUARDRAILS.md`, and open Issues via `gh`.
2. Next Issue is `effort:L` → decomposition rule fires; it's split into
   three linked sub-Issues before any code changes.
3. Orchestrator dispatches one scoped subagent per sub-Issue. One hits a
   missing MCP server partway through, notes it in `IMPROVEMENTS.md` as
   `[template]`, keeps working (checkpointing context if it grows past
   budget), opens its PR against `photo-cull`.
4. CI runs; a red result is a hard stop, no merge. Green → owner merges
   normally.
5. Tick closes. Review subagent reads the one new `IMPROVEMENTS.md`
   entry since the cursor, confirms it's genuinely generalizable, opens
   a PR against `project-template` adding the server to
   `.mcp.json.example`, advances the cursor.
6. Owner reviews and merges the template PR later, at their convenience.
7. Weeks later, working in `workout-tracker`, the owner runs `copier
   update`; the new example server shows up as part of that diff.

## Guardrails carried over / added

- Never auto-merge to `main`, in any repo, for any reason (project code
  or template).
- Never force-push; never push directly to `main`.
- Destructive project ops still require an in-doc APPROVE flag
  (unchanged from dimkos).
- `copier update` conflicts always surface for manual resolution.
- Context-budget breach → checkpoint + fresh subagent, never silent
  continuation past the threshold.
- Cross-repo write access (review subagent → template repo PRs) is a
  named, explicit grant, not inherited implicitly from a project repo's
  own permissions.

## Testing / Validation Plan

- **Pilot on `photo-cull`** — already the designated orchestration
  testbed. Apply the template via `copier copy` against its existing
  content (manual reconciliation where it conflicts with what's already
  there), run one real `/orchestrate` tick end to end, confirm the
  Issues-based backbone, decomposition rule, and `IMPROVEMENTS.md`
  capture all work in practice.
- **Update-path dry run** — after the pilot, make one deliberate template
  change and confirm `copier update` against a second repo applies it
  cleanly.
- **Feedback-loop dry run** — deliberately seed one `[template]`-tagged
  `IMPROVEMENTS.md` entry and confirm the review subagent classifies and
  PRs it correctly before relying on it for real findings.

## Rollout Plan

1. Build template content in this repo.
2. Pilot on `photo-cull`.
3. Iterate on the template using its own feedback loop (bootstrapped —
   the pilot's own friction becomes the first real `[template]` PRs).
4. Roll out to remaining active repos (kapekost-web, workout-tracker,
   claude/home-assistant) opportunistically via `copier update` /
   `copier link` — no forced migration.

## Open questions (proposed defaults — confirm or override)

- **Template repo hosting** — proposed: private GitHub repo under the
  owner's personal account, same as other active repos. Confirm.
- **Decomposition thresholds** — proposed: carry dimkos's existing
  numbers forward unchanged (>40 files or ~150k tokens per task
  triggers mandatory split/checkpoint). Confirm or tune.
- **`/orchestrate review-feedback` cadence** — proposed: run
  automatically at the end of every tick that logged at least one new
  `IMPROVEMENTS.md` entry, rather than requiring a separate manual
  invocation. Confirm.
