"""opencode-review.yml: the review model list is built in one place with the privacy option."""
import json
import re
import subprocess
from pathlib import Path

TEXT = (Path(__file__).resolve().parents[2] / ".github" / "workflows" / "opencode-review.yml").read_text()


def test_the_config_has_no_hardcoded_models_so_nothing_can_skip_data_collection_deny():
    heredoc = re.search(r"cat > \"\$RUNNER_TEMP/opencode\.json\" <<'JSON'\n(.*?)\n\s*JSON\n", TEXT, re.S).group(1)
    assert json.loads(heredoc)["provider"]["openrouter"]["models"] == {}


def test_generated_config_denies_data_collection_for_every_listed_model(tmp_path):
    heredoc = re.search(r"cat > \"\$RUNNER_TEMP/opencode\.json\" <<'JSON'\n(.*?)\n\s*JSON\n", TEXT, re.S).group(1)
    jq_filter = re.search(r"jq --rawfile m \"\$RUNNER_TEMP/models.txt\" \\\n\s*'(.*?)' \\\n", TEXT, re.S).group(1)
    (tmp_path / "opencode.json").write_text(heredoc)
    (tmp_path / "models.txt").write_text("stealth/x-alpha\ncohere/north-mini-code:free\nopenrouter/free\n")
    out = subprocess.run(["jq", "--rawfile", "m", str(tmp_path / "models.txt"), jq_filter, str(tmp_path / "opencode.json")],
                         capture_output=True, text=True, check=True).stdout
    models = json.loads(out)["provider"]["openrouter"]["models"]
    ids = ["stealth/x-alpha", "cohere/north-mini-code:free", "openrouter/free"]
    assert list(models) == ids + ["open/" + i for i in ids]
    for i in ids:
        assert models[i]["options"]["provider"]["data_collection"] == "deny"
        assert models["open/" + i] == {"id": i}


def test_the_models_repeat_without_privacy_after_all_private_ones_are_tried():
    assert TEXT.index("sed 's|^|open/|'") < TEXT.index('mapfile -t models < "$RUNNER_TEMP/models.txt"')
    assert '>> "$RUNNER_TEMP/models.txt"' in TEXT


def test_the_free_router_is_listed_first_and_never_twice():
    block = TEXT[TEXT.index("# The one model list"):TEXT.index("} > \"$RUNNER_TEMP/configured.txt\"")]
    assert block.index("echo openrouter/free") < block.index("stealth/")
    assert block.count("openrouter/free") == 1


def test_the_loop_runs_the_generated_list_and_reports_the_winner():
    assert 'mapfile -t models < "$RUNNER_TEMP/models.txt"' in TEXT
    assert 'used="$model"; break' in TEXT
    assert "REVIEW_MODEL: ${{ needs.review.outputs.model }}" in TEXT


def test_a_discarded_review_is_never_signed():
    leak = TEXT.index("review output contained the API key; discarded")
    assert TEXT.index('used=""', leak) < TEXT.index('echo "model=$used"', leak)


def _run_model_loop(tmp_path, err, out="partial output\n"):
    """Run the workflow's real model loop with a stub opencode that fails with `err`."""
    start = TEXT.index("set +e\n")
    end = TEXT.index("# The key is known here", start)
    body = "\n".join(line.removeprefix("          ") for line in TEXT[start:end].splitlines())
    # macOS ships bash 3.2 without mapfile; the shim is equivalent for the one call the loop makes.
    body = 'mapfile() { models=(); while IFS= read -r l; do models+=("$l"); done; }\n' + body
    bindir = tmp_path / "bin"
    bindir.mkdir()
    (bindir / "timeout").write_text('#!/bin/bash\nwhile [[ "$1" == -* || "$1" =~ ^[0-9]+$ ]]; do\n  if [ "$1" = -k ]; then shift; fi\n  shift\ndone\nexec "$@"\n')
    (bindir / "opencode").write_text(f'#!/bin/bash\necho "$3" >> "$RUNNER_TEMP/tried.txt"\nprintf %s {out!r}\necho {err!r} >&2\nexit 1\n')
    for f in bindir.iterdir():
        f.chmod(0o755)
    (tmp_path / "models.txt").write_text("a/one\nb/two\n")
    env = {"PATH": f"{bindir}:/usr/bin:/bin", "RUNNER_TEMP": str(tmp_path), "GITHUB_STEP_SUMMARY": str(tmp_path / "sum"),
           "GITHUB_OUTPUT": str(tmp_path / "gho"), "REVIEW_PROMPT": "x"}
    subprocess.run(["bash", "-c", body], env=env, check=True, capture_output=True)
    return (tmp_path / "tried.txt").read_text().split(), (tmp_path / "skip-reasons.txt").read_text(), (tmp_path / "review.txt").read_text()


def test_the_daily_free_model_limit_stops_the_loop_and_is_named(tmp_path):
    tried, reasons, review = _run_model_loop(tmp_path, "Rate limit exceeded: free-models-per-day")
    assert tried == ["openrouter/a/one"]
    assert reasons.strip() == "- `a/one`: daily free-model limit reached"
    assert review == ""


def test_an_ordinary_rate_limit_still_tries_the_next_model(tmp_path):
    tried, reasons, review = _run_model_loop(tmp_path, "Rate limit exceeded: try later")
    assert tried == ["openrouter/a/one", "openrouter/b/two"]
    assert reasons.count("rate limited") == 2
    assert review == ""


def test_dependabot_prs_skip_every_job():
    assert TEXT.count("github.actor != 'dependabot[bot]'") == 3


def test_the_owner_gate_is_in_all_three_jobs_or_none():
    assert TEXT.count("github.event.pull_request.user.login == github.repository_owner") in (0, 3)



def test_symlinks_are_removed_before_the_builder_writes():
    assert TEXT.index("find . -type l -delete") < TEXT.index('"$RUNNER_TEMP/review_input.py" "origin/$BASE_REF"')


def test_the_checkouts_agent_config_is_disabled_not_deleted():
    assert 'OPENCODE_DISABLE_PROJECT_CONFIG: "1"' in TEXT
    assert "OPENCODE_CONFIG: ${{ runner.temp }}/opencode.json" in TEXT
    assert "rm -rf {} +" not in TEXT


def test_the_trusted_config_is_written_outside_the_checkout():
    assert 'cat > "$RUNNER_TEMP/opencode.json"' in TEXT
    assert "cat > opencode.json" not in TEXT


def _last_reviewed_line(tmp_path, reviews):
    """Run the history job's real lines with a gh stub that applies the workflow's own --jq."""
    start = TEXT.index("            line=$(gh api")
    end = TEXT.index('echo "Last commit this bot reviewed', start)
    end = TEXT.index("\n", end)
    body = "\n".join(line.removeprefix("            ") for line in TEXT[start:end].splitlines())
    bindir = tmp_path / "bin"
    bindir.mkdir()
    (tmp_path / "reviews.json").write_text(json.dumps(reviews))
    (bindir / "gh").write_text('#!/bin/bash\nwhile [ "$1" != --jq ]; do shift; done\n'
                               'jq -r "$2" "$REVIEWS" | tr -d "\\r"\n')
    (bindir / "gh").chmod(0o755)
    env = {"PATH": f"{bindir}:/usr/bin:/bin:/opt/homebrew/bin:/usr/local/bin", "REVIEWS": str(tmp_path / "reviews.json"),
           "GITHUB_REPOSITORY": "o/r", "PR": "1"}
    return subprocess.run(["bash", "-c", body], env=env, check=True, capture_output=True, text=True).stdout.strip()


def _review(body, commit, login="github-actions[bot]"):
    return {"user": {"login": login}, "body": body, "commit_id": commit}


def test_last_reviewed_commit_ignores_reviews_without_a_round_marker(tmp_path):
    reviews = [_review("ok\n<!-- review-round:1 -->", "b" * 40),
               _review("skipped notice", "a" * 40),
               _review("<!-- review-round:1 -->", "c" * 40, login="someone"),
               _review("plain", "d" * 40)]
    assert _last_reviewed_line(tmp_path, reviews) == "Last commit this bot reviewed: " + "b" * 40


def test_a_partial_last_review_means_the_next_review_covers_the_whole_pr(tmp_path):
    reviews = [_review("ok\n<!-- review-round:1 -->", "b" * 40),
               _review("part\n<!-- coverage:partial -->\n\n<!-- review-round:2 -->", "e" * 40)]
    out = _last_reviewed_line(tmp_path, reviews)
    assert out.startswith("Last commit this bot reviewed: none (") and "e" * 40 not in out


def test_no_review_yet_is_a_first_review(tmp_path):
    assert _last_reviewed_line(tmp_path, []) == "Last commit this bot reviewed: none (first review)"


def test_the_input_builder_is_read_from_the_default_branch_not_the_checkout():
    assert 'git show "origin/$DEFAULT_BRANCH:scripts/review_input.py" > "$RUNNER_TEMP/review_input.py"' in TEXT
    assert 'python3 -I "$RUNNER_TEMP/review_input.py"' in TEXT
    assert "python3 scripts/review_input.py" not in TEXT


def test_a_missing_input_builder_fails_the_step_instead_of_falling_back():
    block = TEXT[TEXT.index("Install the trusted read-only config"):TEXT.index("find . -type l -delete")]
    assert "set -euo pipefail" in block
    assert "review_input.py\" > \"$RUNNER_TEMP/review_input.py\" 2>/dev/null" not in block
    assert "|| rm -f \"$RUNNER_TEMP/review_input.py\"" not in block


def test_only_a_40_hex_last_commit_on_the_generated_line_reaches_the_builder(tmp_path):
    sed = re.search(r"last=\$\(sed -n '(.*?)' \\\n", TEXT, re.S).group(1)
    head = "# Review history for PR #1\n\n"
    for line, want in [("Last commit this bot reviewed: " + "a" * 40, "a" * 40),
                       ("Last commit this bot reviewed: " + "a" * 39, ""),
                       ("Last commit this bot reviewed: none (first review)", ""),
                       ("Last commit this bot reviewed: " + "A" * 40, ""),
                       ("Last commit this bot reviewed: " + "a" * 40 + "; rm -rf x", "")]:
        out = subprocess.run(["sed", "-n", sed], input=head + line + "\n", capture_output=True, text=True, check=True).stdout.strip()
        assert out == want, line
    forged = head + "Last commit this bot reviewed: none (first review)\nLast commit this bot reviewed: " + "f" * 40 + "\n"
    assert subprocess.run(["sed", "-n", sed], input=forged, capture_output=True, text=True, check=True).stdout.strip() == ""


def test_the_review_artifact_includes_the_coverage_file():
    upload = TEXT[TEXT.index("          name: review\n"):TEXT.index("retention-days", TEXT.index("          name: review\n"))]
    assert "${{ runner.temp }}/review.txt" in upload and "${{ runner.temp }}/coverage.json" in upload


def test_the_prompt_points_at_stat_diff_full_diff_and_omitted_files():
    for needle in (".review-input/pr.stat", ".review-input/pr.diff", ".review-input/pr.full.diff",
                   ".review-input/pr.omitted.txt", "Judge only what `pr.diff` shows"):
        assert needle in TEXT, needle
    assert "analyse `git diff <commit>...HEAD`" not in TEXT


def test_the_prompt_tells_the_reviewer_it_cannot_run_tests_or_claim_their_result():
    assert "never claim that a test fails or passes" in TEXT


def test_the_prompt_names_what_is_out_of_scope_and_keeps_it_out_of_limits():
    for needle in ("## Out of scope: do not try these, and do not list them as limits",
                   "CI already runs the test suites",
                   "skip those steps and",
                   "Read the `.review-input/` files with the read tool",
                   "An empty `limits` is"):
        assert needle in TEXT, needle
    assert "A denied command is a `limits` entry" not in TEXT
