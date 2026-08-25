# agent-scaffold

GitHub + Claude Code scaffolding for multi-agent orchestration:
issue-backed tasks, context-budget decomposition, out of the box.

A [Copier](https://copier.readthedocs.io/) template that sets up a new
or existing project with:

- **GitHub scaffolding** — issue forms, PR template, CODEOWNERS, labels,
  baseline CI
- **A `.claude/` baseline** for Claude Code
- **A generalized orchestration pattern** (`/orchestrate` +
  `docs/orchestration/`), backed by GitHub Issues rather than a
  persistent named-agent roster
- **Context-budget task decomposition** — tasks are sized to fit an
  agent's context window, not assigned to a fixed role
- **A two-tier feedback loop** so fixes discovered in a generated
  project can be pulled back into the template itself

Design rationale: `docs/superpowers/specs/2026-08-25-project-template-design.md`.

## Create a new project

```bash
pipx install copier   # once per machine
copier copy gh:kapekost/agent-scaffold <destination-dir>
```

## Pull template updates into an existing project

```bash
cd <existing-project>
copier update
```

This diffs your repo's `.copier-answers.yml` (written the first time you
ran `copier copy`) against the template's current state and applies
changes as a local, reviewable diff. Conflicts are never auto-resolved;
resolve them by hand, same as any merge conflict.

Note: if this template repo has any git tags, `copier update` tracks the
latest tag, not the `main` branch tip. Until this project has a
documented tagging convention, avoid tagging `agent-scaffold`, or use
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

## License

[MIT](LICENSE)
