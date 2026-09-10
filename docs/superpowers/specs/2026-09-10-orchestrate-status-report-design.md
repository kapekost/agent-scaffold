# `/orchestrate status` Report — Design Spec

Date: 2026-09-10
Status: Approved by owner after an independent research pass (subagent review of
`workout-tracker` and `dimkos`'s live orchestration state); proceeding to implementation plan.

## Problem

The owner's own framing: "it's a little hard to understand in a quick view where we are and
what's next." Digging into why surfaced three places that *look* like the answer but aren't
wired to stay current:

1. **The GitHub Projects v2 board's `Status` field is decorative.** Verified via `gh api
   graphql` on both live repos: `workout-tracker` (project #3) mirrors `state:OPEN`→`Todo` /
   `state:CLOSED`→`Done` — `In Progress` has zero items, ever. `dimkos` (project #2) is worse:
   its sync script creates draft items and never writes the `Status` field at all, so
   completed, deployed phases still show `Todo`. Nothing in `PLAYBOOK.md`'s tick logic ever
   writes to this field — GitHub's own built-in automation is the only thing touching it.
2. **`STATE.md`, read from the working tree, is stale by design and currently wrong.**
   `workout-tracker`'s `main`-branch copy says an Issue is executing that closed days ago. This
   isn't a bug exactly — the file is deliberately not the orchestration home branch's live copy
   — but a quick `cat` or GitHub file view of the "obvious" place to look gives a confidently
   wrong answer, with nothing signaling that.
3. **`IMPROVEMENTS.md` (the "agents log friction, it becomes real fixes" channel) works, but
   is invisible and has no closure mechanism.** 25 real entries exist on `workout-tracker`'s
   home branch, and it has already produced merged PRs (this repo's own #1 and #2 among them).
   But the `main`-branch mirror most people would actually open shows far fewer, and five
   `[unsure]`-tagged entries have sat 1-2+ weeks with no forcing function to resolve them.

A fourth, unrelated-but-adjacent bug surfaced during the same investigation: this template's
own `PLAYBOOK.md.jinja` still instructs new repos to track Issue blocking via GitHub's native
issue-dependency relationship ("Blockers" panel) — but `workout-tracker` already discovered
that field doesn't exist on the API (`issueDependenciesBlockedBy` → `undefinedField`) and
switched to a plain `blocked` label months ago. That correction never made it back to the
template, and — notably — it never went through `append_improvement.sh` either, meaning the
very mechanism meant to catch exactly this kind of drift didn't. Since fixing this touches the
same file this spec already changes, it's included here rather than filed separately.

## Goals

- `/orchestrate status` produces a fixed, skimmable table — recomputed live on every
  invocation from sources that are already kept accurate for other reasons (Issue labels, the
  orchestration home branch's own `STATE.md`), so there is no new state to let go stale.
- The report also surfaces `IMPROVEMENTS.md` health (total entries, how many `[unsure]` are
  open, the oldest one's age) — the cheapest fix for "invisible and never closed," tried before
  reaching for a heavier mechanism.
- Fix the template's stale `blocked-by` instruction to match what actually works (`blocked`
  label) — the same file, the same PR, closing a drift the improvement pipeline should have
  caught.
- Close the specific bypass that let the `blocked-by` drift happen: a direct correction to
  `PLAYBOOK.md`/`GUARDRAILS.md` made mid-tick must also get an `append_improvement.sh` entry
  in the same commit.

## Non-Goals

- **Not wiring the Project board's `Status` field yet.** That's real, and it's the thing that
  gives phone/browser glanceability with no CLI session — but it's a second, separable piece of
  work (write `In Progress` at claim-time, add a `Blocked` option, self-heal stuck values) that
  depends on this one having actually run for a while, and `dimkos` would need its own
  sync-script rework first since it doesn't use GitHub Issues as its source of truth the way
  `workout-tracker` does. Revisit as its own spec once this has been in use for a couple of
  weeks.
- **No rendered dashboard (Artifact or otherwise).** Considered and rejected: it doesn't
  propagate through the copier template (Artifacts are per-account, so `copier update` could
  hand a repo the generator script but not a working dashboard), and a missed regeneration
  produces a confidently-wrong board — the same failure mode as the unused `Status` field, with
  better production values making it more convincing when wrong.
- **No new `/orchestrate triage-improvements` command in this pass.** The cheap fix (age/count
  visible in the status report) is being tried first. Only build a dedicated triage flow if
  `[unsure]` entries are still not getting resolved after this ships.
- **Not re-litigating the tick algorithm, task sizing, or destructive-op approval.** This spec
  only adds a read-only reporting surface and fixes two documentation drifts; it changes no
  execution behavior.

## Design

### 1. Report format

`/orchestrate status` prints exactly this shape (real numbers, not a mockup, once wired up):

```
READY (3): #127, #138, #137
IN PROGRESS (1): #125 — claimed 2026-09-10T03:54Z, paused (owner go-ahead pending)
BLOCKED (0)
NEEDS OWNER (2): #30/#32 spec skim; 2 [template] items open in agent-scaffold
INTAKE (2): #152, #148
IMPROVEMENTS: 25 logged, 5 [unsure] open (oldest: 11 days)
```

Each line is empty-safe (`BLOCKED (0)` prints with no list, not an error or an omitted line —
absence of blocked work is itself useful information).

### 2. Where each line comes from

- **READY** — `gh project item-list <project-number> --owner <owner> --query "status:Todo
  label:ready"`, which returns items in the Project's actual manual rank order (same source
  PLAYBOOK step 2/3 already use to pick the next Issue — see PR #3, merged the same day this spec
  was written: `gh issue list` was originally assumed to do this and does not, at all).
- **IN PROGRESS** — the orchestration home branch's own `STATE.md` `## In-flight` section,
  verbatim (claim timestamp + note), not the working tree's copy.
- **BLOCKED** — `gh issue list --label blocked --state open`.
- **NEEDS OWNER** — the home branch's `STATE.md` `## Needs owner` section, summarized to one
  line per item (title + repo if cross-repo, per the existing section's own convention).
- **INTAKE** — `gh issue list --label intake --state open`.
- **IMPROVEMENTS** — parsed from the home branch's `IMPROVEMENTS.md`: total log-line count,
  count of `[unsure]`-tagged lines, and the date on the oldest `[unsure]` line still present.

### 3. Read from the home branch, never the working tree

Every line above that comes from `STATE.md`/`IMPROVEMENTS.md` is read via
`git show origin/<home-branch>:docs/orchestration/<file>` (or an equivalent worktree), the same
pattern `PLAYBOOK.md` step 1 already establishes for the tick itself — this spec just applies
it consistently to the `status` variant too, since a report that's wrong in the same way the
problem it's fixing was wrong defeats the point. A repo with no distinct orchestration home
branch (docs committed straight to `{{ default_branch }}`) falls back to reading the working
tree directly — the home-branch pattern is a per-repo choice the template already supports, not
a hard requirement.

### 4. Fix the `blocked-by` instruction

Replace `PLAYBOOK.md.jinja`'s Triage/INVEST gate section's current text (which mandates
GitHub's native issue-dependency relationship) with `workout-tracker`'s live-corrected version:
dependencies are tracked via a plain `blocked` label, the blocking Issue is named in the body,
and a short note on *why* (the GraphQL field doesn't exist on this API) so a future reader
doesn't reintroduce the same dead end.

### 5. Close the bypass

Add one line to `PLAYBOOK.md.jinja` step 7 ("Write state back"): any direct edit to
`PLAYBOOK.md` or `GUARDRAILS.md` made mid-tick to correct something wrong gets an
`append_improvement.sh` entry in the same commit — `[template]` if the template's own copy
carries the same bug, `[local]` if it's specific to this repo's rendering of it. This is
precisely the step that was skipped when `workout-tracker` fixed `blocked-by` locally and the
fix never reached this template.

### 6. Command-file changes

`orchestrate.md.jinja`'s `status` dispatch line currently just says "reconstruct + report only;
make NO writes." Expand it to name the exact report shape (point at the new PLAYBOOK section
rather than duplicating it) so the command file and the playbook can't drift from each other.

## Rollout

This PR lands in `agent-scaffold` only — a template change, not a behavior change in any
running repo. Downstream repos (`workout-tracker`, `dimkos`, `photo-cull`, `kapekost-web`) pick
it up via `copier update`, run manually per repo whenever the owner chooses; nothing here
pushes automatically. First real validation is the next `/orchestrate status` invocation in
`workout-tracker` after that repo's own `copier update`.
