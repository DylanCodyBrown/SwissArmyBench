"""The Git extension over HTTP, against a GitHub stood in for on 127.0.0.1 (tests/github_standin.py; real GitHub is
never reached): signing in (a token, the device flow; the token in the keyring only and never in an answer, a
file or a log), clone, connect, pull (clean, three-way merged, a conflict beside the file, deletes), push (blobs,
a tree, a commit, the ref fast-forward; refused when behind or a file holds a secret; .gitignore, local/ and
large files left out), the status words, the footer's mark, the Source Control page (stage, discard, commit,
history, a commit's files, diffs, branches), the agent's Allow, and the extension off. Made-up data only."""

from __future__ import annotations

import json
import threading
import time
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from starlette.testclient import TestClient

from swissarmybench import extensions
from swissarmybench_git import extension as git_extension
from swissarmybench_git.domain import sync as rules
from tests.conftest import AGENT, AUTH, make_client
from tests.fake_keyring import MemoryKeyring, memory_keyring
from tests.github_standin import LOGIN, TOKEN, GitHubStandin

REPO = "made-up-team/meta-store"
SHARED = "made-up-team/shared-projects"
CONNECTION = (
    b'# /// swissarmybench-blade\n# format = 1\n# name = "Warehouse"\n# kind = "sql"\n# template = "sqlite"\n'
    b'# dialect = "sqlite"\n# ///\nimport sqlite3\nconn = sqlite3.connect(":memory:")\n'
)


@pytest.fixture
def hub(monkeypatch: pytest.MonkeyPatch) -> Iterator[GitHubStandin]:
    with GitHubStandin() as standin:
        monkeypatch.setenv(extensions.VARIABLE, "streamlit,git")
        monkeypatch.setenv("SWISSARMYBENCH_GITHUB_API", standin.url)
        monkeypatch.setenv("SWISSARMYBENCH_GITHUB_WEB", standin.url)
        monkeypatch.delenv("SWISSARMYBENCH_GITHUB_CLIENT_ID", raising=False)
        # A token only, unless a test names a client id (the real one is the owner's registered app's).
        monkeypatch.setattr(git_extension, "CLIENT_ID", "")
        yield standin


@pytest.fixture
def vault() -> Iterator[MemoryKeyring]:
    with memory_keyring() as fake:
        yield fake


def ok(response: Any) -> Any:
    assert response.status_code == 200, response.text
    return response.json()


def fresh(client: TestClient) -> None:
    """Forget when GitHub was last asked (it is asked at most once a minute)."""
    client.app.state.ctx.git.forget_remote()  # type: ignore[attr-defined]


def answer(client: TestClient, approve: bool) -> threading.Thread:
    def run() -> None:
        for _ in range(200):
            pending = client.get("/agent/approvals", headers=AUTH).json()["pending"]
            if pending:
                client.post(f"/agent/approvals/{pending[0]['id']}", json={"approve": approve}, headers=AUTH)
                return
            time.sleep(0.05)

    thread = threading.Thread(target=run)
    thread.start()
    return thread


def signed_in(client: TestClient) -> None:
    ok(client.post("/git/sign-in/token", json={"token": TOKEN}, headers=AUTH))


def every_text(tmp_path: Path) -> bytes:
    found = b""
    for path in (tmp_path / "state").rglob("*"):
        if path.is_file():
            found += path.read_bytes()
    return found


def test_signing_in_keeps_the_token_in_the_keyring_only(
    tmp_path: Path, hub: GitHubStandin, vault: MemoryKeyring
) -> None:
    with make_client(tmp_path) as client:
        status = ok(client.get("/git", headers=AUTH))
        assert status["signed_in"] is False and status["device"] is False
        assert "Fine-grained tokens" in " ".join(status["token_steps"])
        # The agent never signs in, nor out.
        assert client.post("/git/sign-in/token", json={"token": TOKEN}, headers=AGENT).status_code == 403
        assert client.post("/git/sign-in/device", headers=AGENT).status_code == 403
        # A token GitHub refuses.
        refused = client.post("/git/sign-in/token", json={"token": "github_pat_made_up_wrong"}, headers=AUTH)
        assert refused.status_code == 400 and "GitHub refused that token" in refused.text
        # No client id: Sign in with GitHub says so.
        device = client.post("/git/sign-in/device", headers=AUTH)
        assert device.status_code == 400 and "use a token instead" in device.text
        done = ok(client.post("/git/sign-in/token", json={"token": TOKEN}, headers=AUTH))
        assert done == {"signed_in": True, "account": LOGIN}
        assert vault.values[("SwissArmyBench", "github/token")] == TOKEN
        answers = [
            client.get("/git", headers=AGENT).text,
            client.get("/git/repositories", headers=AGENT).text,
        ]
        assert all(TOKEN not in a for a in answers) and REPO not in answers[1]
        hub.repository(REPO, {"README.md": b"# Meta store\n"})
        assert ok(client.get("/git/repositories", headers=AGENT))["repositories"][0]["repository"] == REPO
        assert client.post("/git/sign-out", headers=AGENT).status_code == 403
        ok(client.post("/git/sign-out", headers=AUTH))
        assert ("SwissArmyBench", "github/token") not in vault.values
        assert client.get("/git/repositories", headers=AUTH).status_code == 403
    assert TOKEN.encode() not in every_text(tmp_path)


def test_the_device_flow(
    tmp_path: Path, hub: GitHubStandin, vault: MemoryKeyring, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("SWISSARMYBENCH_GITHUB_CLIENT_ID", "made-up-client-id")
    with make_client(tmp_path) as client:
        assert ok(client.get("/git", headers=AUTH))["device"] is True
        assert client.post("/git/sign-in/device/poll", headers=AUTH).status_code == 400  # not started
        started = ok(client.post("/git/sign-in/device", headers=AUTH))
        assert (
            started["user_code"] == "WDJB-MJHT"
            and started["verification_uri"] == "https://github.com/login/device"
        )
        assert "device_code" not in started
        assert ok(client.post("/git/sign-in/device/poll", headers=AUTH))["state"] == "pending"
        hub.device_ready = True
        assert ok(client.post("/git/sign-in/device/poll", headers=AUTH)) == {
            "state": "signed_in",
            "account": LOGIN,
        }
        assert vault.values[("SwissArmyBench", "github/token")] == TOKEN
    assert TOKEN.encode() not in every_text(tmp_path)


def test_clone_pull_and_push_the_meta_store(
    tmp_path: Path, hub: GitHubStandin, vault: MemoryKeyring, monkeypatch: pytest.MonkeyPatch
) -> None:
    hub.repository(
        REPO,
        {
            "README.md": b"# Meta store\n",
            ".gitignore": b"local/\nscratch/\n",
            "connections/Warehouse.blade.py": CONNECTION,
            "notes.md": b"one\ntwo\nthree\nfour\nfive\n",
            "shared.md": b"alpha\nbeta\n",
            "old.md": b"going\n",
        },
    )
    meta = tmp_path / "team-meta"
    with make_client(tmp_path) as client:
        # Not signed in: nothing reaches GitHub.
        refused = client.post(
            "/git/clone", json={"which": "library", "repository": REPO, "folder": str(meta)}, headers=AUTH
        )
        assert refused.status_code == 403 and "Sign in to GitHub first" in refused.text
        signed_in(client)
        # A folder that is not empty is not cloned into.
        busy = tmp_path / "busy"
        busy.mkdir()
        (busy / "x.txt").write_text("x")
        taken = client.post(
            "/git/clone", json={"which": "library", "repository": REPO, "folder": str(busy)}, headers=AUTH
        )
        assert taken.status_code == 409 and "Connect this folder instead" in taken.text
        done = ok(
            client.post(
                "/git/clone", json={"which": "library", "repository": REPO, "folder": str(meta)}, headers=AUTH
            )
        )
        assert done["files"] == 6 and done["branch"] == "main"
        assert (meta / "connections" / "Warehouse.blade.py").read_bytes() == CONNECTION
        # The meta store folder is the clone now: its connection is the library's.
        assert ok(client.get("/library", headers=AUTH))["folder"] == str(meta.resolve())
        assert "Warehouse" in {b["name"] for b in ok(client.get("/blades", headers=AUTH))["blades"]}
        library = ok(client.get("/git?remote=1", headers=AUTH))["folders"][0]
        assert (library["which"], library["repository"], library["words"]) == ("library", REPO, "Up to date")

        # A teammate pushes; here a file changes: the words, then Pull (taken, merged, a conflict, a delete).
        hub.teammate(
            REPO,
            {
                "connections/Ledger.blade.py": CONNECTION.replace(b"Warehouse", b"Ledger"),
                "notes.md": b"one\ntwo\nthree\nfour\nFIVE\n",
                "shared.md": b"alpha\nTHEIRS\n",
                "old.md": None,
            },
        )
        (meta / "notes.md").write_text("ONE\ntwo\nthree\nfour\nfive\n")
        (meta / "shared.md").write_text("alpha\nMINE\n")
        (meta / "local").mkdir()
        (meta / "local" / "variables.toml").write_text('PLACE = "here"\n')
        (meta / "scratch").mkdir()
        (meta / "scratch" / "x.txt").write_text("ignored\n")
        fresh(client)
        library = ok(client.get("/git?remote=1", headers=AUTH))["folders"][0]
        assert library["words"] == "1 behind: Pull" and library["to_push"] == 2
        # A push while behind is refused: Pull first (never a force).
        behind = client.post("/git/push", json={"which": "library"}, headers=AUTH)
        assert behind.status_code == 409 and "Pull first" in behind.text
        pulled = ok(client.post("/git/pull", json={"which": "library"}, headers=AUTH))
        assert pulled["updated"] == ["connections/Ledger.blade.py"] and pulled["merged"] == ["notes.md"]
        assert pulled["deleted"] == ["old.md"] and pulled["conflicts"] == ["shared.md"]
        assert pulled["words"] == "1 file updated, 1 merged, 1 deleted. 1 conflict: resolve and Push"
        assert (meta / "notes.md").read_text() == "ONE\ntwo\nthree\nfour\nFIVE\n"
        assert (meta / "shared.md").read_text() == "alpha\nMINE\n"  # left as it was
        assert (meta / "shared.md.theirs").read_text() == "alpha\nTHEIRS\n"
        assert not (meta / "old.md").exists()
        # The shared catalog and the blades read the pulled folder again.
        assert "Ledger" in {b["name"] for b in ok(client.get("/blades", headers=AUTH))["blades"]}
        status = ok(client.get("/git", headers=AUTH))
        assert status["folders"][0]["words"] == "Conflicts: 1"
        assert status["folders"][0]["conflicts"] == ["shared.md"]
        conflict = client.post("/git/push", json={"which": "library"}, headers=AUTH)
        assert conflict.status_code == 409 and "conflict to resolve first" in conflict.text

        # Resolved: the file kept as wanted, its .theirs deleted. A secret in a file is refused, then taken out.
        (meta / "shared.md").write_text("alpha\nMINE\nTHEIRS\n")
        (meta / "shared.md.theirs").unlink()
        (meta / "connections" / "Warehouse.blade.py").write_bytes(
            CONNECTION + b'password = "Pa55word-Zx81!"\n'
        )
        secret = client.post("/git/push", json={"which": "library"}, headers=AUTH)
        assert (
            secret.status_code == 400
            and "connections/Warehouse.blade.py looks like it holds a password" in secret.text
        )
        (meta / "connections" / "Warehouse.blade.py").write_bytes(CONNECTION + b"# edited\n")
        # Large files are left out (GitHub's limit: 50 MB, made small here).
        monkeypatch.setattr(rules, "MAX_FILE_BYTES", 1000)
        (meta / "big.csv").write_text("x" * 2000)
        assert ok(client.get("/git", headers=AUTH))["folders"][0]["words"] == "3 changes to push"
        pushed = ok(
            client.post("/git/push", json={"which": "library", "message": "Resolve the notes"}, headers=AUTH)
        )
        assert pushed["pushed"] == 3 and pushed["large"] == ["big.csv"]
        there = hub.files(REPO)
        assert (
            there["shared.md"] == b"alpha\nMINE\nTHEIRS\n"
            and there["notes.md"] == b"ONE\ntwo\nthree\nfour\nFIVE\n"
        )
        assert "big.csv" not in there and "local/variables.toml" not in there and "scratch/x.txt" not in there
        assert hub.commits[hub.head(REPO)]["message"] == "Resolve the notes"
        assert ok(client.get("/git?remote=1", headers=AUTH))["folders"][0]["words"] == "Up to date"
        # Nothing to push.
        assert (
            ok(client.post("/git/push", json={"which": "library"}, headers=AUTH))["words"]
            == "Nothing to push"
        )
    assert TOKEN.encode() not in every_text(tmp_path)


def test_connect_compares_and_writes_nothing(
    tmp_path: Path, hub: GitHubStandin, vault: MemoryKeyring
) -> None:
    hub.repository(REPO, {"README.md": b"# Meta store\n", "a.md": b"theirs\n", "only-there.md": b"x\n"})
    with make_client(tmp_path) as client:
        signed_in(client)
        folder = Path(ok(client.get("/library", headers=AUTH))["folder"])
        folder.mkdir(parents=True, exist_ok=True)
        (folder / "a.md").write_text("mine\n")
        (folder / "only-here.md").write_text("y\n")
        done = ok(client.post("/git/connect", json={"which": "library", "repository": REPO}, headers=AUTH))
        assert done["different"] == ["a.md"] and "only-there.md" in done["only_there"]
        assert "only-here.md" in done["only_here"]
        assert (folder / "a.md").read_text() == "mine\n" and not (folder / "only-there.md").exists()
        assert ok(client.get("/git", headers=AUTH))["folders"][0]["words"] == "Not pulled yet: Pull"
        pulled = ok(client.post("/git/pull", json={"which": "library"}, headers=AUTH))
        assert "a.md" in pulled["conflicts"] and (folder / "a.md.theirs").read_text() == "theirs\n"
        assert (folder / "only-there.md").read_text() == "x\n"
        ok(client.post("/git/disconnect", json={"which": "library"}, headers=AGENT))
        assert ok(client.get("/git", headers=AUTH))["folders"][0]["words"] == "Not connected"


def test_the_agent_pulls_and_pushes_only_on_the_users_allow(
    tmp_path: Path, hub: GitHubStandin, vault: MemoryKeyring
) -> None:
    hub.repository(REPO, {"README.md": b"# Meta store\n"})
    meta = tmp_path / "team-meta"
    with make_client(tmp_path) as client:
        signed_in(client)
        thread = answer(client, False)
        refused = client.post(
            "/git/clone", json={"which": "library", "repository": REPO, "folder": str(meta)}, headers=AGENT
        )
        thread.join()
        assert refused.status_code == 403 and not meta.exists()
        thread = answer(client, True)
        ok(
            client.post(
                "/git/clone",
                json={"which": "library", "repository": REPO, "folder": str(meta)},
                headers=AGENT,
            )
        )
        thread.join()
        hub.teammate(REPO, {"README.md": b"# Meta store, edited\n"})
        thread = answer(client, False)
        assert client.post("/git/pull", json={"which": "library"}, headers=AGENT).status_code == 403
        thread.join()
        assert (meta / "README.md").read_text() == "# Meta store\n"
        thread = answer(client, True)
        ok(client.post("/git/pull", json={"which": "library"}, headers=AGENT))
        thread.join()
        (meta / "README.md").write_text("# Meta store, mine\n")
        thread = answer(client, True)
        pushed = ok(client.post("/git/push", json={"which": "library"}, headers=AGENT))
        thread.join()
        # (the library made its .gitignore in the clone on first use: it goes too)
        assert pushed["pushed"] >= 1 and hub.files(REPO)["README.md"] == b"# Meta store, mine\n"
        log = (
            (tmp_path / "state" / "audit.log").read_text()
            if (tmp_path / "state" / "audit.log").exists()
            else ""
        )
        assert TOKEN not in log


def test_the_source_control_page(tmp_path: Path, hub: GitHubStandin, vault: MemoryKeyring) -> None:
    hub.repository(
        REPO,
        {"README.md": b"# Meta store\n", ".gitignore": b"local/\n", "a.py": b"one\ntwo\n", "b.py": b"bee\n"},
    )
    hub.teammate(REPO, {"c.py": b"sea\n"}, "Add c")
    meta = tmp_path / "team-meta"
    with make_client(tmp_path) as client:
        signed_in(client)
        ok(
            client.post(
                "/git/clone", json={"which": "library", "repository": REPO, "folder": str(meta)}, headers=AUTH
            )
        )
        (meta / "a.py").write_text("one\nTWO\n")
        (meta / "b.py").unlink()
        (meta / "new.py").write_text("new\n")
        repo = ok(client.get("/git/changes", headers=AGENT))["repositories"][0]
        letters = {g: [(r["path"], r["letter"]) for r in rows] for g, rows in repo["groups"].items()}
        assert letters == {
            "merge": [],
            "index": [],
            "workingTree": [("a.py", "M"), ("b.py", "D"), ("new.py", "U")],
        }
        assert repo["name"] == "meta-store" and repo["branch"] == "main"
        ok(client.post("/git/stage", json={"which": "library", "paths": ["a.py", "new.py"]}, headers=AGENT))
        repo = ok(client.get("/git/changes?which=library", headers=AUTH))["repositories"][0]
        assert [(r["path"], r["letter"]) for r in repo["groups"]["index"]] == [("a.py", "M"), ("new.py", "A")]
        ok(
            client.post(
                "/git/stage", json={"which": "library", "paths": ["new.py"], "unstage": True}, headers=AUTH
            )
        )
        # The diff editor's two sides, and the agent's unified text.
        sides = ok(client.get("/git/diff?which=library&path=a.py", headers=AUTH))
        assert (sides["original"], sides["modified"]) == ("one\ntwo\n", "one\nTWO\n")
        assert sides["original_label"] == "a.py (HEAD)" and sides["modified_label"] == "a.py (Working Tree)"
        text = ok(client.get("/git/diff?which=library&path=a.py&unified=1", headers=AGENT))["diff"]
        assert "-two\n+TWO\n" in text
        # Commit: the staged file only.
        assert (
            client.post("/git/commit", json={"which": "library", "message": " "}, headers=AUTH).status_code
            == 400
        )
        committed = ok(
            client.post("/git/commit", json={"which": "library", "message": "Shout two"}, headers=AUTH)
        )
        assert (
            committed["pushed"] == 1
            and hub.files(REPO)["a.py"] == b"one\nTWO\n"
            and "b.py" in hub.files(REPO)
        )
        repo = ok(client.get("/git/changes", headers=AUTH))["repositories"][0]
        assert [r["path"] for r in repo["groups"]["workingTree"]] == ["b.py", "new.py"] and repo["groups"][
            "index"
        ] == []
        # Discard: the deleted file back, the new one gone (the agent's on Allow).
        thread = answer(client, True)
        ok(client.post("/git/discard", json={"which": "library", "paths": ["b.py", "new.py"]}, headers=AGENT))
        thread.join()
        assert (meta / "b.py").read_text() == "bee\n" and not (meta / "new.py").exists()
        assert ok(client.get("/git/changes", headers=AUTH))["repositories"][0]["count"] == 0
        # The graph's history, a commit's files and its diff.
        history = ok(client.get("/git/history?which=library", headers=AUTH))
        assert [r["subject"] for r in history["rows"]] == ["Shout two", "Add c", "Initial commit"]
        assert history["rows"][0]["parents"] == [history["rows"][1]["id"]]
        assert {r["kind"] for r in history["refs"]} == {"local", "remote"} and history["uncommitted"] == 0
        shout = history["rows"][0]["id"]
        files = ok(client.get(f"/git/commit-files?which=library&commit={shout}", headers=AUTH))
        assert [(f["path"], f["letter"]) for f in files["files"]] == [("a.py", "M")]
        sides = ok(client.get(f"/git/diff?which=library&path=a.py&commit={shout}", headers=AUTH))
        assert (sides["original"], sides["modified"]) == ("one\ntwo\n", "one\nTWO\n")
        added = ok(
            client.get(f"/git/diff?which=library&path=c.py&commit={history['rows'][1]['id']}", headers=AUTH)
        )
        assert added["added"] and added["modified"] == "sea\n"
        # Branches: create one on GitHub (Allow for the agent), check out another.
        thread = answer(client, True)
        ok(
            client.post(
                "/git/checkout",
                json={"which": "library", "branch": "q3-close", "create": True},
                headers=AGENT,
            )
        )
        thread.join()
        assert "q3-close" in hub.repos[REPO].refs
        branches = ok(client.get("/git/branches?which=library", headers=AUTH))
        assert branches["current"] == "q3-close" and {b["name"] for b in branches["branches"]} == {
            "main",
            "q3-close",
        }
        hub.teammate(REPO, {"main-only.md": b"m\n"}, branch="main")
        (meta / "a.py").write_text("dirty\n")
        dirty = client.post("/git/checkout", json={"which": "library", "branch": "main"}, headers=AUTH)
        assert dirty.status_code == 409 and "would be overwritten by checkout" in dirty.text
        (meta / "a.py").write_text("one\nTWO\n")
        ok(client.post("/git/checkout", json={"which": "library", "branch": "main"}, headers=AUTH))
        assert (meta / "main-only.md").read_text() == "m\n"
        # Sync: Pull then Push.
        hub.teammate(REPO, {"t.md": b"t\n"})
        (meta / "mine.md").write_text("mine\n")
        synced = ok(client.post("/git/sync", json={"which": "library"}, headers=AUTH))
        assert synced["pushed"]["pushed"] == 1 and (meta / "t.md").exists() and "mine.md" in hub.files(REPO)


def test_a_shared_project_its_card_and_the_footers_mark(
    tmp_path: Path, hub: GitHubStandin, vault: MemoryKeyring
) -> None:
    manifest = json.dumps({"swissarmybench": "project", "format": 1, "tables": []}).encode()
    hub.repository(
        SHARED,
        {
            "Close/.sab/project.json": manifest,
            "Close/notes.md": b"close\n",
            "Close/.gitignore": b".sab/data/\n",
            "Budget/.sab/project.json": manifest,
        },
    )
    shared = tmp_path / "shared"
    with make_client(tmp_path) as client:
        signed_in(client)
        # No project open: no mark.
        assert ok(client.get("/git/mark", headers=AUTH))["mark"] is None
        ok(
            client.post(
                "/git/clone",
                json={"which": "shared", "repository": SHARED, "folder": str(shared)},
                headers=AUTH,
            )
        )
        assert ok(client.get("/projects/folder", headers=AUTH))["shared_folder"] == str(shared.resolve())
        ok(client.post("/project/open", json={"path": str(shared / "Close")}, headers=AUTH))
        assert ok(client.get("/git/mark", headers=AUTH))["mark"] is None  # up to date
        (shared / "Close" / "notes.md").write_text("close, edited\n")
        (shared / "Close" / ".sab" / "data").mkdir()
        (shared / "Close" / ".sab" / "data" / "orders.parquet").write_bytes(b"made-up rows")
        (shared / "Budget" / "plan.md").write_text("another project's\n")
        mark = ok(client.get("/git/mark", headers=AUTH))["mark"]
        assert mark["words"] == "↑1 to push" and mark["which"] == "shared" and mark["name"] == "Close"
        status = ok(client.get("/git", headers=AUTH))["folders"][1]
        assert status["projects"] == {
            "Close": {"to_push": 1, "conflicts": 0},
            "Budget": {"to_push": 1, "conflicts": 0},
        }
        # The card's Push: its own project's files only, said in the message.
        pushed = ok(
            client.post("/git/push", json={"which": "shared", "path": str(shared / "Close")}, headers=AUTH)
        )
        assert pushed["pushed"] == 1 and pushed["message"] == "Update Close from Swiss Army Bench: 1 file"
        assert "Budget/plan.md" not in hub.files(
            SHARED
        ) and "Close/.sab/data/orders.parquet" not in hub.files(SHARED)
        assert ok(client.get("/git/mark", headers=AUTH))["mark"] is None
        hub.teammate(SHARED, {"Close/notes.md": b"close, theirs\n"})
        fresh(client)
        ok(client.get("/git?remote=1", headers=AUTH))
        assert ok(client.get("/git/mark", headers=AUTH))["mark"]["words"] == "↓1 behind"
        ok(client.post("/git/pull", json={"which": "shared"}, headers=AUTH))
        assert ok(client.get("/git/mark", headers=AUTH))["mark"] is None
        # The Source Control page scopes the shared folder to the open project.
        repo = ok(client.get("/git/changes?which=shared", headers=AUTH))["repositories"][0]
        assert repo["name"] == "shared-projects/Close" and repo["count"] == 0
        # The rail's area is the extension's (the page draws it from this), with the footer's mark route.
        assert ok(client.get("/app/areas", headers=AUTH))["areas"] == [
            {"area": "scm", "name": "Git", "icon": "source-control", "mark": "/git/mark"}
        ]


def test_off_the_door_says_which_extension(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(extensions.VARIABLE, "streamlit")
    with make_client(tmp_path) as client:
        off = client.get("/git", headers=AUTH)
        assert off.status_code in (404, 409) and "Git" in off.text
        assert ok(client.get("/app/areas", headers=AUTH))["areas"] == []


def test_githubs_sign_in_refusals_are_said_in_plain_words() -> None:
    """The owner saw only "GitHub answered 400" (2026-11-18): github.com/login says why in "error", not "message"."""
    import http.server

    from swissarmybench_git.adapters.github import GitHubClient, GitHubError

    answers = [
        (
            400,
            {"error": "device_flow_disabled", "error_description": "Device Flow must be explicitly enabled."},
        ),
        (404, {"error": "incorrect_client_credentials"}),
        (400, {"error": "something_new", "error_description": "A made-up reason."}),
        (200, {"error": "device_flow_disabled"}),
    ]

    class Refuses(http.server.BaseHTTPRequestHandler):
        def do_POST(self) -> None:
            status, body = answers.pop(0)
            data = json.dumps(body).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def log_message(self, *args: Any) -> None:
            return

    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Refuses)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        base = f"http://127.0.0.1:{server.server_address[1]}"
        client = GitHubClient(base, base, None)
        said = []
        for _ in range(4):
            with pytest.raises(GitHubError) as caught:
                client.device_code("made-up-client-id")
            said.append(str(caught.value))
        assert "tick Enable Device Flow" in said[0]
        assert "does not know this app's Client ID" in said[1]
        assert "A made-up reason." in said[2]
        assert "tick Enable Device Flow" in said[3]  # the same refusal on a 200 answer
    finally:
        server.shutdown()
