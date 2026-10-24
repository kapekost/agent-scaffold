#!/usr/bin/env python3
"""Turn the reviewer's output into one GitHub review, or one plain comment.

The reviewer holds no token and its output is derived from attacker-controlled PR
text, so this script treats it as untrusted: it parses, validates, caps and escapes
it before anything is posted. It runs from the default branch, never from the PR.

    python3 post_review.py <pr> <owner/repo> <head-sha> <review-file>
    python3 post_review.py --check-verdict <review-file>

The second form only reports, through its exit status, whether the file holds a verdict
(0) or not (1). It makes no network call and runs no process.

Output that is not the expected JSON is posted inside a code block, truncated.

The script, not the model, chooses the review state. Critical and major findings request
changes, and only a review with no findings, notes or set-aside items approves; anything else
comments. GitHub may refuse a state, in which case the body is posted as a comment with a
line saying so.
"""
import json
import os
import re
import subprocess
import sys
import unicodedata
from typing import NamedTuple

MAX_FINDINGS = 20
MAX_BODY = 400
MAX_SUMMARY = 200
MAX_PLAIN = 3000
MAX_INPUT = 50_000
MAX_DEFERRED = 3
MAX_OMITTED = 5
MAX_FILES = 100_000
BLOCK_CAP = 2
BOT_LOGIN = "github-actions[bot]"
SEVERITIES = ("critical", "major", "minor")
ROUND_MARKER = re.compile(r"<!-- review-round:\d+ -->\s*$")

BEARER = re.compile(r"Bearer (?:[A-Za-z0-9._~+/=]{20,}|(?=[A-Za-z0-9._-]*\d)[A-Za-z0-9._-]{20,})")
TOKEN = re.compile(r"sk-or-v\d+-|sk-or-[A-Za-z0-9_-]{20,}|gh[pousr]_[A-Za-z0-9]{20,}|github_pat_")
WITHHELD = ("**Automated review withheld.** The output matched a secret pattern "
            "and was not posted. See the Actions log for the run.")
FENCE = "`" * 3


def visible(text):
    """Text with the characters that render as nothing removed and compatibility forms folded,
    so a token cannot be hidden by splitting it. Whitespace is kept."""
    text = unicodedata.normalize("NFKC", text)
    return "".join(c for c in text if c.isspace() or c not in "\u115f\u1160\u3164\uffa0\u2800"
                   and unicodedata.category(c) not in ("Cc", "Cf", "Mn", "Me"))


def leaks(text):
    """Whether text holds a token, even one split by invisible characters or whitespace."""
    text = visible(text)
    if BEARER.search(text) or TOKEN.search(text) or TOKEN.search(re.sub(r"\s+", "", text)):
        print("::warning::the review output matched a secret pattern and was withheld")
        return True
    return False


def sanitize(text, repo, limit):
    """URLs and HTML are removed, @mentions are broken, and brackets, angle brackets,
    ampersands, # and backslashes are escaped, so nothing renders as a link, image,
    mention or cross-reference. Runs of three or more backticks or tildes are defused so a body
    cannot open a code block."""
    text = str(text)[:limit * 4]
    text = re.sub(r"<[^>]{0,200}>", "", text)
    text = visible(text)
    text = re.sub(r"\b\w+://\S+|\bwww\.\S+", "[link removed]", text, flags=re.I)
    text = " ".join(text.split())[:limit]
    text = re.sub(r"@(?=\w)", "@​", text)
    text = re.sub(r"`{3,}|~{3,}", "'''", text)
    return re.sub(r"([\\\[\]<>&#])", r"\\\1", text)


def extract_json(text):
    """The verdict, or None. The output is either one JSON object, or prose around exactly
    one code fence holding one JSON object. A second fence, an unclosed fence, a second
    object, or a verdict nested in a longer object makes the output unstructured, so text a
    misled model quotes from the PR cannot replace the real answer."""
    text = text[:MAX_INPUT].lstrip("\ufeff").strip()
    parts = text.split(FENCE)
    if len(parts) == 3:
        text = parts[1].strip().removeprefix("json")
    elif len(parts) != 1:
        return None
    try:
        obj = json.loads(text)
    except (ValueError, RecursionError):
        return None
    return obj if is_verdict(obj) else None


def is_verdict(obj):
    """A findings list plus a real summary. An echo of the prompt's example shape has a
    placeholder summary such as "<one line, max 150 chars>", "..." or "-", and is not a
    verdict. A real summary has at least one word character."""
    if not isinstance(obj, dict) or not isinstance(obj.get("findings"), list):
        return False
    summary = obj.get("summary")
    return (isinstance(summary, str) and re.search(r"\w", summary) is not None
            and not summary.lstrip().startswith("<"))


def plain_comment(text):
    """Unstructured output goes inside a code block, where nothing renders or notifies."""
    text = text[:MAX_PLAIN].replace(FENCE, "'''")
    return f"**Automated review output (not structured, shown as text)**\n\n{FENCE}text\n{text}\n{FENCE}"


def commentable_lines(patch):
    """New-side line numbers that a review comment may anchor to (RIGHT side)."""
    lines = set()
    new = 0
    for row in (patch or "").split("\n"):
        hunk = re.match(r"@@ -\d+(?:,\d+)? \+(\d+)(?:,\d+)? @@", row)
        if hunk:
            new = int(hunk.group(1))
            continue
        if row.startswith("-") or row.startswith("\\"):
            continue
        if new:
            lines.add(new)
            new += 1
    return lines


def is_line(value):
    return isinstance(value, int) and not isinstance(value, bool)


class Built(NamedTuple):
    kind: str          # "review" is posted as a review, "plain" as an issue comment
    body: str
    comments: list
    event: str         # REQUEST_CHANGES, APPROVE or COMMENT
    counts: dict       # critical, major (still counted), minor, dropped (malformed)
    skipped: bool


def severity_of(finding):
    """A valid "severity" wins. Without one, "blocking": true is major and anything else is
    minor. A severity outside the three words is treated as absent."""
    sev = finding.get("severity")
    if isinstance(sev, str) and sev.strip().lower() in SEVERITIES:
        return sev.strip().lower()
    return "major" if finding.get("blocking") is True else "minor"


def decide_event(counts, kind, has_notes):
    """The review state. kind is "review" only for a structured, non-skipped review; a skipped
    notice, plain output and a withheld secret never approve. Approval needs a strictly clean
    review: no finding of any severity, none dropped, and no
    note about something the reviewer could not verify."""
    if kind != "review":
        return "COMMENT"
    if counts["critical"] or counts["major"]:
        return "REQUEST_CHANGES"
    if counts["minor"] or counts["dropped"] or has_notes:
        return "COMMENT"
    return "APPROVE"


def plain_result(body):
    return Built("plain", body, [], "COMMENT",
                 {"critical": 0, "major": 0, "minor": 0, "dropped": 0}, False)


def count(value):
    return isinstance(value, int) and not isinstance(value, bool) and 0 <= value <= MAX_FILES


MAX_COVERAGE_BYTES = 100_000
UNKNOWN_COVERAGE = {"unknown": True}


def read_coverage(review_path):
    """What scripts/review_input.py recorded next to the review file. The workflow always runs
    it, so a file that is missing, oversized, malformed or inconsistent is UNKNOWN_COVERAGE:
    it comes from an artifact, so every value is checked, and a record that cannot be trusted
    never lets a review approve."""
    try:
        with open(os.path.join(os.path.dirname(review_path), "coverage.json"), encoding="utf-8") as fh:
            raw = fh.read(MAX_COVERAGE_BYTES + 1)
    except (OSError, ValueError):
        return UNKNOWN_COVERAGE
    try:
        data = json.loads(raw) if len(raw) <= MAX_COVERAGE_BYTES else None
    except ValueError:
        data = None
    if not isinstance(data, dict) or data.get("mode") not in ("full", "incremental"):
        return UNKNOWN_COVERAGE
    shown, total, omitted = data.get("shown"), data.get("total"), data.get("omitted")
    if not (count(shown) and count(total) and shown <= total):
        return UNKNOWN_COVERAGE
    if not (isinstance(omitted, list) and all(isinstance(o, str) for o in omitted)
            and len(omitted) <= total - shown):
        return UNKNOWN_COVERAGE
    since = data.get("since")
    return {"incremental": data["mode"] == "incremental",
            "since": since if isinstance(since, str) and re.fullmatch(r"[0-9a-f]{7}", since) else "",
            "shown": shown, "total": total, "omitted": omitted}


def is_partial(cov):
    """Whether the reviewer saw less than the whole change, or nobody can say."""
    return bool(cov) and (cov.get("unknown", False) or cov["shown"] < cov["total"] or cov["total"] == 0)


def coverage_lines(cov, repo):
    if cov.get("unknown"):
        return ["", "**Coverage** unknown: the coverage record was missing or unreadable."]
    line = f"**Coverage** reviewed {cov['shown']} of {cov['total']} changed files"
    if cov["incremental"] and cov["since"]:
        line += f" since {cov['since']}"
    lines = ["", line]
    names = [sanitize(o, repo, 120) for o in cov["omitted"][:MAX_OMITTED]]
    if cov["shown"] < cov["total"] and names:
        rest = cov["total"] - cov["shown"] - len(names)
        lines.append("Not shown: " + ", ".join(names) + (f" and {rest} more" if rest else ""))
    return lines


def build(text, patches, repo, coverage=None):
    """Turns the reviewer's output into a Built. coverage is read_coverage's result: a review that
    was shown only part of the diff never approves."""
    if leaks(text):
        return plain_result(WITHHELD)
    data = extract_json(text)
    if data is None:
        return plain_result(plain_comment(text) if text.strip() else "The reviewer produced no output.")
    if leaks(json.dumps(data, ensure_ascii=False)):
        return plain_result(WITHHELD)

    findings = data.get("findings")
    if not isinstance(findings, list):
        findings = []
    valid = []
    dropped = 0
    for f in findings:
        if not isinstance(f, dict):
            dropped += 1
            continue
        path = f.get("file")
        body = sanitize(f.get("body", ""), repo, MAX_BODY)
        # The reviewer's checkout is stripped, so it can mistake that for changes to files the
        # PR never touched. An empty patches means the file list could not be fetched.
        if isinstance(path, str):
            path = path.strip().removeprefix("./")
        if not body or not isinstance(path, str) or (patches and path not in patches):
            dropped += 1
            continue
        valid.append((SEVERITIES.index(severity_of(f)), path, f.get("line"), body))
    # Sorted before the cap, so a pile of minor findings cannot push a critical one out.
    valid.sort(key=lambda row: row[0])

    counts = {"critical": 0, "major": 0, "minor": 0, "dropped": dropped}
    for rank, *_ in valid:
        counts[SEVERITIES[rank]] += 1
    blocking_lines, minor_lines, comments = [], [], []
    for rank, path, line, body in valid[:MAX_FINDINGS]:
        sev = SEVERITIES[rank]
        shown = sanitize(path, repo, 120)
        where = f"{shown}:{line}" if is_line(line) else shown
        if sev == "minor":
            minor_lines.append(f"- {where} {body}")
        elif is_line(line) and path in patches and line in commentable_lines(patches[path]):
            comments.append({"path": path, "line": line, "side": "RIGHT", "body": body})
        else:
            blocking_lines.append(f"- {where} {body}")

    skipped = data.get("skipped") is True and not findings
    kind = "skipped" if skipped else "review"
    notes = data.get("notes")
    clean_notes = ([sanitize(n, repo, MAX_BODY) for n in notes[:5] if isinstance(n, str)]
                   if isinstance(notes, list) else [])
    limits = data.get("limits")
    clean_limits = ([sanitize(n, repo, MAX_BODY) for n in limits[:5] if isinstance(n, str)]
                    if isinstance(limits, list) else [])
    event = decide_event(counts, kind, bool(notes) or bool(limits) or is_partial(coverage))

    summary = sanitize(data.get("summary", ""), repo, MAX_SUMMARY)
    summary = re.sub(r"^(CLEAN|BLOCKING)\b[\s:.\-]*", "", summary)
    if skipped:
        head = f"**Automated review skipped.** {summary}".strip()
    elif event == "REQUEST_CHANGES":
        head = f"**BLOCKING** {summary}".strip()
    else:
        head = f"**CLEAN** {summary}".strip()
    parts = [head]
    if blocking_lines:
        parts += ["", "**Blocking (not on a changed line)**"] + blocking_lines
    if minor_lines:
        shown_lines = minor_lines[:MAX_DEFERRED]
        parts += ["", "**Deferred**"] + shown_lines
        if counts["minor"] > len(shown_lines):
            parts.append(f"- and {counts['minor'] - len(shown_lines)} more not shown")
    if clean_notes:
        parts += ["", "**Notes**"] + [f"- {n}" for n in clean_notes]
    if coverage and not skipped:
        parts += coverage_lines(coverage, repo)
    if clean_limits:
        parts += ["", "<details><summary>Review limits (sandbox, not the PR)</summary>", ""]
        parts += [f"- {n}" for n in clean_limits] + ["", "</details>"]
    posted = "\n".join(parts + [c["body"] for c in comments])
    # Sanitizing removes tags and joins what they split, so a token can only appear here.
    if leaks(posted):
        return plain_result(WITHHELD)
    return Built("review", "\n".join(parts), comments, event, counts, skipped)


def gh(args, payload=None):
    cmd = ["gh", "api"] + args
    if payload is not None:
        cmd += ["--input", "-"]
    return subprocess.run(cmd, input=json.dumps(payload) if payload is not None else None,
                          capture_output=True, text=True)


def pr_patches(repo, pr):
    out = subprocess.run(["gh", "api", "--paginate", f"repos/{repo}/pulls/{pr}/files",
                          "--jq", ".[] | {filename, previous_filename, patch}"],
                         capture_output=True, text=True)
    patches = {}
    if out.returncode != 0:
        return patches
    for row in out.stdout.splitlines():
        try:
            obj = json.loads(row)
            for name in (obj["filename"], obj.get("previous_filename")):
                if name:
                    patches[name] = obj.get("patch") or ""
        except (ValueError, KeyError, AttributeError):
            return {}
    return patches


def check_verdict(path):
    try:
        with open(path, encoding="utf-8", errors="replace") as fh:
            text = fh.read(MAX_INPUT)
    except OSError as exc:
        print(f"cannot read {path}: {exc}", file=sys.stderr)
        return 1
    return 0 if extract_json(text) is not None else 1


def signed(body, model, repo):
    """Names the model that produced the review; a skipped run has none."""
    return f"{body}\n\n_Reviewed by `{sanitize(model, repo, 80)}`_" if model else body


def pr_reviews(repo, pr):
    """The PR's reviews as dicts with id, state, commit_id, login and body, or None when GitHub cannot be
    asked. The login is an API field, not review text, so model output cannot set it."""
    out = subprocess.run(["gh", "api", "--paginate", f"repos/{repo}/pulls/{pr}/reviews",
                          "--jq", ".[] | {id, state, commit_id, login: .user.login, body}"],
                         capture_output=True, text=True)
    if out.returncode != 0:
        print(f"could not list reviews: {out.stderr.strip()}", file=sys.stderr)
        return None
    reviews = []
    for row in out.stdout.splitlines():
        try:
            obj = json.loads(row)
        except ValueError:
            continue
        if isinstance(obj, dict):
            reviews.append(obj)
    return reviews


def review_round(reviews):
    """This review's round: the bot's earlier marked reviews plus one. Skipped notices and
    plain output carry no marker, so a provider failure does not use up a round."""
    prior = [r for r in reviews or []
             if r.get("login") == BOT_LOGIN and ROUND_MARKER.search(str(r.get("body") or ""))]
    return len(prior) + 1


def blocks_posted(reviews):
    """How many REQUEST_CHANGES reviews the bot has posted on this PR. A dismissed one still
    counts, so a push-and-dismiss cycle cannot reset it. A dismissed approval would count too;
    approvals are off, so that cannot happen yet."""
    return len([r for r in reviews or []
                if r.get("login") == BOT_LOGIN and r.get("state") in ("CHANGES_REQUESTED", "DISMISSED")
                and ROUND_MARKER.search(str(r.get("body") or ""))])


def refused(r):
    return r.returncode != 0 and "HTTP 422" in (r.stderr + r.stdout)


def one_line(text, limit=300):
    """Gh error text on one line, so a line of it cannot start a workflow command."""
    return " ".join(str(text).split())[:limit]


def with_note(body, note):
    """Adds a paragraph before the round marker, which must stay the last line or the round
    is not counted."""
    marker = ROUND_MARKER.search(body)
    if not marker:
        return f"{body}\n\n{note}"
    return f"{body[:marker.start()].rstrip()}\n\n{note}\n\n{marker.group().strip()}"


def post_review(repo, pr, head_sha, body, comments, event):
    """Posts the review and returns (result, event actually posted). GitHub answers 422 both
    for a state it refuses (APPROVE while Actions may not approve, REQUEST_CHANGES on the
    bot's own PR) and for an inline line it cannot place, so a refusal tries the lesser
    change first: the same state with the comments folded into the body, then COMMENT with
    the comments, then COMMENT with them folded. A review that ends in a different state says
    so in its body and in a workflow warning."""
    url = f"repos/{repo}/pulls/{pr}/reviews"

    def attempt(ev, cs, text):
        return gh([url, "-X", "POST"],
                  {"commit_id": head_sha, "event": ev, "body": text, "comments": cs})

    folded_body = body
    if comments:
        folded = [f"- {sanitize(c['path'], repo, 120)}:{c['line']} {c['body']}" for c in comments]
        folded_body = with_note(body, "**Blocking**\n" + "\n".join(folded))
    refusal = f"_Posted as COMMENT because GitHub rejected {event} (HTTP 422)._"
    tries = [(event, comments, body)]
    if comments:
        tries.append((event, [], folded_body))
    if event != "COMMENT":
        tries.append(("COMMENT", comments, with_note(body, refusal)))
        if comments:
            tries.append(("COMMENT", [], with_note(folded_body, refusal)))
    for i, (ev, cs, text) in enumerate(tries):
        r = attempt(ev, cs, text)
        if not refused(r) or i == len(tries) - 1:
            if r.returncode == 0 and ev != event:
                print(f"::warning::GitHub rejected {event} (HTTP 422), the review was posted as {ev}")
            return r, ev
        print(f"GitHub refused {ev} ({len(cs)} inline), trying a lesser form: "
              f"{(r.stderr + r.stdout).strip()}", file=sys.stderr)


def api_lines(repo, path, jq):
    r = gh([f"repos/{repo}/{path}", "--paginate", "--jq", jq])
    if r.returncode != 0:
        print(f"::warning::could not read {path.split('/')[0]} for a dismissal check: {one_line(r.stderr)}")
        return set()
    return set(r.stdout.splitlines())


def block_touched(repo, pr, rev, head_sha):
    """True when the push since the blocked commit changed a file the block commented on. A
    clean incremental review only covers that push, so it says nothing about a block whose
    files were not touched. A block with no inline comment, a failed API call or a compare against a
    force-pushed-away commit cannot be tied to a file and stands: a stale block is cheap, a
    wrong dismissal is not. Touching a commented file with a trivial edit still counts."""
    commented = api_lines(repo, f"pulls/{pr}/reviews/{rev.get('id')}/comments", ".[].path")
    changed = api_lines(repo, f"compare/{rev.get('commit_id')}...{head_sha}", ".files[] | .filename, .previous_filename // empty")
    return bool(commented & changed)


def dismiss_stale(repo, pr, head_sha, reviews):
    """Dismisses the bot's CHANGES_REQUESTED reviews of earlier commits whose files the new
    commits touched. A review of the current head stands. Failure is a warning, never fatal."""
    short = re.sub(r"[^0-9a-fA-F]", "", head_sha)[:7]
    for rev in reviews or []:
        if (rev.get("login") != BOT_LOGIN or rev.get("state") != "CHANGES_REQUESTED"
                or rev.get("commit_id") == head_sha
                or not block_touched(repo, pr, rev, head_sha)):
            continue
        r = gh([f"repos/{repo}/pulls/{pr}/reviews/{rev.get('id')}/dismissals", "-X", "PUT"],
               {"message": f"Superseded by a clean re-review of {short}.", "event": "DISMISS"})
        if r.returncode != 0:
            print(f"::warning::could not dismiss review {rev.get('id')}: {one_line(r.stderr)}")


def main(argv):
    if len(argv) == 3 and argv[1] == "--check-verdict":
        return check_verdict(argv[2])
    if len(argv) != 5:
        print(__doc__, file=sys.stderr)
        return 2
    pr, repo, head_sha, path = argv[1:]
    with open(path, encoding="utf-8", errors="replace") as fh:
        text = fh.read(200_000)

    structured = extract_json(text) is not None
    patches = pr_patches(repo, pr) if structured else {}
    reviews = pr_reviews(repo, pr) if structured else None
    round_n = review_round(reviews)
    coverage = read_coverage(path)
    built = build(text, patches, repo, coverage)
    body = built.body
    event = built.event
    if built.kind == "plain":
        r = gh([f"repos/{repo}/issues/{pr}/comments", "-X", "POST"], {"body": body})
        print("posted plain comment" if r.returncode == 0 else r.stderr, file=sys.stderr)
        return r.returncode

    body = signed(body, os.environ.get("REVIEW_MODEL", ""), repo)
    if event == "REQUEST_CHANGES" and blocks_posted(reviews) >= BLOCK_CAP:
        event = "COMMENT"
        body = with_note(body, f"_Posted as COMMENT: the bot has already requested changes {BLOCK_CAP} times "
                               "on this PR. The findings are unresolved; no further changes-requested review is posted._")
    if not built.skipped:
        if is_partial(coverage):
            body += "\n\n<!-- coverage:partial -->"
        body += f"\n\n<!-- review-round:{round_n} -->"
    r, event = post_review(repo, pr, head_sha, body, built.comments, event)
    print(f"posted review as {event} (round {round_n})" if r.returncode == 0 else r.stderr,
          file=sys.stderr)
    if r.returncode == 0 and built.event == "APPROVE":
        dismiss_stale(repo, pr, head_sha, reviews)
    return r.returncode


if __name__ == "__main__":
    sys.exit(main(sys.argv))
