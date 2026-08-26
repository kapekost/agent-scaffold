# Human/Agent Collaboration Model — Design Spec

Date: 2026-08-26
Status: Draft, pending owner review

## Problem

The orchestration system (`/orchestrate` + `docs/orchestration/{PLAYBOOK,GUARDRAILS,STATE,
DECISIONS,IMPROVEMENTS}.md`) fully specifies *agent* behavior — how a tick runs, what's
forbidden, how state is tracked. It says nothing, anywhere, addressed to the *human* on the
other end of it: what their job is each cycle, what they should expect to see, where to look.
Someone browsing `docs/orchestration/` today finds five agent-facing operating documents and
no orientation.

This surfaced concretely during the first real use of the system (migrating old-style
markdown backlogs into GitHub Issues across two projects, 2026-08-26): the owner had no way
to tell that a tick had produced a new question for them, because the orchestrator's Issue
comments are posted under the owner's own `gh` authentication — GitHub never notifies an
account of its own activity. The complaint that surfaced this ("no notification as it looks
it comes from me") is a specific instance of a general gap: the system has no human-facing
observability story.

A second, related gap surfaced while designing the fix: GUARDRAILS' merge rule ("never
auto-merge... a human merges") no longer matches how work actually happened today — every PR
this session was opened by the agent, reviewed by CI, then merged by the agent after the
owner said "yes" live, once per PR. That live-approval loop is also what tripped a permission
block partway through (`gh pr merge --squash` was denied by the session's own auto-mode
classifier), forcing a stop-and-ask that a cleaner rule would avoid.

## Goals

- Give a human picking up this template (or returning to a project using it) a single,
  diagram-led entry point to `docs/orchestration/` explaining what their role is, what the
  agent's role is, and where each cycle's state lives.
- Close the "I don't know something needs me" gap using a mechanism that exists today
  (`PushNotification`), not new infrastructure.
- Resolve the merge-rule mismatch explicitly, as a superseding decision — not a silent
  reinterpretation of existing text.

## Non-Goals

- **No distinct agent GitHub identity (bot account / GitHub App) in this pass.** It would
  give a cleaner attribution trail in the Issue timeline, but it's new credential
  infrastructure to provision and manage; `PushNotification` alone solves the actual
  complaint (real-time "something needs you," not historical attribution). Revisit only if
  the live-alert approach proves insufficient in practice.
- **Not re-litigating the intake/triage/INVEST flow, task sizing, or destructive-op approval.**
  Those are working as designed; this spec only adds an orientation layer on top and closes
  the two gaps above.

## Supersedes

**The 2026-08-25 project-template design spec's explicit non-goal:** *"No auto-merge,
anywhere, for anything. Every existing GUARDRAILS approval gate stays intact; template-level
PRs get the same treatment."* That was a deliberate, considered choice one day before this
one — not accidental wording, and it explicitly called out template-repo PRs as deserving the
same manual gate as destructive operations. Now that the system has been exercised, the owner
has confirmed the merge rule should change **for both**: auto-merge on green CI applies
uniformly, including to PRs against this template repo itself — no carve-out. Named here
explicitly so a future reader doesn't find two specs disagreeing without knowing which one is
current, and doesn't assume a template-PR exception exists when it was deliberately
considered and rejected.

## Design

### 1. Roles, at a glance

| | Human | Agent |
|---|---|---|
| Feature ideas | Originates, states outcome/constraints/priority | Never invents scope |
| Prioritization | Ranks the Project board | Follows the board's rank, never reorders itself |
| Open questions | Answers via Issue comment | Asks, waits, never guesses |
| Destructive approval | Sole holder of `approved` | Never self-approves |
| Execution | — | Plans, codes, tests, reviews, opens PRs |
| Housekeeping | — | Keeps STATE/DECISIONS/IMPROVEMENTS current, links docs, closes stale issues |
| Merge | Enables the policy once (branch protection + "Allow auto-merge") | Opens PR, enables `--auto`, CI gates the rest |
| Observability | Gets pushed a notification when something needs them | Reports every tick into STATE.md + Issue comments |

### 2. Two diagrams, not one

The intake cycle (occasional, human-initiated) and the steady-state tick (recurring,
agent-initiated) are different rhythms; combining them into one diagram makes both harder to
follow. Both render as fenced code blocks (GitHub does not auto-render ASCII as a diagram,
but this matches the existing style of GUARDRAILS' "chain of authority" block, and needs no
new tooling or Mermaid dependency).

**Feature Intake Cycle:**
```
Human: raw idea -> Agent: ask clarifying questions (outcome, non-goals, constraints, priority)
  -> Agent: capture as `intake` Issue -> Agent: Triage/INVEST
  - small enough -> `ready`
  - needs owner input -> `needs-clarification` -> Human answers -> back to Triage
  - too big -> split into `ready` children
`ready` -> Agent: plan+execute+test+review -> PR (auto-merge enabled) -> CI green?
  no -> back to execute (fix, push again)
  yes -> merged, no further action needed
```

**Steady-State Tick** (what `/orchestrate` does each run):
```
Tick starts -> Reconcile git/gh/STATE.md -> new human comments since last tick?
  yes -> answer them first
  -> pick next ready/intake Issue -> execute -> update STATE.md + comment on Issue
  -> needs the human now? (new question / hard stop / nothing left unattended)
      yes -> PushNotification -> tick ends
      no -> tick ends
```
(Step 8, feedback review, is omitted above — it only runs when the tick logged a new
`IMPROVEMENTS.md` entry, so it's conditional rather than part of every cycle.)

### 3. Observability: `PushNotification`, not a new channel

`PLAYBOOK.md`'s step 9 ("Close the tick") gains one conditional action: if the tick produced
something the owner couldn't already know about without checking — a new `intake`/
`needs-clarification` question now waiting on them, a hard stop, or nothing left to do
unattended — call `PushNotification` with a one-line summary. Skip it when the tick ended cleanly with
more `ready` work still queued; a notification for every tick defeats the purpose (the tool's
own guidance: "a notification they didn't need is annoying in a way that accumulates").

This requires no new infrastructure — `PushNotification` is a capability of the Claude Code
session already, including scheduled/cloud sessions, not something specific to GitHub.

### 4. Merge policy: auto-merge on green CI

`PLAYBOOK.md` step 6 changes from "open a PR, wait for CI, never auto-merge" to: open the PR,
then immediately run `gh pr merge --auto --squash --delete-branch <PR>`. This flags the PR to
merge once required CI checks pass; it does not merge synchronously and never bypasses a red
check. `GUARDRAILS.md`'s merge rule and "chain of authority" diagram are updated to match —
the human's role moves from "merges each PR" to "enabled the auto-merge policy once, up
front" (repo setting: "Allow auto-merge", plus branch protection requiring the CI check).

This is coherent with the rest of the gate structure, not a review step being skipped: code
review already happens pre-PR via `superpowers:requesting-code-review` (PLAYBOOK step 5), and
destructive work is already gated by the `approved` label before execution starts (GUARDRAILS
"Destructive operations") — auto-merge doesn't remove either gate, it just stops asking the
human to re-approve what CI and those earlier gates already cleared.

**No carve-out for template-repo PRs.** GUARDRAILS' "Cross-repo writes" section previously
required `[template]`-tagged PRs to skip auto-merge entirely (the clause named in "Supersedes"
above). That's removed: template PRs auto-merge on green CI exactly like any other PR. The
credential restriction in that section (a `[template]`-tagged PR may only be opened with a
named, explicit credential, never this repo's own `gh` auth) is unchanged and remains the
actual safeguard for that class of PR — it was never a merge-gate, and doesn't need to become
one now.

## Rollout

1. Template (`agent-scaffold`): `GUARDRAILS.md.jinja` and `PLAYBOOK.md.jinja` already edited
   as part of this design pass (merge policy, template-PR carve-out removed, PushNotification
   step). Remaining work: author `template/docs/orchestration/README.md.jinja` (new file)
   containing sections 1 and 2 above, parameterized with `{{ project_name }}` where natural.
2. `tests/test_copier_generate.sh` should get one new `assert_file
   "docs/orchestration/README.md"` line (plus a content assertion or two) for the new file, as
   normal practice for anything the template generates — verified this is not required to keep
   the suite passing (the full-tree count check compares `template/` against generated output,
   and both sides increment together when a new file renders normally), but it's still the
   right coverage for a file whose content actually matters.
3. **Enable the auto-merge prerequisite** in all three repos (`agent-scaffold`,
   `workout-tracker`, `kapekost-web`) before step 6/GUARDRAILS' new rule can actually work: repo
   setting "Allow auto-merge", plus branch protection on the default branch requiring the CI
   check to pass. Without this, the first `gh pr merge --auto` call in any of them fails.
4. Propagate the doc changes to `workout-tracker` and `kapekost-web` via `copier update` in
   each. Both will also need a `DECISIONS.md` entry recording the auto-merge policy change
   locally (mirroring how the 2026-08-26 B2C-reversal decision was logged in `kapekost-web`),
   since their copies of `GUARDRAILS.md` currently still say "never auto-merge" until the
   update lands.
5. No `STATE.md`/`.claude/commands/orchestrate.md.jinja` changes needed — the command
   dispatch table is unaffected; only step content within the tick changes.
