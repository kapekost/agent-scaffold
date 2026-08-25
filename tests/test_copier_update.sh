#!/usr/bin/env bash
set -euo pipefail

# Proves the propagation story from the spec: a change made to the
# template after a project was generated can be pulled in later via
# `copier update`, and the update leaves a `.copier-answers.yml` pointer
# behind so future updates keep working.

export PATH="$HOME/.local/bin:$PATH"
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
