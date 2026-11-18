"""The Git extension's rules (extensions/git domain/sync.py): git's blob hash, what syncs (.gitignore and the app's
own exclusions), the three-way merge, a pull's plan, a push's secrets, the words and the Source Control page's
groups. Made-up data only."""

from __future__ import annotations

import hashlib

import pytest

from swissarmybench_git.domain import sync as rules


def test_the_blob_hash_is_gits_own() -> None:
    # `git hash-object` of "hello\n" (a well-known value).
    assert rules.blob_sha(b"hello\n") == "ce013625030ba8dba906f756967f9e9ca394464a"
    assert rules.blob_sha(b"") == hashlib.sha1(b"blob 0\0", usedforsecurity=False).hexdigest()


def test_repositories_branches_and_paths_are_checked() -> None:
    assert rules.check_repository("made-up-team/meta-store") == "made-up-team/meta-store"
    assert (
        rules.check_repository("https://github.com/made-up-team/meta-store.git") == "made-up-team/meta-store"
    )
    for bad in ("", "nobody", "a/b/c", "../x", "made up/team"):
        with pytest.raises(rules.SyncError):
            rules.check_repository(bad)
    assert rules.check_branch(None) is None and rules.check_branch("feature/q3") == "feature/q3"
    with pytest.raises(rules.SyncError):
        rules.check_branch("../main")
    assert rules.safe_path("connections/Warehouse.blade.py")
    for bad in ("../x", "/etc/passwd", "a//b", "C:/x", ".git/config", "a/.GIT/x", "a\\b"):
        assert not rules.safe_path(bad), bad


def test_gitignore_patterns_and_the_apps_own_exclusions() -> None:
    ignore = rules.Ignore(
        [
            ("", "# comment\n*.log\n/build/\n!keep.log\nnotes/**/draft.md\n"),
            ("Close", ".sab/data/\nsecret.txt\n"),
        ]
    )
    assert ignore.ignored("a.log") and not ignore.ignored("keep.log") and ignore.ignored("deep/x.log")
    assert ignore.ignored("build/out.csv") and not ignore.ignored("src/build/out.csv")
    assert ignore.ignored("notes/a/b/draft.md") and ignore.ignored("notes/draft.md")
    assert ignore.ignored("Close/secret.txt") and not ignore.ignored("secret.txt")
    # Always out, whatever .gitignore says: local/ at the top, .sab/data/ anywhere, .git/, a conflict's theirs.
    bare = rules.Ignore([("", "!local/\n")])
    assert bare.ignored("local/variables.toml") and not bare.ignored("teams/local/x.py")
    assert bare.ignored("Close/.sab/data/orders.parquet") and bare.ignored(".git/HEAD")
    assert bare.ignored("connections/Warehouse.blade.py.theirs")
    assert not bare.ignored("Close/.sab/project.json")


def test_the_three_way_merge_by_lines() -> None:
    base = b"alpha\nbeta\ngamma\ndelta\nepsilon\n"
    ours = b"ALPHA\nbeta\ngamma\ndelta\nepsilon\n"
    theirs = b"alpha\nbeta\ngamma\ndelta\nEPSILON\n"
    assert rules.merge3(base, ours, theirs) == b"ALPHA\nbeta\ngamma\ndelta\nEPSILON\n"
    # The same change on both sides: once.
    assert rules.merge3(base, ours, ours) == ours
    # One side only.
    assert rules.merge3(base, base, theirs) == theirs
    # Both changed the same line differently: a conflict.
    assert (
        rules.merge3(base, b"one\nbeta\ngamma\ndelta\nepsilon\n", b"two\nbeta\ngamma\ndelta\nepsilon\n")
        is None
    )
    # Both inserted at the same place, differently (a sorted file's new entries side by side): a conflict.
    assert rules.merge3(b"a\nc\n", b"a\nb1\nc\n", b"a\nb2\nc\n") is None
    # No base (a file made on both sides): two different files conflict.
    assert rules.merge3(None, b"x\n", b"y\n") is None
    # Not text: never merged.
    assert rules.merge3(b"\xff\n", b"\xfe\n", b"\xfd\n") is None


def test_a_pulls_plan() -> None:
    base = {
        "same.py": "1",
        "theirs.py": "1",
        "mine.py": "1",
        "both.py": "1",
        "gone.py": "1",
        "keep.py": "1",
        "lost.py": "1",
    }
    local = {"same.py": "1", "theirs.py": "1", "mine.py": "2", "both.py": "2", "keep.py": "2", "new.py": "n"}
    remote = {
        "same.py": "1",
        "theirs.py": "3",
        "mine.py": "1",
        "both.py": "3",
        "lost.py": "4",
        "added.py": "a",
    }
    steps = {s.path: s.action for s in rules.pull_plan(base, local, remote)}
    assert steps == {
        "theirs.py": "take",  # only they changed it
        "both.py": "merge",  # both did
        "keep.py": "kept",  # deleted there, changed here: stays, said
        "lost.py": "restore",  # deleted here, changed there: theirs back
        "added.py": "take",  # new there
    }  # same.py, mine.py (a change to push), new.py (to push) and gone.py (gone on both sides): nothing
    # Deleted there and unchanged here: deleted here.
    assert [s.action for s in rules.pull_plan({"x": "1"}, {"x": "1"}, {})] == ["delete"]


def test_a_secret_is_found_before_it_leaves() -> None:
    assert rules.secret_in('conn = connect(password=secret("WAREHOUSE_PASSWORD"))') is None
    assert rules.secret_in('password = "Pa55word-Zx81!"') == "a password written into it"
    assert rules.secret_in('api_key: "changeme"') is None
    assert rules.secret_in("token ghp_" + "a" * 36) == "a GitHub token"
    assert rules.secret_in("-----BEGIN RSA PRIVATE KEY-----") == "a private key"
    assert rules.secret_in("AccountKey=" + "Q" * 40) == "a storage account key"
    assert rules.secret_in("the value made-up-kept-in-keyring here", ["made-up-kept-in-keyring"]) == (
        "a value this computer keeps in its keyring"
    )


def test_the_words() -> None:
    assert rules.status_words(False, 0, 0, 0) == ("not_connected", "Not connected")
    assert rules.status_words(True, 2, 3, 4) == ("conflicts", "Conflicts: 2")
    assert rules.status_words(True, 0, 2, 4) == ("behind", "2 behind: Pull")
    assert rules.status_words(True, 0, 0, 3) == ("changes", "3 changes to push")
    assert rules.status_words(True, 0, 0, 1) == ("changes", "1 change to push")
    assert rules.status_words(True, 0, 0, 0) == ("up_to_date", "Up to date")
    assert rules.message("", 3) == "Update from Swiss Army Bench: 3 files"
    assert rules.message(None, 1, "Close") == "Update Close from Swiss Army Bench: 1 file"
    assert rules.pull_words(2, 1, 0, 2, 0) == "2 files updated, 1 merged. 2 conflicts: resolve and Push"
    assert rules.device_answer({"error": "authorization_pending", "interval": 5}) == ("pending", 5)
    assert rules.device_answer({"access_token": "x"}) == ("token", "x")


def test_the_source_control_groups_use_vs_codes_letters() -> None:
    base = {"a.py": "1", "b.py": "1", "c.py": "1", "d.py": "1"}
    local = {"a.py": "2", "b.py": "1", "d.py": "2", "new.py": "n", "staged_new.py": "s"}
    found = rules.groups(base, local, ["a.py", "staged_new.py"], ["d.py"])
    letters = {g: [(r["path"], r["letter"]) for r in rows] for g, rows in found.items()}
    assert letters == {
        "merge": [("d.py", "!")],
        "index": [("a.py", "M"), ("staged_new.py", "A")],
        "workingTree": [("c.py", "D"), ("new.py", "U")],
    }
    assert found["index"][0]["colour"] == "gitDecoration.stageModifiedResourceForeground"
    assert found["workingTree"][1]["tooltip"] == "Untracked"
    # Scoped to a shared project's folder.
    scoped = rules.groups(
        {"Close/a.py": "1", "Other/b.py": "1"}, {"Close/a.py": "2", "Other/b.py": "2"}, [], [], "Close"
    )
    assert [r["path"] for r in scoped["workingTree"]] == ["Close/a.py"]
    text = rules.unified("one\ntwo\n", "one\nthree\n", "x.py")
    assert text.splitlines()[:3] == ["--- a/x.py", "+++ b/x.py", "@@ -1,2 +1,2 @@"]
