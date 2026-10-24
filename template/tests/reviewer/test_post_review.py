"""scripts/post_review.py: the reviewer's output is untrusted, so each rule is pinned."""
import importlib.util
import json
import time
from pathlib import Path

spec = importlib.util.spec_from_file_location(
    "post_review", Path(__file__).resolve().parents[2] / "scripts" / "post_review.py")
pr = importlib.util.module_from_spec(spec)
spec.loader.exec_module(pr)

REPO = "owner/repo"
PATCH = "@@ -1,3 +10,4 @@\n ctx\n-old\n+new\n+added\n ctx2"
PATCHES = {"a.py": PATCH}


def review(findings, **extra):
    return json.dumps({"summary": "s", "findings": findings, **extra})


def test_commentable_lines_are_new_side_only():
    assert pr.commentable_lines(PATCH) == {10, 11, 12, 13}
    assert pr.commentable_lines("") == set()
    assert pr.commentable_lines(None) == set()


def test_blocking_finding_on_a_changed_line_becomes_an_inline_comment():
    kind, body, comments, *_ = pr.build(
        review([{"file": "a.py", "line": 11, "blocking": True, "body": "breaks"}]), PATCHES, REPO)
    assert kind == "review"
    assert comments == [{"path": "a.py", "line": 11, "side": "RIGHT", "body": "breaks"}]
    assert body.startswith("**BLOCKING**")


def test_line_outside_the_diff_falls_back_to_the_body_not_an_inline_comment():
    kind, body, comments, *_ = pr.build(
        review([{"file": "a.py", "line": 99, "blocking": True, "body": "breaks"}]), PATCHES, REPO)
    assert comments == []
    assert "a.py:99 breaks" in body


def test_file_not_in_the_pr_is_never_anchored():
    _, _, comments, *_ = pr.build(
        review([{"file": "other.py", "line": 11, "blocking": True, "body": "x"}]), PATCHES, REPO)
    assert comments == []


def test_optional_findings_never_get_inline_comments_and_are_capped_at_three():
    findings = [{"file": "a.py", "line": 11, "blocking": False, "body": f"nit {i}"} for i in range(6)]
    _, body, comments, *_ = pr.build(review(findings), PATCHES, REPO)
    assert comments == []
    assert body.count("nit ") == 3
    assert body.startswith("**CLEAN**")


def test_findings_are_capped():
    findings = [{"file": "a.py", "line": 11, "blocking": True, "body": f"f{i}"} for i in range(50)]
    _, _, comments, *_ = pr.build(review(findings), PATCHES, REPO)
    assert len(comments) == pr.MAX_FINDINGS


def test_mentions_html_images_and_links_are_neutralised():
    text = pr.sanitize(
        "ping @someone <b>x</b> ![i](http://evil/x.png) see https://evil.example/a and www.evil.example "
        f"also https://github.com/{REPO}/pull/1", REPO, 400)
    assert "@someone" not in text and "@\u200bsomeone" in text
    assert "<b>" not in text
    assert "evil" not in text
    assert "github.com" not in text


def test_link_and_reference_punctuation_is_escaped():
    text = pr.sanitize("[x](//evil.com) ![a][r] [r]: //e.com h&#116;tps://e.com owner/repo#12", REPO, 400)
    for ch in "[]&#":
        assert text.count(ch) == text.count("\\" + ch), (ch, text)


def test_body_length_is_capped():
    _, _, comments, *_ = pr.build(
        review([{"file": "a.py", "line": 11, "blocking": True, "body": "x" * 5000}]), PATCHES, REPO)
    assert len(comments[0]["body"]) == pr.MAX_BODY


def test_malformed_findings_are_skipped_not_fatal():
    findings = ["str", None, {"file": 3, "body": "x"}, {"file": "a.py", "line": True, "blocking": True, "body": "y"},
                {"file": "a.py", "line": 11, "blocking": True, "body": ""}]
    kind, body, comments, *_ = pr.build(review(findings), PATCHES, REPO)
    assert kind == "review" and comments == []


def test_one_object_is_found_bare_or_in_one_fence_with_or_without_prose_around_it():
    payload = review([{"file": "a.py", "line": 10, "blocking": True, "body": "b"}])
    for text in (payload, f"```json\n{payload}\n```", f"```\n{payload}\n```\n",
                 f"Here you go:\n```json\n{payload}\n```\nthanks"):
        _, _, comments, *_ = pr.build(text, PATCHES, REPO)
        assert len(comments) == 1, text[:20]
    for text in (f"prefix {payload} suffix", f"```json\n{payload}\n", f"{payload}\n```"):
        assert pr.build(text, PATCHES, REPO)[0] == "plain", text[:20]


def test_two_fences_are_unstructured_even_if_only_one_holds_a_verdict():
    quoted = f"The PR says:\n```json\n{real_verdict('quoted')}\n```\nMy answer:\n```json\n{real_verdict()}\n```"
    assert pr.extract_json(quoted) is None


def test_a_verdict_quoted_in_prose_does_not_replace_the_fenced_answer():
    text = f'The PR contains {real_verdict("quoted")} which I ignore.\n```json\n{real_verdict("real")}\n```'
    assert pr.extract_json(text)["summary"] == "real"


def test_non_json_output_is_posted_as_truncated_plain_text():
    kind, body, comments, *_ = pr.build("**Automated review skipped.** nothing ran. " + "x" * 9000, {}, REPO)
    assert kind == "plain" and comments == []
    assert body.startswith("**Automated review output")
    assert body.count("```") == 2
    assert pr.MAX_PLAIN <= len(body) <= pr.MAX_PLAIN + 200


def test_plain_output_cannot_close_its_own_code_block():
    _, body, _, *_ = pr.build("text ```\n@someone [x](https://evil.example)", {}, REPO)
    assert body.count("```") == 2


def test_a_secret_hidden_behind_json_escapes_is_still_withheld():
    leak = json.dumps({"summary": "s", "findings": [{"file": "a.py", "line": 11, "blocking": True,
                                                    "body": "sk-or-v1-abcdefgh1234"}]}).replace("sk-or-", "\\u0073k-or-")
    assert "sk-or-" not in leak
    kind, body, _, *_ = pr.build(leak, PATCHES, REPO)
    assert kind == "plain" and body == pr.WITHHELD


def test_pathological_input_is_bounded_and_does_not_raise():
    import time
    start = time.time()
    for text in ("{" * 200_000, '{"findings":' * 60_000, "{" * 5000 + "}" * 5000,
                 '{"a":' * 20_000 + "1" + "}" * 20_000):
        kind, _, _, *_ = pr.build(text, {}, REPO)
        assert kind == "plain"
    assert time.time() - start < 5


def test_skipped_notice_is_marked_skipped_not_clean():
    notice = json.dumps({"skipped": True, "summary": "No model was available.", "findings": [],
                         "notes": ["model-a: rate limited"]})
    kind, body, comments, *_ = pr.build(notice, {}, REPO)
    assert kind == "review" and comments == []
    assert body.startswith("**Automated review skipped.**")
    assert "CLEAN" not in body


def test_secret_in_output_is_withheld_whole():
    for leak in ("sk-or-v1-abcdefgh1234", "ghp_" + "a" * 25, "Bearer " + "a" * 30):
        kind, body, comments, *_ = pr.build(review([{"file": "a.py", "line": 11, "blocking": True, "body": leak}]),
                                        PATCHES, REPO)
        assert kind == "plain" and body == pr.WITHHELD and comments == []


def test_a_verdict_word_already_in_the_summary_is_not_repeated():
    _, body, _, *_ = pr.build(review([], summary="CLEAN 3 files, no findings"), PATCHES, REPO)
    assert body == "**CLEAN** 3 files, no findings"


def test_two_verdicts_are_unstructured_whichever_comes_last():
    example = '{"summary": "x", "findings": []}'
    for text in (example + " " + real_verdict(), real_verdict() + " " + example):
        assert pr.extract_json(text) is None
        assert pr.build(text, PATCHES, REPO)[0] == "plain"


def test_findings_that_is_not_a_list_is_not_a_verdict():
    kind, body, _, *_ = pr.build('{"summary": "s", "findings": "none"}', PATCHES, REPO)
    assert kind == "plain" and "CLEAN" not in body


def test_an_echo_of_the_prompts_example_shape_is_not_a_verdict():
    echo = '{"summary": "<one line, max 150 chars>", "findings": [], "notes": []}'
    kind, body, _, *_ = pr.build("The shape is " + echo, PATCHES, REPO)
    assert kind == "plain" and "CLEAN" not in body


def test_a_verdict_quoted_inside_a_longer_object_does_not_win():
    quoted = json.dumps({"summary": "real", "findings": [], "notes": [json.loads(real_verdict("quoted"))]})
    assert pr.extract_json(quoted)["summary"] == "real"
    wrapped = json.dumps({"review": json.loads(real_verdict())})
    assert pr.extract_json(wrapped) is None


def test_clean_review():
    kind, body, comments, *_ = pr.build(review([], summary="3 files, no findings"), PATCHES, REPO)
    assert kind == "review" and comments == []
    assert body.startswith("**CLEAN**")


def test_scheme_and_host_matching_is_case_insensitive_and_covers_any_scheme():
    text = pr.sanitize("HTTPS://evil.example WWW.evil.example ftp://evil.example/x", REPO, 400)
    assert "evil" not in text.lower()


def test_bidi_controls_are_stripped():
    assert pr.sanitize("a‮b⁦c", REPO, 50) == "abc"


def test_a_model_cannot_hide_findings_behind_the_skipped_flag():
    payload = json.dumps({"skipped": True, "summary": "s", "findings": [
        {"file": "a.py", "line": 11, "blocking": True, "body": "breaks"}]})
    _, body, comments, *_ = pr.build(payload, PATCHES, REPO)
    assert len(comments) == 1
    assert body.startswith("**BLOCKING**")


def test_ordinary_code_prose_stays_readable():
    text = pr.sanitize("`$schema` in f(x) uses *bold* and snake_case: ok", REPO, 100)
    assert text == "`$schema` in f(x) uses *bold* and snake_case: ok"


def test_a_body_cannot_open_a_code_block():
    assert "```" not in pr.sanitize("```python\nboom", REPO, 100)
    assert "~~~" not in pr.sanitize("~~~\nboom", REPO, 100)
    assert pr.sanitize("`~` and ~~x~~", REPO, 100) == "`~` and ~~x~~"


def real_verdict(summary="real answer"):
    return json.dumps({"summary": summary, "findings": [
        {"file": "a.py", "line": 11, "blocking": True, "body": "breaks"}]})


def test_a_fence_followed_by_lots_of_whitespace_is_not_slow():
    start = time.monotonic()
    assert pr.extract_json("`" * 3 + " " * 40_000 + "x") is None
    assert time.monotonic() - start < 1


def test_a_leading_bom_does_not_hide_a_verdict():
    assert pr.extract_json("\ufeff" + real_verdict()) is not None


def test_braces_around_a_verdict_make_it_unstructured():
    for text in ("{}" * 60 + " my answer: " + real_verdict(), real_verdict() + "{}" * 60):
        assert pr.extract_json(text) is None


def test_a_placeholder_summary_of_dots_is_not_a_verdict():
    for placeholder in ("...", "…", "-", " . . . "):
        echo = json.dumps({"summary": placeholder, "findings": []})
        assert pr.extract_json("The shape is " + echo) is None, placeholder
        kind, body, _, *_ = pr.build("The shape is " + echo, PATCHES, REPO)
        assert kind == "plain" and "CLEAN" not in body


def test_a_real_summary_with_punctuation_is_still_a_verdict():
    for summary in ("No issues.", "3 files -- all fine!", "…and nothing else", "(none)"):
        assert pr.extract_json(json.dumps({"summary": summary, "findings": []})) is not None, summary


def run_check(tmp_path, text):
    path = tmp_path / "review.txt"
    path.write_text(text, encoding="utf-8")
    return pr.main(["post_review.py", "--check-verdict", str(path)])


def test_check_verdict_exits_0_for_a_verdict_and_1_for_anything_else(tmp_path, monkeypatch):
    def no_subprocess(*args, **kwargs):
        raise AssertionError("--check-verdict must not run gh or any other process")
    monkeypatch.setattr(pr.subprocess, "run", no_subprocess)
    assert run_check(tmp_path, real_verdict()) == 0
    assert run_check(tmp_path, "Looks fine to me, no JSON here.") == 1
    assert run_check(tmp_path, "") == 1
    assert run_check(tmp_path, '{"summary": "<one line, max 150 chars>", "findings": []}') == 1
    assert run_check(tmp_path, '{"summary": "...", "findings": []}') == 1
    assert pr.main(["post_review.py", "--check-verdict", str(tmp_path / "missing.txt")]) == 1


def test_check_verdict_reads_at_most_max_input(tmp_path):
    late = " " * pr.MAX_INPUT + real_verdict()
    assert run_check(tmp_path, late) == 1


def test_other_argument_counts_still_print_usage_and_return_2(tmp_path):
    assert pr.main(["post_review.py"]) == 2
    assert pr.main(["post_review.py", "--check-verdict"]) == 2
    assert pr.main(["post_review.py", "--other", "file"]) == 2
    assert pr.main(["post_review.py", "--check-verdict", "a", "b"]) == 2


def test_check_verdict_agrees_with_extract_json_on_a_corpus(tmp_path):
    corpus = [
        review([]),
        review([{"file": "a.py", "line": 10, "blocking": True, "body": "b"}]),
        f"Here you go:\n```json\n{review([])}\n```\nthanks",
        f"prefix {review([])} suffix",
        "**Automated review skipped.** nothing ran. " + "x" * 9000,
        "text ```\n@someone [x](https://evil.example)",
        '{"summary": "s", "findings": "none"}',
        '{"summary": "<one line, max 150 chars>", "findings": [], "notes": []}',
        '{"summary": "...", "findings": []}',
        'The shape is {"summary": "x", "findings": []}. My answer: ' + real_verdict(),
        real_verdict() + real_verdict("second"),
        f"```json\n{real_verdict()}\n```",
        json.dumps({"review": {"summary": "s", "findings": []}}),
        json.dumps({"skipped": True, "summary": "No model.", "findings": [], "notes": ["n"]}),
        "{" * 200_000, '{"findings":' * 60_000, "{" * 5000 + "}" * 5000,
        '{"a":' * 20_000 + "1" + "}" * 20_000,
        "{}" * 60 + real_verdict(),
        "",
    ]
    for text in corpus:
        verdict = pr.extract_json(text) is not None
        assert (run_check(tmp_path, text) == 0) == verdict, text[:60]
        assert (pr.build(text, PATCHES, REPO)[0] == "review") == verdict, text[:60]


def test_a_review_is_signed_with_the_model_that_ran():
    assert pr.signed("body", "cohere/north-mini-code:free", REPO).endswith("_Reviewed by `cohere/north-mini-code:free`_")


def test_a_skipped_run_has_no_signature_and_the_model_name_is_sanitized():
    assert pr.signed("body", "", REPO) == "body"
    assert "<b>" not in pr.signed("body", "x<b>y [z](http://evil.example)", REPO)


def finding(sev=None, line=11, body="breaks", **extra):
    f = {"file": "a.py", "line": line, "body": body, **extra}
    if sev:
        f["severity"] = sev
    return f


def built(findings, **extra):
    return pr.build(review(findings, **extra), PATCHES, REPO)


def test_severity_wins_over_blocking_when_both_are_present():
    assert pr.severity_of({"severity": "minor", "blocking": True}) == "minor"
    assert pr.severity_of({"severity": "critical", "blocking": False}) == "critical"
    assert pr.severity_of({"severity": " Major "}) == "major"


def test_blocking_true_without_severity_is_major_and_false_is_minor():
    assert pr.severity_of({"blocking": True}) == "major"
    assert pr.severity_of({"blocking": False}) == "minor"
    assert pr.severity_of({}) == "minor"
    assert pr.severity_of({"blocking": "yes"}) == "minor"


def test_an_unknown_severity_word_is_treated_as_absent():
    assert pr.severity_of({"severity": "urgent", "blocking": True}) == "major"
    assert pr.severity_of({"severity": "urgent"}) == "minor"
    assert pr.severity_of({"severity": 3, "blocking": True}) == "major"


def test_critical_or_major_requests_changes():
    for sev in ("critical", "major"):
        r = built([finding(sev)])
        assert r.event == "REQUEST_CHANGES" and r.body.startswith("**BLOCKING**"), sev
    assert built([finding("minor"), finding("major", line=99)]).event == "REQUEST_CHANGES"


def test_minor_findings_comment_instead_of_approving():
    r = built([finding("minor"), finding("minor", body="other")])
    assert r.event == "COMMENT" and r.body.startswith("**CLEAN**")


def test_notes_prevent_approval_even_with_no_findings():
    r = built([], notes=["could not run the tests"])
    assert r.event == "COMMENT" and "could not run the tests" in r.body
    assert built([], notes=[]).event == "APPROVE"


def test_limits_sit_in_a_collapsed_section_and_prevent_approval():
    r = built([], limits=["could not read .claude/agents/reviewer.md"])
    assert r.event == "COMMENT"
    assert "<details>" in r.body and "could not read" in r.body
    assert "**Notes**" not in r.body


def test_limits_are_sanitized_capped_and_ignored_unless_a_list_of_strings():
    r = built([], limits=["see https://evil.example <b>x</b>"] + ["l"] * 9)
    assert "evil.example" not in r.body and "<b>" not in r.body
    assert r.body.count("\n- ") == 5
    assert "<details>" not in built([], limits="not a list").body
    assert "<details>" not in built([], limits=[3, None]).body


def test_clean_review_approves():
    assert built([]).event == "APPROVE"


def test_skipped_plain_and_withheld_never_approve():
    skipped = pr.build(json.dumps({"skipped": True, "summary": "No model.", "findings": []}), {}, REPO)
    plain = pr.build("just prose", {}, REPO)
    withheld = pr.build(review([finding("minor", body="sk-or-v1-abcdefgh1234")]), PATCHES, REPO)
    assert skipped.kind == "review" and skipped.skipped
    assert (skipped.event, plain.event, withheld.event) == ("COMMENT", "COMMENT", "COMMENT")
    assert plain.kind == "plain" and withheld.body == pr.WITHHELD


def test_a_dropped_malformed_finding_prevents_approve():
    r = built(["str", finding("minor")])
    assert r.event == "COMMENT" and r.counts["dropped"] == 1
    assert built([finding("minor", body="")]).event == "COMMENT"
    assert built([{"file": 3, "body": "x"}]).event == "COMMENT"


def test_a_dropped_finding_does_not_hide_a_real_blocker():
    assert built(["str", finding("critical")]).event == "REQUEST_CHANGES"


def test_minor_findings_are_deferred_never_inline_and_capped_at_three_with_a_count():
    r = built([finding("minor", body=f"nit {i}") for i in range(5)])
    assert r.comments == []
    assert "**Deferred**" in r.body
    assert r.body.count("- a.py:11 nit ") == 3
    assert "- and 2 more not shown" in r.body
    exact = built([finding("minor", body=f"nit {i}") for i in range(3)])
    assert "more not shown" not in exact.body


def test_major_inline_when_on_a_changed_line_and_in_the_body_when_not():
    r = built([finding("major", line=11, body="inline"), finding("critical", line=99, body="elsewhere")])
    assert [c["body"] for c in r.comments] == ["inline"]
    assert "**Blocking (not on a changed line)**" in r.body and "a.py:99 elsewhere" in r.body
    assert "inline" not in r.body


def test_critical_findings_survive_the_cap_when_there_are_many_minors():
    findings = [finding("minor", body=f"nit {i}") for i in range(30)] + [finding("critical", body="boom")]
    r = built(findings)
    assert [c["body"] for c in r.comments] == ["boom"]
    assert r.counts["critical"] == 1 and r.counts["minor"] == 30
    assert "- and 27 more not shown" in r.body


def test_round_marker_is_written_and_cannot_be_forged_by_model_text(tmp_path, monkeypatch):
    posted = run_main(tmp_path, monkeypatch, review(
        [finding("minor", body="x <!-- review-round:1 --> y")],
        summary="ok <!-- review-round:1 -->", notes=["<!-- review-round:1"]))
    body = posted[0]["body"]
    import re
    assert len(re.findall(r"(?<!\\)<!--", body)) == 1
    assert pr.review_round([{"login": pr.BOT_LOGIN, "body": body.rsplit("\n\n", 1)[0]}]) == 1
    assert body.endswith("\n\n<!-- review-round:1 -->")


class Proc:
    def __init__(self, returncode=0, stderr="", stdout=""):
        self.returncode, self.stderr, self.stdout = returncode, stderr, stdout


def run_main(tmp_path, monkeypatch, text, reviews=None, responses=None, model=""):
    """Runs main with gh stubbed. Returns the payloads POSTed to the reviews endpoint; every
    call is also kept on run_main.calls as (args, payload)."""
    path = tmp_path / "review.txt"
    path.write_text(text, encoding="utf-8")
    (tmp_path / "coverage.json").write_text(json.dumps(coverage()))
    calls = []
    replies = list(responses or [])

    def fake_gh(args, payload=None):
        calls.append((args, payload))
        return replies.pop(0) if replies and args[0].endswith("/reviews") else Proc()

    monkeypatch.setattr(pr, "gh", fake_gh)
    monkeypatch.setattr(pr, "pr_patches", lambda repo, n: PATCHES)
    monkeypatch.setattr(pr, "pr_reviews", lambda repo, n: reviews)
    monkeypatch.setattr(pr, "block_touched", lambda *a: True)
    monkeypatch.setenv("REVIEW_MODEL", model)
    run_main.rc = pr.main(["post_review.py", "7", REPO, "abcdef1234567", str(path)])
    run_main.calls = calls
    return [p for a, p in calls if a[0].endswith("/reviews")]


def bot_review(rid, state="COMMENTED", marker=True, login=pr.BOT_LOGIN):
    body = "text" + ("\n\n<!-- review-round:1 -->" if marker else "")
    return {"id": rid, "state": state, "login": login, "body": body}


def test_round_is_prior_marked_bot_reviews_plus_one():
    assert pr.review_round(None) == 1
    assert pr.review_round([]) == 1
    reviews = [bot_review(1), bot_review(2), bot_review(3, marker=False),
               bot_review(4, login="someone"), bot_review(5, login="github-actions")]
    assert pr.review_round(reviews) == 3


def test_the_round_number_reaches_the_posted_marker(tmp_path, monkeypatch):
    posted = run_main(tmp_path, monkeypatch, review([finding("major")]),
                      reviews=[bot_review(1), bot_review(2, login="someone")])
    assert posted[0]["body"].endswith("<!-- review-round:2 -->")
    assert posted[0]["event"] == "REQUEST_CHANGES"


def test_a_skipped_notice_carries_no_marker_and_posts_a_comment(tmp_path, monkeypatch):
    notice = json.dumps({"skipped": True, "summary": "No model.", "findings": []})
    posted = run_main(tmp_path, monkeypatch, notice, reviews=[bot_review(1, "CHANGES_REQUESTED")])
    assert "review-round" not in posted[0]["body"] and posted[0]["event"] == "COMMENT"
    assert not [a for a, _ in run_main.calls if a[0].endswith("/dismissals")]


def test_majors_block_in_every_round():
    r = built([finding("major", body="m")])
    assert r.event == "REQUEST_CHANGES" and [c["body"] for c in r.comments] == ["m"]


def test_blocks_posted_counts_marked_bot_blocks_even_when_dismissed():
    reviews = [bot_review(1, "CHANGES_REQUESTED"), bot_review(2, "DISMISSED"),
               bot_review(3, "COMMENTED"), bot_review(4, "CHANGES_REQUESTED", marker=False),
               bot_review(5, "CHANGES_REQUESTED", login="someone")]
    assert pr.blocks_posted(reviews) == 2
    assert pr.blocks_posted(None) == 0


def test_the_third_block_on_one_pr_is_posted_as_a_comment_with_the_findings_intact(tmp_path, monkeypatch):
    prior = [bot_review(1, "CHANGES_REQUESTED"), bot_review(2, "DISMISSED")]
    posted = run_main(tmp_path, monkeypatch, review([finding("major")]), reviews=prior)
    assert posted[0]["event"] == "COMMENT" and len(posted[0]["comments"]) == 1
    assert "already requested changes" in posted[0]["body"]
    assert posted[0]["body"].endswith("<!-- review-round:3 -->")


def test_the_second_block_still_requests_changes(tmp_path, monkeypatch):
    posted = run_main(tmp_path, monkeypatch, review([finding("major")]),
                      reviews=[bot_review(1, "CHANGES_REQUESTED")])
    assert posted[0]["event"] == "REQUEST_CHANGES"


REFUSED = Proc(1, stderr="gh: Unprocessable Entity (HTTP 422)")


def test_approve_refused_with_422_is_reposted_as_comment_that_says_so(tmp_path, monkeypatch, capsys):
    posted = run_main(tmp_path, monkeypatch, review([]), responses=[REFUSED, Proc()])
    assert [p["event"] for p in posted] == ["APPROVE", "COMMENT"]
    assert posted[1]["body"].startswith("**CLEAN**")
    assert "Posted as COMMENT because GitHub rejected APPROVE" in posted[1]["body"]
    assert posted[1]["body"].endswith("<!-- review-round:1 -->")
    assert "::warning::" in capsys.readouterr().out
    assert run_main.rc == 0


def test_only_an_http_422_counts_as_a_refusal(tmp_path, monkeypatch):
    posted = run_main(tmp_path, monkeypatch, review([]),
                      responses=[Proc(1, stderr="HTTP 500: upstream said 422 times")])
    assert len(posted) == 1 and run_main.rc == 1


def test_request_changes_refused_with_422_is_reposted_as_comment_keeping_the_inline_lines(tmp_path, monkeypatch):
    posted = run_main(tmp_path, monkeypatch, review([finding("major")]),
                      responses=[REFUSED, REFUSED, Proc()])
    assert [p["event"] for p in posted] == ["REQUEST_CHANGES", "REQUEST_CHANGES", "COMMENT"]
    assert posted[2]["body"].startswith("**BLOCKING**") and len(posted[2]["comments"]) == 1
    assert "Posted as COMMENT because GitHub rejected REQUEST_CHANGES" in posted[2]["body"]


def test_a_refused_line_is_folded_into_the_body_and_keeps_the_state(tmp_path, monkeypatch):
    posted = run_main(tmp_path, monkeypatch, review([finding("major", body="breaks")]),
                      responses=[REFUSED, Proc()])
    assert [p["event"] for p in posted] == ["REQUEST_CHANGES", "REQUEST_CHANGES"]
    assert posted[1]["comments"] == [] and "a.py:11 breaks" in posted[1]["body"]


def test_a_folded_body_keeps_the_round_marker_last_so_the_round_is_counted(tmp_path, monkeypatch):
    posted = run_main(tmp_path, monkeypatch, review([finding("major", body="breaks")]),
                      responses=[REFUSED, Proc()])
    folded = posted[1]["body"]
    assert folded.endswith("<!-- review-round:1 -->")
    assert folded.index("a.py:11 breaks") < folded.index("<!-- review-round")
    assert pr.review_round([{"login": pr.BOT_LOGIN, "body": folded}]) == 2


def test_state_and_line_both_refused_ends_as_a_comment_with_the_lines_folded(tmp_path, monkeypatch):
    posted = run_main(tmp_path, monkeypatch, review([finding("major", body="breaks")]),
                      responses=[REFUSED, REFUSED, REFUSED, Proc()])
    assert [p["event"] for p in posted] == ["REQUEST_CHANGES"] * 2 + ["COMMENT"] * 2
    assert posted[3]["comments"] == [] and "a.py:11 breaks" in posted[3]["body"]
    assert run_main.rc == 0


def test_a_non_422_failure_is_not_retried(tmp_path, monkeypatch):
    posted = run_main(tmp_path, monkeypatch, review([finding("minor")]),
                      responses=[Proc(1, stderr="HTTP 500")])
    assert len(posted) == 1 and run_main.rc == 1


def dismissals(calls):
    return [(a[0], p) for a, p in calls if a[0].endswith("/dismissals")]


def test_a_clean_run_dismisses_earlier_changes_requested_by_the_bot_only(tmp_path, monkeypatch):
    reviews = [bot_review(10, "CHANGES_REQUESTED"), bot_review(11, "COMMENTED"),
               bot_review(12, "CHANGES_REQUESTED", login="someone"), bot_review(13, "DISMISSED")]
    run_main(tmp_path, monkeypatch, review([]), reviews=reviews)
    sent = dismissals(run_main.calls)
    assert [path for path, _ in sent] == [f"repos/{REPO}/pulls/7/reviews/10/dismissals"]
    assert sent[0][1] == {"message": "Superseded by a clean re-review of abcdef1.", "event": "DISMISS"}


def test_a_review_with_findings_or_set_aside_items_dismisses_nothing(tmp_path, monkeypatch):
    stale = [bot_review(1), bot_review(2), bot_review(10, "CHANGES_REQUESTED")]
    for text in (review([finding("major")]), review([finding("minor")]), review(["str"]),
                 review([], notes=["unverified"])):
        run_main(tmp_path, monkeypatch, text, reviews=stale)
        assert dismissals(run_main.calls) == [], text


def test_a_review_of_the_current_head_is_never_dismissed(tmp_path, monkeypatch):
    head = dict(bot_review(10, "CHANGES_REQUESTED"), commit_id="abcdef1234567")
    older = dict(bot_review(11, "CHANGES_REQUESTED"), commit_id="1111111")
    run_main(tmp_path, monkeypatch, review([]), reviews=[head, older])
    assert [p for p, _ in dismissals(run_main.calls)] == [f"repos/{REPO}/pulls/7/reviews/11/dismissals"]


def test_dismissal_also_runs_when_the_state_fell_back_to_comment(tmp_path, monkeypatch):
    run_main(tmp_path, monkeypatch, review([]), reviews=[bot_review(10, "CHANGES_REQUESTED")],
             responses=[REFUSED, Proc()])
    assert len(dismissals(run_main.calls)) == 1


def test_the_dismissal_comes_after_the_new_review_posts(tmp_path, monkeypatch):
    run_main(tmp_path, monkeypatch, review([]), reviews=[bot_review(10, "CHANGES_REQUESTED")])
    order = [a[0] for a, _ in run_main.calls if a[0].endswith(("/reviews", "/dismissals"))]
    assert order == [f"repos/{REPO}/pulls/7/reviews", f"repos/{REPO}/pulls/7/reviews/10/dismissals"]


def test_no_dismissal_on_skipped_plain_withheld_or_blocking_runs(tmp_path, monkeypatch):
    stale = [bot_review(10, "CHANGES_REQUESTED")]
    texts = [json.dumps({"skipped": True, "summary": "No model.", "findings": []}),
             "prose, not json",
             review([finding("minor", body="sk-or-v1-abcdefgh1234")]),
             review([finding("major")]),
             review([finding("critical")])]
    for text in texts:
        run_main(tmp_path, monkeypatch, text, reviews=stale)
        assert dismissals(run_main.calls) == [], text[:40]


def test_no_dismissal_when_the_review_failed_to_post(tmp_path, monkeypatch):
    run_main(tmp_path, monkeypatch, review([]), reviews=[bot_review(10, "CHANGES_REQUESTED")],
             responses=[Proc(1, stderr="HTTP 500")])
    assert dismissals(run_main.calls) == []


def test_gh_error_text_cannot_start_a_workflow_command():
    assert pr.one_line("boom\n::add-mask::x\n  more") == "boom ::add-mask::x more"
    assert len(pr.one_line("x" * 1000)) == 300


def test_dismissal_failure_does_not_fail_the_job(tmp_path, monkeypatch, capsys):
    path = tmp_path / "review.txt"
    path.write_text(review([]), encoding="utf-8")
    (tmp_path / "coverage.json").write_text(json.dumps(coverage()))
    monkeypatch.setattr(pr, "gh", lambda args, payload=None: Proc(1, stderr="HTTP 403\n::stop-commands::x")
                        if args[0].endswith("/dismissals") else Proc())
    monkeypatch.setattr(pr, "pr_patches", lambda repo, n: PATCHES)
    monkeypatch.setattr(pr, "pr_reviews", lambda repo, n: [bot_review(10, "CHANGES_REQUESTED")])
    monkeypatch.setattr(pr, "block_touched", lambda *a: True)
    assert pr.main(["post_review.py", "7", REPO, "abcdef1234567", str(path)]) == 0
    assert "::warning::could not dismiss review 10: HTTP 403 ::stop-commands::x" in capsys.readouterr().out


def test_an_unreadable_review_list_means_round_one_and_no_dismissal(tmp_path, monkeypatch):
    posted = run_main(tmp_path, monkeypatch, review([finding("major")]), reviews=None)
    assert posted[0]["body"].endswith("<!-- review-round:1 -->")
    assert dismissals(run_main.calls) == []


def test_plain_output_is_an_issue_comment_without_any_review_call(tmp_path, monkeypatch):
    posted = run_main(tmp_path, monkeypatch, "prose", reviews=[bot_review(10, "CHANGES_REQUESTED")])
    assert posted == [] and run_main.calls[0][0][0].endswith("/issues/7/comments")
    assert dismissals(run_main.calls) == []


def test_a_finding_on_a_file_the_pr_did_not_change_is_dropped_and_blocks_nothing():
    r = built([{"file": "AGENTS.md", "body": "deleted", "severity": "major"}])
    assert r.event == "COMMENT" and r.counts["dropped"] == 1 and r.counts["major"] == 0


def test_without_a_pr_file_list_findings_on_any_file_are_kept():
    r = pr.build(review([finding("major")]), {}, REPO)
    assert r.event == "REQUEST_CHANGES" and r.counts["dropped"] == 0


def test_a_path_with_a_dot_slash_or_whitespace_still_matches_a_changed_file():
    for path in ("./a.py", " a.py "):
        r = built([finding("major", file=path)])
        assert r.event == "REQUEST_CHANGES" and r.counts["dropped"] == 0
        assert [c["path"] for c in r.comments] == ["a.py"]


def stub_files(monkeypatch, stdout, returncode=0):
    monkeypatch.setattr(pr.subprocess, "run", lambda *a, **k: Proc(returncode, stdout=stdout))


def test_pr_patches_keeps_a_renamed_files_old_name(monkeypatch):
    stub_files(monkeypatch, json.dumps({"filename": "new.py", "previous_filename": "old.py", "patch": "p"}))
    assert pr.pr_patches(REPO, 7) == {"new.py": "p", "old.py": "p"}


def test_pr_patches_returns_nothing_when_a_row_is_malformed(monkeypatch):
    stub_files(monkeypatch, json.dumps({"filename": "a.py", "patch": "p"}) + "\nnot json\n")
    assert pr.pr_patches(REPO, 7) == {}


def test_a_token_split_by_a_tag_is_withheld_after_sanitizing():
    for f in (finding("minor", body="leak sk-<i>or-v1-abcdefgh1234"), finding("major", body="leak sk-<i>or-v1-abcdefgh1234")):
        r = built([f])
        assert r.kind == "plain" and r.body == pr.WITHHELD


def stub_api_lines(monkeypatch, commented, changed):
    monkeypatch.setattr(pr, "api_lines", lambda repo, path, jq: commented if "comments" in path else changed)


def test_a_block_is_dismissed_only_when_the_push_touched_a_file_it_commented_on(monkeypatch):
    rev = {"id": 10, "commit_id": "old"}
    stub_api_lines(monkeypatch, {"a.py", "b.py"}, {"b.py", "c.py"})
    assert pr.block_touched(REPO, 7, rev, "head")
    stub_api_lines(monkeypatch, {"a.py"}, {"c.py"})
    assert not pr.block_touched(REPO, 7, rev, "head")


def test_a_block_with_no_inline_comment_or_an_unreadable_compare_stands(monkeypatch):
    rev = {"id": 10, "commit_id": "old"}
    stub_api_lines(monkeypatch, set(), {"a.py"})
    assert not pr.block_touched(REPO, 7, rev, "head")
    stub_api_lines(monkeypatch, {"a.py"}, set())
    assert not pr.block_touched(REPO, 7, rev, "head")


def test_an_untouched_block_is_not_dismissed_by_a_clean_review(monkeypatch):
    calls = []
    monkeypatch.setattr(pr, "gh", lambda args, payload=None: calls.append(args) or Proc())
    monkeypatch.setattr(pr, "block_touched", lambda *a: False)
    pr.dismiss_stale(REPO, 7, "abcdef1234567", [bot_review(10, "CHANGES_REQUESTED")])
    assert calls == []


def test_api_lines_keeps_names_with_spaces_and_warns_on_failure(monkeypatch, capsys):
    monkeypatch.setattr(pr, "gh", lambda args, payload=None: Proc(0, stdout="my file.js\nb.py\n"))
    assert pr.api_lines(REPO, "compare/a...b", ".x") == {"my file.js", "b.py"}
    monkeypatch.setattr(pr, "gh", lambda args, payload=None: Proc(1, stderr="HTTP 404"))
    assert pr.api_lines(REPO, "compare/a...b", ".x") == set()
    assert "::warning::could not read compare" in capsys.readouterr().out


def test_a_token_split_by_a_zero_width_character_is_withheld():
    for zw in "​‌‍‎‏⁠﻿­":
        r = pr.build(review([finding("minor", body=f"sk-{zw}or-v1-abcdefgh1234")]), PATCHES, REPO)
        assert r.kind == "plain" and r.body == pr.WITHHELD
        raw = pr.build(f"sk-{zw}or-v1-abcdefgh1234", PATCHES, REPO)
        assert raw.body == pr.WITHHELD


def test_sanitize_strips_zero_width_characters():
    assert pr.sanitize("a​b﻿c­d", REPO, 50) == "abcd"


def test_ordinary_words_that_contain_the_token_prefix_are_not_withheld():
    for text in ("the risk-or-reward trade", "disk-or-memory pressure", "Bearer token-authentication"):
        r = pr.build(review([finding("major", body=text)]), PATCHES, REPO)
        assert r.kind == "review" and r.event == "REQUEST_CHANGES"


def test_real_looking_tokens_are_still_withheld():
    for text in ("key sk-or-v1-abcdefgh1234", "Bearer abcdefghij0123456789xyz"):
        r = pr.build(review([finding("minor", body=text)]), PATCHES, REPO)
        assert r.body == pr.WITHHELD


def test_withholding_prints_a_warning(capsys):
    pr.build("sk-or-v1-abcdefgh1234", PATCHES, REPO)
    assert "::warning::" in capsys.readouterr().out


def test_other_invisible_characters_and_whitespace_cannot_hide_a_token():
    gh = "ghp_" + "A" * 36
    for text in ("sk\u034f-or-v1-abcdefgh1234", "gh\u3164p_" + "A" * 36, "sk-or\ufe0f-v1-abcdefgh1234",
                 "sk\U000e002d-or-v1-abcdefgh1234", "Xsk-or-v1-abcdefgh1234", "sk-or-v1-ab.cd.ef.gh12.34",
                 gh[:10] + " " + gh[10:], "\uff53k-or-v1-abcdefgh1234"):
        assert pr.build(review([finding("minor", body=text)]), PATCHES, REPO).body == pr.WITHHELD, text


def coverage(**extra):
    return {"mode": "full", "since": "", "shown": 3, "total": 3, "omitted": [], **extra}


def read_cov(cov, tmp_path):
    (tmp_path / "coverage.json").write_text(json.dumps(cov))
    return pr.read_coverage(str(tmp_path / "review.txt"))


def covered(findings, cov, tmp_path, **extra):
    return pr.build(review(findings, **extra), PATCHES, REPO, read_cov(cov, tmp_path))


def test_coverage_of_all_files_is_one_line_and_still_approves_a_clean_review(tmp_path):
    r = covered([], coverage(), tmp_path)
    assert r.event == "APPROVE"
    assert "**Coverage** reviewed 3 of 3 changed files" in r.body
    assert "Not shown" not in r.body


def test_partial_coverage_prevents_approve_and_lists_omitted_files(tmp_path):
    r = covered([], coverage(shown=1, omitted=["docs/a.md", "docs/b.md"]), tmp_path)
    assert r.event == "COMMENT"
    assert "reviewed 1 of 3 changed files" in r.body
    assert "Not shown: docs/a.md, docs/b.md" in r.body


def test_partial_coverage_lists_five_names_and_counts_the_rest(tmp_path):
    r = covered([], coverage(shown=0, total=9, omitted=[f"f{i}.md" for i in range(9)]), tmp_path)
    assert "f4.md" in r.body and "f5.md" not in r.body and "and 4 more" in r.body


def test_the_rest_count_comes_from_the_totals_when_the_file_names_only_some(tmp_path):
    r = covered([], coverage(shown=10, total=2010, omitted=[f"f{i}.md" for i in range(20)]), tmp_path)
    assert r.event == "COMMENT" and "f4.md" in r.body and "and 1995 more" in r.body


def test_partial_coverage_still_requests_changes_for_a_major(tmp_path):
    r = covered([finding("major")], coverage(shown=1), tmp_path)
    assert r.event == "REQUEST_CHANGES"


def test_an_incremental_review_names_the_commit_it_started_from(tmp_path):
    r = covered([], coverage(mode="incremental", since="abc1234"), tmp_path)
    assert "reviewed 3 of 3 changed files since abc1234" in r.body
    assert r.event == "APPROVE"


def test_coverage_file_names_are_sanitized_like_findings(tmp_path):
    r = covered([], coverage(shown=0, omitted=["see https://evil.example <b>x</b>.md", "a[b](c)#1.md"]), tmp_path)
    assert "evil.example" not in r.body and "<b>" not in r.body
    assert "a\\[b\\]" in r.body and "\\#1" in r.body


def test_a_since_that_is_not_a_short_sha_is_dropped(tmp_path):
    r = covered([], coverage(mode="incremental", since="[x](http://evil.example)"), tmp_path)
    assert "evil.example" not in r.body and "since" not in r.body.split("**Coverage**")[1]


def test_a_missing_coverage_file_never_approves(tmp_path):
    assert pr.read_coverage(str(tmp_path / "review.txt")) == pr.UNKNOWN_COVERAGE
    r = pr.build(review([]), PATCHES, REPO, pr.read_coverage(str(tmp_path / "review.txt")))
    assert r.event == "COMMENT" and "**Coverage** unknown" in r.body


def test_no_coverage_argument_still_approves_a_clean_review():
    r = pr.build(review([]), PATCHES, REPO, None)
    assert r.event == "APPROVE" and "Coverage" not in r.body


def test_a_malformed_coverage_file_never_approves(tmp_path):
    review_file = tmp_path / "review.txt"
    review_file.write_text("x")
    cov = tmp_path / "coverage.json"
    for bad in ["not json", "[]", '{"mode": "full"}', json.dumps(coverage(shown="3")),
                json.dumps(coverage(shown=True)), json.dumps(coverage(shown=4, total=3)),
                json.dumps(coverage(shown=-1)), json.dumps(coverage(omitted="a.md")),
                json.dumps(coverage(omitted=[3])), json.dumps(coverage(mode="other")),
                json.dumps(coverage(total=10**9, shown=1)),
                json.dumps(coverage(shown=2, total=3, omitted=["a.md", "b.md"]))]:
        cov.write_text(bad)
        assert pr.read_coverage(str(review_file)) == pr.UNKNOWN_COVERAGE, bad
        r = pr.build(review([]), PATCHES, REPO, pr.read_coverage(str(review_file)))
        assert r.event == "COMMENT" and "**Coverage** unknown" in r.body, bad
    cov.write_text(json.dumps(coverage()))
    assert pr.read_coverage(str(review_file))["total"] == 3


def test_an_oversized_coverage_file_never_approves(tmp_path):
    review_file = tmp_path / "review.txt"
    review_file.write_text("x")
    (tmp_path / "coverage.json").write_text(
        json.dumps(coverage(shown=0, total=2010, omitted=["a" * 6000] * 20)))
    assert (tmp_path / "coverage.json").stat().st_size > pr.MAX_COVERAGE_BYTES
    assert pr.read_coverage(str(review_file)) == pr.UNKNOWN_COVERAGE


def test_a_review_of_zero_files_does_not_approve(tmp_path):
    r = covered([], coverage(shown=0, total=0), tmp_path)
    assert r.event == "COMMENT"


def test_a_skipped_notice_prints_no_coverage(tmp_path):
    text = json.dumps({"skipped": True, "summary": "No model.", "findings": []})
    r = pr.build(text, {}, REPO, read_cov(coverage(shown=0), tmp_path))
    assert r.skipped and "Coverage" not in r.body


def test_a_partial_review_is_marked_so_the_next_run_reviews_the_whole_pr(tmp_path, monkeypatch):
    run_main(tmp_path, monkeypatch, review([]))
    assert "coverage:partial" not in run_main.calls[-1][1]["body"]
    (tmp_path / "coverage.json").write_text(json.dumps(coverage(shown=1)))
    path = tmp_path / "review.txt"
    monkeypatch.setattr(pr, "pr_patches", lambda repo, n: PATCHES)
    monkeypatch.setattr(pr, "pr_reviews", lambda repo, n: [])
    posted = []
    monkeypatch.setattr(pr, "gh", lambda args, payload=None: posted.append(payload) or Proc())
    assert pr.main(["post_review.py", "1", REPO, "a" * 40, str(path)]) == 0
    body = posted[-1]["body"]
    assert body.rstrip().endswith("<!-- review-round:1 -->") and "<!-- coverage:partial -->" in body
