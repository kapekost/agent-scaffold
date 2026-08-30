# Orchestration Playbook

> How `/orchestrate` runs. Obey `GUARDRAILS.md` (it wins on conflict). Source of truth for tasks is
> GitHub Issues + Projects (see below); this file is *how* to drive them. Reuse superpowers skills —
> do not reinvent.

## When to actually use this

The Project board and the intake/triage machinery below earn their keep once a repo has ongoing,
real feature work moving through it — not from the first commit. A one-off fix, or a repo nobody's
actively driving feature requests into yet, doesn't need Issues, a ranked board, or
clarifying-question ceremony: just do the work directly. Turn this on once a product owner starts
bringing feature requests you'd otherwise have to remember and sequence yourself.

## Feature intake (product owner → Issues)

A high-level feature request from the product owner — in conversation, not yet an Issue — does not
go straight to code, and does not get invented scope on their behalf.

1. **Ask clarifying questions** to shape it: the actual user-facing outcome, what's explicitly out
   of scope, constraints, rough priority. Do not guess at intent — the same "never guess" principle
   GUARDRAILS applies to destructive-op approval applies here to scope.
2. **Capture the raw ask as a single Issue labeled `intake`** before attempting full decomposition —
   even a rough capture beats losing the ask to context. `intake` means "not triaged at all yet";
   it is a different state from `needs-clarification` ("was triaged and failed" — see the Triage /
   INVEST gate below). Neither is `ready`.
3. **Run it through the Triage / INVEST gate.** If it's small enough as one Issue, relabel `intake` →
   `ready` (or `needs-clarification` if it still doesn't pass) directly. If it needs splitting, open
   properly-scoped child Issues (type/priority/effort labeled, INVEST-checked, referencing the
   `intake` Issue), add them to the Project board ranked, then close the `intake` Issue with a
   pointer to its children.
4. An unattended `/orchestrate` tick that reaches an `intake`-labeled Issue and can't resolve steps
   1–3 without the owner (the clarifying questions have no answer yet) treats it exactly like a
   failed INVEST gate: relabel `needs-clarification`, stop, flag for the owner. Never guess and never
   invent an answer to keep moving.

## Command variants (dispatch on the argument)
- `/orchestrate` (no arg) — run the next tick.
- `/orchestrate status` — reconstruct + report only. **No execution, no writes.** Cheapest path.
- `/orchestrate approve <issue-number>` — **human-only**, never dispatched by an unattended tick (see
  GUARDRAILS "Approval is human-only"). When a human runs it: add the `approved` label to the given
  Issue, comment why, stop.
- `/orchestrate plan <issue-number>` — write the detailed plan for an Issue lacking one, via
  `superpowers:writing-plans`, then stop.
- `/orchestrate review-feedback` — run only step 8 below (feedback review), then stop. Also runs
  automatically at the end of any tick that logged a new `IMPROVEMENTS.md` entry.
- `/orchestrate stop` — set `STATE.md` → Stop-condition to "owner stop", commit, stop.

## Triage / INVEST gate
Before an Issue gets the `ready` label, it must pass a basic INVEST sanity check (Independent,
Negotiable, Valuable, Estimable, Small, Testable — see the `feature` issue form). If it clearly
fails — too vague, too large for its stated effort, or not independently actionable — label it
`needs-clarification` instead of `ready` and stop; do not guess at intent. An Issue arriving via
Feature intake starts labeled `intake`, not `needs-clarification` — see that section above for the
distinction.

Issue dependencies (`blocked-by`) are tracked via GitHub's native issue-dependency relationship,
not a label: set it through the Issue UI's "Blockers" panel, since there is no plain `gh issue`
subcommand for it (it's a GraphQL-only feature, reachable via `gh api graphql` if scripting it
later). Until that's automated, check an Issue's blocked status by reading its "Blocked by" panel
in the UI (or `gh api graphql` for the same data) before treating it as pickable in step 3 below.

## The tick (for `/orchestrate` with no arg)
1. **Read** `STATE.md`, `GUARDRAILS.md`, `DECISIONS.md`. Do not read source files yet.
2. **Reconcile reality:** `git status`, `gh pr list`, `gh issue list --label ready --state open`
   (sorted by the Project's manual rank). If reality diverged from `STATE.md`, correct `STATE.md` and
   continue. Also check for new owner comments since the last tick on any Issue currently in
   progress, or any `intake`/`needs-clarification` Issue awaiting an answer
   (`gh issue view <n> --comments`, or `gh api` filtered by date if scripting it across many Issues) —
   respond to them (answer, incorporate the feedback, or act on it) before picking the next action.
   A comment sitting unanswered across a tick boundary is a bug in the loop, not something to defer.
3. **Pick the next action.** If any Issue is labeled `intake`, resolve the highest-ranked one first
   via the Feature intake flow above, then re-run this step. Otherwise: highest-ranked open Issue
   with the `ready` label and no unresolved `blocked-by` dependency. Then:
   - If it has no linked plan and is `effort:M` or larger → run the `/orchestrate plan` flow and stop.
   - If it is `effort:L`/`XL` and has no sub-Issues yet → split it per GUARDRAILS "Task sizing" and stop.
   - If it is **destructive** (per GUARDRAILS) and lacks the `approved` label → skip to the next ready
     Issue; if none, stop + notify.
   - Else → execute.
4. **Execute** via `superpowers:subagent-driven-development`. Lean: dispatch one subagent per task; it
   reads only the Issue + its plan doc + the named files, never the whole tree. If context bloats
   mid-task per GUARDRAILS, checkpoint and hand off to a fresh subagent rather than pushing through.
   Tell the subagent to log friction as it goes: whenever it hits something worth noting (a wrong
   guardrail, a missing tool, an outdated doc), run
   `scripts/append_improvement.sh <local|template|unsure> "<note>"` inline rather than waiting.
5. **Gate:** run the task's verification commands; then `superpowers:requesting-code-review` (spec +
   code quality). At a deploy/milestone checkpoint, also run `/security-review`.
6. **PR:** open a PR referencing the Issue (`Closes #N`), then run
   `gh pr checks <PR> --watch --fail-fast` to block until CI finishes. **Right after any push** (new PR
   or a new commit on one already open), `--watch` can return a stale rollup for the *previous* commit
   if checks haven't registered yet server-side — confirm `gh pr view <PR> --json
   headRefOid,statusCheckRollup` shows the commit you just pushed before trusting a green result; if
   it's stale, wait and re-check rather than merging on faith. Once genuinely green: merge immediately
   (`gh pr merge <PR> --squash --delete-branch`), no further live approval needed. If checks exit
   non-zero, treat red CI as a hard stop — do not merge, fix and push again. Do not use `gh pr merge
   --auto` — it only waits for checks configured as *required* via branch protection, which may not
   exist (or, on a private repo on the free plan, may not even be available); without that, `--auto`
   merges immediately, before CI has even started.
   If the base branch moved since the PR opened and it now conflicts, resolve by hand — read both
   sides' intent, never blindly take one side or force through — then re-run local verification before
   pushing the merge commit.
7. **Write state back:** comment progress on the Issue; update `STATE.md`'s cursor/next-action only
   when on the orchestration home branch, never on a feature branch; append to `DECISIONS.md` if a
   decision was made.
8. **Feedback review:** if this tick appended any `IMPROVEMENTS.md` entries, run
   `scripts/improvements_since_cursor.sh`, classify each (`[local]` → PR in this repo; `[template]` →
   PR against the template repo per GUARDRAILS "Cross-repo writes"; `[unsure]` → `STATE.md` → Needs
   owner), then run `scripts/advance_improvements_cursor.sh` with the new total entry count. Skip this
   step entirely if nothing new was logged this tick.
9. **Close the tick:** print a one-screen summary (position, what you did, next action, anything
   needing the owner). If the tick ends with something the owner couldn't already know about without
   checking — a new `intake`/`needs-clarification` question now waiting on them, a hard stop, or
   nothing left to do unattended — call `PushNotification` with a one-line summary. Skip it for routine
   ticks that ended cleanly with more `ready` work still queued; a notification for every tick is worse
   than none.

## Budget & checkpointing
Track work against the GUARDRAILS per-tick token budget. When near the limit, finish the current
step, write `STATE.md`, and stop with a clean resume note rather than starting a new task.

## Lean rules (always)
- Prefer `git`/`gh`/grep over reading files. Read a file only when about to change it.
- One subagent per task with an explicit file list. Summarize subagent results into STATE; do not
  pull their full transcripts into the controller context.
