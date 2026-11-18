"""Local and shared projects (the owner, 2026-11-18: "introduce the idea of local projects and shared
projects and put another setting for shared projects folder in settings" / "work a shared project and clone
it into a local project"). projects.json's older key read as the local folder; both folders scanned, each
card Local or Shared, the filter; New project in Shared; Share (no rows, its .git left, the original kept,
then opened); Make a local copy (copied_from, a name taken, no rows); a shared project whose connections only
work here said once. The app never runs git. Made-up data only."""

from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

from swissarmybench.domain import notebooks
from swissarmybench.domain import project_explorer as rules
from tests.conftest import AGENT, AUTH, make_client
from tests.fake_keyring import memory_keyring


@pytest.fixture(autouse=True)
def vault() -> Iterator[None]:
    with memory_keyring():
        yield


def ok(response: Any) -> Any:
    assert response.status_code == 200, response.text
    return response.json()


def project(folder: Path, rows: bool = False, script: str = "") -> Path:
    folder.mkdir(parents=True)
    (folder / "data.ipynb").write_text(notebooks.write_notebook([]), encoding="utf-8")
    (folder / ".sab").mkdir()
    manifest = {"swissarmybench": "project", "format": 1, "tables": []}
    (folder / ".sab" / "project.json").write_text(json.dumps(manifest), encoding="utf-8")
    if rows:
        (folder / ".sab" / "data").mkdir()
        (folder / ".sab" / "data" / "orders.parquet").write_bytes(b"made-up rows")
    if script:
        (folder / "look.py").write_text(script, encoding="utf-8")
    (folder / ".git").mkdir()
    (folder / ".git" / "HEAD").write_text("ref: refs/heads/main\n", encoding="utf-8")
    return folder


def test_where_rules_and_the_older_key() -> None:
    assert rules.read_settings({"folder": "/made-up/projects"})["folder"] == "/made-up/projects"
    settings = rules.read_settings({"local_folder": "/made-up/local", "shared_folder": "/made-up/team"})
    assert (settings["folder"], settings["shared_folder"]) == ("/made-up/local", "/made-up/team")
    written = json.loads(rules.write_settings(settings))
    assert written["local_folder"] == "/made-up/local" and "folder" not in written
    assert rules.where_of("/made-up/team/Close", "/made-up/team") == "shared"
    assert rules.where_of("/made-up/teammates/Close", "/made-up/team") == "local"
    assert rules.where_of("C:\\Team\\Close", "c:/team") == "shared"
    words = "2 connections in this shared project only work on your machine: "
    assert rules.local_only_words(2) == words + "teammates and a Function App can't use them"


def test_two_folders_marks_filter_new_share_and_a_local_copy(tmp_path: Path) -> None:
    local = tmp_path / "home" / "Projects here"
    shared = tmp_path / "team-projects"
    (tmp_path / "state").mkdir()
    (tmp_path / "state" / "projects.json").write_text(json.dumps({"folder": str(local)}), encoding="utf-8")
    project(local / "Q3 review", rows=True)
    project(shared / "Cession close")
    with make_client(tmp_path) as client:
        folders = ok(client.get("/projects/folder", headers=AGENT))
        assert folders["local_folder"] == str(local) and folders["shared_folder"] is None  # the older key
        # No shared folder yet: New project there says what to do.
        refused = client.post("/project/new", json={"name": "Team", "where": "shared"}, headers=AUTH)
        assert refused.status_code == 400 and "Set the shared projects folder in Settings" in refused.text
        ok(client.post("/projects/folder", json={"which": "shared", "folder": str(shared)}, headers=AUTH))
        cards = {c["name"]: c for c in ok(client.get("/projects/explorer", headers=AUTH))["projects"]}
        assert (cards["Q3 review"]["where"], cards["Cession close"]["where"]) == ("local", "shared")
        only = ok(client.get("/projects/explorer?where=shared", headers=AUTH))["projects"]
        assert [c["name"] for c in only] == ["Cession close"]

        # New project in Shared.
        made = ok(client.post("/project/new", json={"name": "Team budget", "where": "shared"}, headers=AGENT))
        assert Path(made["project"]["folder"]) == (shared / "Team budget").resolve()
        ok(client.post("/project/close", json={"discard": True}, headers=AUTH))

        # Share: copied (never .sab/data, nor .git), the original kept, the shared copy opened.
        done = ok(client.post("/projects/share", json={"path": str(local / "Q3 review")}, headers=AUTH))
        copy = shared / "Q3 review"
        assert Path(done["shared"]) == copy.resolve() and done["opened"]
        assert (copy / ".sab" / "project.json").is_file() and not (copy / ".sab" / "data").exists()
        assert not (copy / ".git").exists() and (local / "Q3 review" / ".sab" / "data").is_dir()
        again = client.post("/projects/share", json={"path": str(local / "Q3 review")}, headers=AUTH)
        assert again.status_code == 409 and '"Q3 review 2" is free' in again.text
        ok(client.post("/project/close", json={"discard": True}, headers=AUTH))

        # Make a local copy of a shared project: copied_from, no rows; a name taken asks for another.
        project(local / "Cession close")
        taken = client.post(
            "/projects/copy-local", json={"path": str(shared / "Cession close")}, headers=AGENT
        )
        assert taken.status_code == 409 and '"Cession close 2" is free' in taken.text
        body = {"path": str(shared / "Cession close"), "name": "Cession close mine"}
        copied = ok(client.post("/projects/copy-local", json=body, headers=AGENT))
        mine = local / "Cession close mine"
        assert Path(copied["copied"]) == mine.resolve() and copied["opened"]
        assert json.loads((mine / ".sab" / "project.json").read_text())["copied_from"] == "Cession close"
        ok(client.post("/project/save", json={}, headers=AUTH))  # a save keeps it
        assert json.loads((mine / ".sab" / "project.json").read_text())["copied_from"] == "Cession close"
        cards = {c["name"]: c for c in ok(client.get("/projects/explorer", headers=AUTH))["projects"]}
        assert cards["Cession close mine"]["copied_from"] == "Cession close"
        assert cards["Cession close mine"]["where"] == "local"
        assert (shared / "Cession close" / ".git" / "HEAD").is_file()  # the shared one untouched


def test_a_shared_projects_connections_that_only_work_here_are_said(tmp_path: Path) -> None:
    shared = tmp_path / "team-projects"
    body = {
        "name": "Warehouse",
        "kind": "sql",
        "template": "sqlite",
        "dialect": "sqlite",
        "code": 'import sqlite3\nconn = sqlite3.connect(r"/made-up/warehouse.sqlite")\n',
    }
    project(shared / "Close", script='import swissarmybench as sab\nconn = sab.connection("Warehouse")\n')
    with make_client(tmp_path) as client:
        ok(client.post("/connections", json=body, headers=AUTH))
        ok(client.post("/projects/folder", json={"which": "shared", "folder": str(shared)}, headers=AUTH))
        ok(client.post("/project/open", json={"path": str(shared / "Close")}, headers=AUTH))
        notices = [n["text"] for n in ok(client.get("/library", headers=AUTH))["notices"]]
        assert "1 connection in this shared project only works on your machine" in " ".join(notices)
        # The setup checklist lists a shared project whose connections are not set up here.
        ok(client.delete("/blades/Warehouse", headers=AUTH))
        ok(client.post("/connections", json=body | {"name": "Ledger"}, headers=AUTH))
        (shared / "Close" / "look.py").write_text('import swissarmybench as sab\nsab.connection("Ledger")\n')
        assert ok(client.get("/library/setup", headers=AUTH))["projects"] == []  # Ledger works here
        needs = body | {
            "name": "Ledger",
            "code": 'import sqlite3\nassert secret("LEDGER_PW")\nconn = sqlite3.connect(":memory:")\n',
        }
        ok(client.put("/connections/Ledger", json=needs, headers=AUTH))
        setup = ok(client.get("/library/setup", headers=AUTH))
        assert setup["projects"] == [
            {"name": "Close", "folder": str((shared / "Close").resolve()), "connections": ["Ledger"],
             "words": "Close needs Ledger set up here"}
        ]  # fmt: skip
