"""A team's rules (domain/team.py; the owner, 2026-11-19: "you have made linking a meta store and shared
project folder way too difficult"): one repository's layout, the local copy's place, the steps and the one
kept
over Install's restart, the repositories offered, what a new team takes from this computer, Leave's choices
and
the Joined row's words. Made-up names only."""

from __future__ import annotations

import pytest

from swissarmybench.domain import team as rules


def test_a_new_teams_layout() -> None:
    files = rules.layout()
    assert set(files) == {"README.md", ".gitignore", "projects/README.md"}
    readme = files["README.md"].decode()
    for folder in (
        "connections/",
        "vaults/",
        "apis/",
        "blades/",
        "relationship-sets/",
        "catalog/",
        "projects/",
    ):
        assert folder in readme
    assert "meta store" not in readme.casefold() and "clone" not in readme.casefold()
    ignored = files[".gitignore"].decode().splitlines()
    assert "local/" in ignored and ".sab/data/" in ignored


def test_the_local_copys_place_is_the_same_every_time() -> None:
    place = rules.local_copy("made-up-team/team-library")
    assert place == ("team", "made-up-team-team-library")
    assert rules.local_copy("made-up-team/team-library") == place
    assert rules.PROJECTS == "projects"
    # Nothing odd in the folder's name.
    assert rules.local_copy("a/..") == ("team", "a")


def test_names_and_owners() -> None:
    assert rules.check_name(" team library ") == "team-library"
    for bad in ("", "..", "a/b", "x.git", "x" * 101):
        with pytest.raises(rules.TeamError):
            rules.check_name(bad)
    assert rules.check_owner("") is None
    assert rules.check_owner("made-up-team") == "made-up-team"
    with pytest.raises(rules.TeamError):
        rules.check_owner("-nope")


def test_the_steps_and_the_one_kept_over_a_restart() -> None:
    assert rules.next_step("join", False, False) == "install"
    assert rules.next_step("join", True, False) == "sign_in"
    assert rules.next_step("join", True, True) == "pick"
    assert rules.next_step("start", True, True) == "name"
    kept = rules.pending("join", "install", 1000.0)
    assert kept == {"action": "join", "step": "install", "since": 1000.0}
    with pytest.raises(rules.TeamError):
        rules.pending("join", "name", 1000.0)
    # After the restart with GitHub sync installed: the flow goes on where it was.
    assert rules.resume(kept, True, False, 1100.0) == {"action": "join", "step": "sign_in"}
    assert rules.resume(kept, True, True, 1100.0) == {"action": "join", "step": "pick"}
    # The install did not happen: Install again.
    assert rules.resume(kept, False, False, 1100.0) == {"action": "join", "step": "install"}
    # A day later, or a broken record: nothing taken up.
    assert rules.resume(kept, True, True, 1000.0 + rules.PENDING_SECONDS + 1) is None
    for broken in (None, {}, {"action": "steal", "since": 1}, {"action": "join", "since": "x"}, [1]):
        assert rules.resume(broken, True, True, 1100.0) is None


def test_the_repositories_offered_newest_first() -> None:
    found = rules.newest_first(
        [
            {"repository": "made-up-team/old", "pushed": "2026-01-01T00:00:00Z"},
            {"repository": "made-up-team/team-library", "pushed": "2026-11-18T00:00:00Z"},
            {"repository": "someone/read-only", "pushed": "2026-11-19T00:00:00Z", "can_push": False},
        ]
    )
    assert [r["repository"] for r in found] == ["made-up-team/team-library", "made-up-team/old"]
    assert [r["repository"] for r in rules.newest_first(found, "TEAM lib")] == ["made-up-team/team-library"]


def test_what_a_new_team_takes_from_this_computer() -> None:
    paths = [
        "README.md",
        ".gitignore",
        ".git/HEAD",
        "connections/Warehouse.blade.py",
        "variables.toml",
        "local/variables.toml",
        "catalog/Warehouse.json",
        "projects/Old/plan.md",
    ]
    assert rules.copied_to_new_team(paths) == [
        "catalog/Warehouse.json",
        "connections/Warehouse.blade.py",
        "local/variables.toml",
        "variables.toml",
    ]


def test_leaves_choices() -> None:
    team = {
        "connections/Warehouse.blade.py": "a",
        "connections/Sales.blade.py": "b",
        "variables.toml": "c",
        "projects/Close/plan.md": "d",
        "README.md": "e",
        "local/variables.toml": "f",
    }
    own = {"connections/Sales.blade.py": "b", "variables.toml": "mine"}
    assert rules.leave_plan(team, own, False) == {"copy": [], "same": [], "kept": []}
    assert rules.leave_plan(team, own, True) == {
        "copy": ["connections/Warehouse.blade.py"],
        "same": ["connections/Sales.blade.py"],
        "kept": ["variables.toml"],
    }
    asked = rules.leave_question("made-up-team/team-library")
    assert [c["keep"] for c in asked["choices"]] == [True, False]
    said = rules.leave_words("made-up-team/team-library", "/made/up/team", 1, 1)
    assert "/made/up/team" in said and "1 item copied" in said and "1 of yours kept" in said


def test_the_joined_rows_words_only_when_something_is_to_do() -> None:
    assert rules.sync_words(None) is None
    assert rules.sync_words({"connected": True, "state": "up_to_date", "words": "Up to date"}) is None
    assert rules.sync_words({"connected": True, "state": "changes", "words": "2 changes to push"}) == {
        "state": "changes",
        "words": "2 changes to push",
    }
    assert rules.sync_words({"connected": True, "state": "behind", "words": "1 behind: Pull"})
    assert rules.sync_words({"connected": True, "error": "x", "state": "up_to_date"}) == {
        "state": "error",
        "words": "GitHub could not be asked",
    }
