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

Note: if this template repo has any git tags, `copier update` tracks the
latest tag, not the `main` branch tip. Until this project has a
documented tagging convention, avoid tagging `project-template`, or use
`copier update --vcs-ref=HEAD` to force tracking the branch tip instead.

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
