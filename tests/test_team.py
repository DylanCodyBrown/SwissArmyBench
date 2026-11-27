"""Settings' Team box over HTTP (services/team.py; the owner, 2026-11-19: "you have made linking a meta store
and
shared project folder way too difficult"), against GitHub stood in for on 127.0.0.1 (tests/github_standin.py):
one repository for the team library and its projects/. Join (signed in, the repository picked, the local copy
made in the state folder, both folders pointed at it, the checklist), the Joined row's sync words, Pull and
Push,
a shared project's card inside the one repository, Start (the repository made with the layout, this computer's
library pushed, never local/), Leave (asked first; with and without a copy; the local copy left), the agent's
Allow, the step kept over Install's restart, and GitHub sync not installed. Made-up data only."""

from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path

import pytest

from swissarmybench_git import extension as git_extension
from tests.conftest import AGENT, AUTH, make_client
from tests.fake_keyring import MemoryKeyring, memory_keyring
from tests.github_standin import LOGIN, TOKEN, GitHubStandin
from tests.test_scm import CONNECTION, answer, every_text, fresh, ok, signed_in

TEAM = "made-up-team/team-library"
MANIFEST = json.dumps({"swissarmybench": "project", "format": 1, "tables": []}).encode()


@pytest.fixture
def hub(monkeypatch: pytest.MonkeyPatch) -> Iterator[GitHubStandin]:
    with GitHubStandin() as standin:
        monkeypatch.setenv("SWISSARMYBENCH_GITHUB_API", standin.url)
        monkeypatch.setenv("SWISSARMYBENCH_GITHUB_WEB", standin.url)
        monkeypatch.delenv("SWISSARMYBENCH_GITHUB_CLIENT_ID", raising=False)
        monkeypatch.setattr(git_extension, "CLIENT_ID", "")
        standin.repository("made-up-team/old-notes", {"README.md": b"# Old\n"})
        standin.repository(
            TEAM,
            {
                "README.md": b"# Team library\n",
                ".gitignore": b"local/\n.sab/data/\n",
                "connections/Warehouse.blade.py": CONNECTION,
                "projects/Close/.sab/project.json": MANIFEST,
                "projects/Close/plan.md": b"alpha\nbeta\n",
            },
        )
        yield standin


@pytest.fixture
def vault() -> Iterator[MemoryKeyring]:
    with memory_keyring() as fake:
        yield fake


def test_join_a_team_pull_push_and_its_shared_projects(
    tmp_path: Path, hub: GitHubStandin, vault: MemoryKeyring
) -> None:
    copy = (tmp_path / "state" / "team" / "made-up-team-team-library").resolve()
    with make_client(tmp_path) as client:
        status = ok(client.get("/team", headers=AUTH))
        assert status["state"] == "none" and status["sync_on"] is True and "needs" not in status
        assert status["signed_in"] is False and "Fine-grained tokens" in " ".join(status["token_steps"])
        # Not signed in: nothing is offered, nothing joined.
        assert client.get("/team/repositories", headers=AUTH).status_code == 403
        assert client.post("/team/join", json={"repository": TEAM}, headers=AUTH).status_code == 403
        signed_in(client)
        offered = ok(client.get("/team/repositories", headers=AUTH))
        assert [r["repository"] for r in offered["repositories"]] == [TEAM, "made-up-team/old-notes"]
        assert [
            r["repository"]
            for r in ok(client.get("/team/repositories?search=LIB", headers=AUTH))["repositories"]
        ] == [TEAM]

        joined = ok(
            client.post("/team/join", json={"repository": f"https://github.com/{TEAM}"}, headers=AUTH)
        )
        assert joined["state"] == "joined" and joined["joined"] == TEAM and joined["files"] == 5
        assert joined["team"]["repository"] == TEAM and Path(joined["team"]["folder"]) == copy
        assert joined["team"]["sync"] is None  # up to date: nothing said
        assert joined["team"]["url"] == f"{hub.url}/{TEAM}"
        assert "heading" in joined["setup"]
        # The library is the local copy; the shared projects folder its projects/.
        assert Path(ok(client.get("/library", headers=AUTH))["folder"]) == copy
        assert Path(ok(client.get("/projects/folder", headers=AUTH))["shared_folder"]) == copy / "projects"
        assert "Warehouse" in {b["name"] for b in ok(client.get("/blades", headers=AUTH))["blades"]}
        cards = ok(client.get("/projects/explorer", headers=AUTH))["projects"]
        close = next(c for c in cards if c["name"] == "Close")
        assert close["where"] == "shared"
        # The shared projects folder is inside the one repository: connected through it.
        shared = next(f for f in ok(client.get("/git", headers=AUTH))["folders"] if f["which"] == "shared")
        assert shared["connected"] is True and shared["repository"] == TEAM and shared["within"] == "projects"

        # A teammate's push: the row says Pull; Pull brings it.
        hub.teammate(TEAM, {"projects/Close/plan.md": b"alpha\nbeta\ngamma\n"})
        fresh(client)
        assert ok(client.get("/team?remote=1", headers=AUTH))["team"]["sync"] == {
            "state": "behind",
            "words": "1 behind: Pull",
        }
        pulled = ok(client.post("/team/pull", headers=AUTH))
        assert pulled["updated"] == ["projects/Close/plan.md"]
        assert (copy / "projects" / "Close" / "plan.md").read_text() == "alpha\nbeta\ngamma\n"

        # A change here, in a project and in the library: the shared card pushes only its project's files.
        (copy / "projects" / "Close" / "plan.md").write_text("alpha\nbeta\ngamma\ndelta\n")
        (copy / "connections" / "Warehouse.blade.py").write_bytes(CONNECTION + b"# edited\n")
        assert ok(client.get("/team", headers=AUTH))["team"]["sync"]["words"] == "2 changes to push"
        card = next(f for f in ok(client.get("/git", headers=AUTH))["folders"] if f["which"] == "shared")
        assert card["projects"] == {"Close": {"to_push": 1, "conflicts": 0}} and card["to_push"] == 1
        one = ok(
            client.post(
                "/git/push", json={"which": "shared", "path": str(copy / "projects" / "Close")}, headers=AUTH
            )
        )
        assert one["pushed"] == 1
        assert hub.files(TEAM)["connections/Warehouse.blade.py"] == CONNECTION
        # The Team box's Push: the rest.
        assert ok(client.post("/team/push", headers=AUTH))["pushed"] == 1
        assert hub.files(TEAM)["connections/Warehouse.blade.py"] == CONNECTION + b"# edited\n"
        assert ok(client.get("/team", headers=AUTH))["team"]["sync"] is None

        # A second Join of the same repository pulls into the same copy (nothing in the way).
        again = ok(client.post("/team/join", json={"repository": TEAM}, headers=AUTH))
        assert again["state"] == "joined" and Path(again["team"]["folder"]) == copy
        # Show its folder is the user's own.
        assert client.post("/team/show", headers=AGENT).status_code == 403

        # Leave: asked first; then without a copy. The library and the shared folder go back; the copy stays.
        asked = ok(client.post("/team/leave", json={}, headers=AUTH))
        assert [c["keep"] for c in asked["ask"]["choices"]] == [True, False]
        left = ok(client.post("/team/leave", json={"keep": False}, headers=AUTH))
        assert left["state"] == "none" and left["copied"] == 0 and str(copy) in left["words"]
        assert ok(client.get("/library", headers=AUTH))["is_default"] is True
        assert ok(client.get("/projects/folder", headers=AUTH))["shared_folder"] is None
        assert "Warehouse" not in {b["name"] for b in ok(client.get("/blades", headers=AUTH))["blades"]}
        assert (copy / "connections" / "Warehouse.blade.py").is_file()
        assert client.post("/team/leave", json={"keep": True}, headers=AUTH).status_code == 409
    assert TOKEN.encode() not in every_text(tmp_path)


def test_leave_with_a_copy_keeps_this_computers_own_items(
    tmp_path: Path, hub: GitHubStandin, vault: MemoryKeyring
) -> None:
    own = tmp_path / "state" / "library"
    with make_client(tmp_path) as client:
        (own / "connections").mkdir(parents=True, exist_ok=True)
        mine = CONNECTION.replace(b"sqlite3.connect", b"sqlite3.connect  # mine")
        (own / "connections" / "Warehouse.blade.py").write_bytes(mine)
        signed_in(client)
        ok(client.post("/team/join", json={"repository": TEAM}, headers=AUTH))
        copy = Path(ok(client.get("/team", headers=AUTH))["team"]["folder"])
        (copy / "connections" / "Ledger.blade.py").write_bytes(CONNECTION.replace(b"Warehouse", b"Ledger"))
        left = ok(client.post("/team/leave", json={"keep": True}, headers=AUTH))
        assert (left["copied"], left["kept"]) == (1, 1)
        assert "1 of yours kept" in left["words"]
        assert (own / "connections" / "Ledger.blade.py").is_file()
        assert (own / "connections" / "Warehouse.blade.py").read_bytes() == mine
        assert not (own / "projects").exists()
        names = {b["name"] for b in ok(client.get("/blades", headers=AUTH))["blades"]}
        assert {"Ledger", "Warehouse"} <= names


def test_start_a_team_makes_the_repository_and_pushes_the_library(
    tmp_path: Path, hub: GitHubStandin, vault: MemoryKeyring
) -> None:
    own = tmp_path / "state" / "library"
    with make_client(tmp_path) as client:
        (own / "connections").mkdir(parents=True, exist_ok=True)
        (own / "connections" / "Warehouse.blade.py").write_bytes(CONNECTION)
        (own / "local").mkdir(exist_ok=True)
        (own / "local" / "variables.toml").write_text('[variables.PLACE]\nvalue = "here"\n')
        assert client.post("/team/start", json={"name": "finance-team"}, headers=AUTH).status_code == 403
        signed_in(client)
        assert ok(client.get("/team/owners", headers=AUTH))["owners"] == [LOGIN, "made-up-team"]
        bad = client.post("/team/start", json={"name": "no/slash"}, headers=AUTH)
        assert bad.status_code == 400
        started = ok(
            client.post("/team/start", json={"name": "finance team", "owner": "made-up-team"}, headers=AUTH)
        )
        repository = "made-up-team/finance-team"
        assert started["started"] == repository and started["state"] == "joined"
        assert hub.created == [repository] and hub.repos[repository].private is True
        there = hub.files(repository)
        assert set(there) == {
            "README.md",
            ".gitignore",
            "projects/README.md",
            "connections/Warehouse.blade.py",
        }
        assert b"projects/" in there["README.md"] and b".sab/data/" in there[".gitignore"]
        copy = Path(started["team"]["folder"])
        assert copy.name == "made-up-team-finance-team"
        assert (copy / "local" / "variables.toml").is_file()  # copied, never pushed
        assert Path(ok(client.get("/projects/folder", headers=AUTH))["shared_folder"]) == copy / "projects"
        # The same name again: GitHub refuses, said.
        ok(client.post("/team/leave", json={"keep": False}, headers=AUTH))
        taken = client.post(
            "/team/start", json={"name": "finance-team", "owner": "made-up-team"}, headers=AUTH
        )
        assert taken.status_code == 409 and "already exists" in taken.text


def test_the_agent_joins_starts_and_leaves_only_on_the_users_allow(
    tmp_path: Path, hub: GitHubStandin, vault: MemoryKeyring
) -> None:
    with make_client(tmp_path) as client:
        signed_in(client)
        waiter = answer(client, False)
        declined = client.post("/team/join", json={"repository": TEAM}, headers=AGENT)
        waiter.join()
        assert declined.status_code == 403 and ok(client.get("/team", headers=AGENT))["state"] == "none"
        waiter = answer(client, True)
        ok(client.post("/team/join", json={"repository": TEAM}, headers=AGENT))
        waiter.join()
        assert ok(client.get("/team", headers=AGENT))["state"] == "joined"
        # The agent must say keep or not (it gets the question back), then Allow.
        assert "ask" in ok(client.post("/team/leave", json={}, headers=AGENT))
        waiter = answer(client, True)
        ok(client.post("/team/leave", json={"keep": False}, headers=AGENT))
        waiter.join()
        waiter = answer(client, False)
        refused = client.post("/team/start", json={"name": "agent-team"}, headers=AGENT)
        waiter.join()
        assert refused.status_code == 403 and hub.created == []
        # Signing in stays the user's own.
        assert client.post("/git/sign-in/token", json={"token": TOKEN}, headers=AGENT).status_code == 403
