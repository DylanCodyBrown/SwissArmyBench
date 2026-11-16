"""What belongs to the open project (services/project_scope.py, services/sab_projects.py; the owner,
2026-11-16): a new project is saved first; autosave saves after a change, and not when off; notebooks,
scripts, apps, connections, blades and saved dashboards are each project's own; importing copies them in
(from another .sab, a project folder, a loose file, or this computer's saved connections); a .sab never
holds a password, whether it comes from the keyring, a vault or an environment variable. Made-up data
only."""

from __future__ import annotations

import json
import os
import time
import zipfile
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from starlette.testclient import TestClient

from swissarmybench.domain import notebooks
from swissarmybench.domain import project_scope as rules
from tests.conftest import AGENT, AUTH, make_client
from tests.fake_keyring import memory_keyring

KEYRING_SECRET = "made-up-keyring-pa55"
VAULT_SECRET = "made-up-vault-s3cret"
ENV_SECRET = "made-up-env-passw0rd"


@pytest.fixture(autouse=True)
def vault() -> Iterator[None]:
    with memory_keyring():
        yield


def ok(response: Any) -> Any:
    assert response.status_code == 200, response.text
    return response.json()


def state(client: TestClient) -> dict[str, Any]:
    return dict(ok(client.get("/project", headers=AUTH)))


def entries(path: Path) -> dict[str, bytes]:
    with zipfile.ZipFile(path) as read:
        return {name: read.read(name) for name in read.namelist()}


def csv_file(tmp_path: Path) -> Path:
    csv = tmp_path / "orders.csv"
    csv.write_text("order_id,region,units\n1,North,3\n2,East,9\n", encoding="utf-8")
    return csv


def warehouse(name: str = "Warehouse") -> dict[str, Any]:
    """A made-up SQLite connection whose password is saved in this computer's keyring."""
    return {
        "name": name,
        "kind": "sql",
        "template": "sqlite",
        "dialect": "sqlite",
        "code": 'import sqlite3\nassert secret("password")\nconn = sqlite3.connect(":memory:")\n',
        "secrets": {"password": KEYRING_SECRET},
    }


def notebook(text: str) -> str:
    return notebooks.write_notebook([notebooks.Cell("code", text)])


# ===== the rules =====


def test_free_names_and_the_documents_of_a_project() -> None:
    assert rules.free_name("analysis.ipynb", ["data.ipynb"]) == "analysis.ipynb"
    assert rules.free_name("analysis.ipynb", ["Analysis.ipynb", "analysis 2.ipynb"]) == "analysis 3.ipynb"
    assert rules.free_name("pages/a.py", ["pages/a.py"]) == "pages/a 2.py"
    assert rules.free_name("sales.stapp.json", ["sales.stapp.json"]) == "sales 2.stapp.json"
    listed = rules.documents(
        [
            ("data.py", 1, 0.0),
            ("data.ipynb", 1, 0.0),
            ("b.ipynb", 1, 0.0),
            ("s.stapp.json", 1, 0.0),
            ("notes.md", 1, 0.0),
            (".sab/blades/x.json", 1, 0.0),
        ]
    )
    assert [(d["path"], d["kind"], d["made"]) for d in listed] == [
        ("b.ipynb", "notebook", False),
        ("data.ipynb", "notebook", False),
        ("data.py", "script", True),
        ("s.stapp.json", "app", False),
    ]
    assert [d["path"] for d in rules.documents([("a.py", 1, 0.0), ("b.ipynb", 1, 0.0)], "script")] == ["a.py"]
    with pytest.raises(rules.ScopeError):
        rules.documents([], "spreadsheet")
    assert rules.app_entry(".sab/blades/warehouse-1.json") and rules.app_entry(".sab/dashboards/q1.json")
    assert not rules.app_entry(".sab/other/x.json") and not rules.app_entry(".sab/blades/a/b.json")


def test_a_password_needs_a_source_on_this_computer() -> None:
    def present(name: str) -> bool:
        return name == "SET_HERE"

    def covered(name: str) -> bool:
        return name == "FROM_VAULT"

    secrets = {"password": False, "SET_HERE": False, "FROM_VAULT": False, "saved": True, "TYPED": False}
    variables = {"TOKEN": {"from": "env", "env": "API_TOKEN"}, "PLAIN": {"from": "value", "value": "x"}}
    missing = rules.needs_passwords(secrets, variables, present, covered, ["TYPED"])
    assert missing == ["password", "API_TOKEN"]


# ===== new, autosave =====


def test_a_new_project_is_saved_first_and_opens_its_grids_with_no_tables(tmp_path: Path) -> None:
    with make_client(tmp_path) as client:
        refused = client.post("/project/new", json={}, headers=AUTH)
        assert refused.status_code == 400 and "path" in refused.text
        gone = client.post("/project/new", json={"path": str(tmp_path / "nowhere" / "a.sab")}, headers=AUTH)
        assert gone.status_code == 404 and state(client)["project"] is None
        made = ok(client.post("/project/new", json={"path": str(tmp_path / "plans")}, headers=AUTH))
        target = tmp_path / "plans.sab"
        assert made["saved"] == str(target) and target.is_file()
        assert made["project"]["name"] == "plans" and made["project"]["dirty"] is False
        assert made["project"]["autosave"] is False
        assert json.loads(entries(target)["project.json"])["autosave"] is False
        assert [r["path"] for r in made["recent"]] == [str(target)]


def test_autosave_saves_after_a_change_and_not_when_off(tmp_path: Path) -> None:
    with make_client(tmp_path, autosave_seconds=0.05) as client:
        target = tmp_path / "auto.sab"
        ok(client.post("/project/new", json={"path": str(target)}, headers=AUTH))
        # Off: a change stays unsaved.
        ok(client.post("/datasets/orders/load", json={"path": str(csv_file(tmp_path))}, headers=AUTH))
        time.sleep(0.6)
        assert state(client)["project"]["dirty"] is True
        assert "orders" not in json.dumps(json.loads(entries(target)["project.json"])["tables"])
        # On: kept in the file at once (project.json only), then the change saves quietly.
        switched = ok(client.post("/project/autosave", json={"on": True}, headers=AUTH))["project"]
        assert switched["autosave"] is True
        for _ in range(100):
            if not state(client)["project"]["dirty"]:
                break
            time.sleep(0.05)
        manifest = json.loads(entries(target)["project.json"])
        assert manifest["autosave"] is True and [t["name"] for t in manifest["tables"]] == ["orders"]
        # Off again: the switch is kept, the next change waits for Save.
        ok(client.post("/project/autosave", json={"on": False}, headers=AUTH))
        assert json.loads(entries(target)["project.json"])["autosave"] is False
        ok(client.post("/datasets/more/paste", content="a\tb\n1\t2\n", headers=AUTH))
        time.sleep(0.6)
        assert state(client)["project"]["dirty"] is True
        assert client.post("/project/autosave", json={"on": "yes"}, headers=AUTH).status_code == 400
    # Opened again: the switch as the file keeps it.
    with make_client(tmp_path / "again") as client:
        assert (
            ok(client.post("/project/open", json={"path": str(target)}, headers=AGENT))["project"]["autosave"]
            is False
        )


# ===== scope =====


def test_a_second_project_sees_none_of_the_firsts_own(tmp_path: Path) -> None:
    with make_client(tmp_path) as client:
        before = {b["name"] for b in ok(client.get("/blades", headers=AUTH))["blades"]}
        first = tmp_path / "first.sab"
        made = ok(client.post("/project/new", json={"path": str(first)}, headers=AUTH))["project"]
        Path(made["folder"], "analysis.ipynb").write_text(notebook("print(1)"), encoding="utf-8")
        ok(client.post("/connections", json=warehouse(), headers=AUTH))
        ok(
            client.post(
                "/blades", json={"name": "Typed", "kind": "secret", "env_names": ["API_KEY"]}, headers=AUTH
            )
        )
        ok(client.post("/cards", json={"kind": "note", "title": "Made-up", "body": "x"}, headers=AUTH))
        ok(client.post("/dashboards", json={"name": "Quarter"}, headers=AUTH))
        documents = ok(client.get("/project/documents?kind=notebook", headers=AUTH))
        assert [d["path"] for d in documents["documents"]] == ["analysis.ipynb", "data.ipynb"]
        assert documents["documents"][0]["full"] == str(Path(made["folder"]) / "analysis.ipynb")
        assert client.get("/project/documents?kind=sheet", headers=AUTH).status_code == 400
        ok(client.post("/project/save", json={}, headers=AUTH))
        inside = entries(first)
        assert any(n.startswith(".sab/blades/") for n in inside)
        assert any(n.startswith(".sab/dashboards/") for n in inside)

        second = tmp_path / "second.sab"
        ok(client.post("/project/new", json={"path": str(second)}, headers=AUTH))
        names = {b["name"] for b in ok(client.get("/blades", headers=AUTH))["blades"]}
        assert "Warehouse" not in names and "Typed" not in names
        assert ok(client.get("/connections", headers=AUTH))["connections"] == []
        assert ok(client.get("/dashboards", headers=AUTH))["dashboards"] == []
        listed = ok(client.get("/project/documents", headers=AUTH))["documents"]
        assert "analysis.ipynb" not in {d["path"] for d in listed}

        # The first again: its own are back, from its file.
        ok(client.post("/project/open", json={"path": str(first)}, headers=AUTH))
        names = {b["name"] for b in ok(client.get("/blades", headers=AUTH))["blades"]}
        assert {"Warehouse", "Typed"} <= names
        assert [d["name"] for d in ok(client.get("/dashboards", headers=AUTH))["dashboards"]] == ["Quarter"]
        # No project: this computer's own, as before projects held them.
        ok(client.post("/project/close", json={"discard": True}, headers=AUTH))
        assert {b["name"] for b in ok(client.get("/blades", headers=AUTH))["blades"]} == before
        assert ok(client.get("/project/documents", headers=AUTH)) == {"project": None, "documents": []}


# ===== import =====


def test_import_copies_documents_connections_and_blades(tmp_path: Path) -> None:
    with make_client(tmp_path) as client:
        # This computer's saved connection (made before projects held their own).
        ok(client.post("/connections", json=warehouse("Old warehouse"), headers=AUTH))
        source = tmp_path / "source.sab"
        made = ok(client.post("/project/new", json={"path": str(source)}, headers=AUTH))["project"]
        Path(made["folder"], "analysis.ipynb").write_text(notebook("print('made up')"), encoding="utf-8")
        Path(made["folder"], "load.py").write_text("print('load')\n", encoding="utf-8")
        ok(client.post("/connections", json=warehouse(), headers=AUTH))
        ok(
            client.post(
                "/blades", json={"name": "Typed", "kind": "secret", "env_names": ["API_KEY"]}, headers=AUTH
            )
        )
        ok(client.post("/project/save", json={}, headers=AUTH))

        target = tmp_path / "target.sab"
        made = ok(client.post("/project/new", json={"path": str(target)}, headers=AUTH))["project"]
        folder = Path(made["folder"])
        Path(folder, "analysis.ipynb").write_text(notebook("print('mine')"), encoding="utf-8")
        offered = ok(client.post("/project/import/sources", json={"from": str(source)}, headers=AUTH))
        assert {d["path"] for d in offered["documents"]} >= {"analysis.ipynb", "load.py", "data.ipynb"}
        assert [c["name"] for c in offered["connections"]] == ["Warehouse"]
        assert [b["name"] for b in offered["blades"]] == ["Typed"]
        refused = client.post("/project/import", json={"from": str(source)}, headers=AUTH)
        assert refused.status_code == 400
        missing = client.post(
            "/project/import", json={"from": str(source), "documents": ["x.ipynb"]}, headers=AUTH
        )
        assert missing.status_code == 400 and "x.ipynb" in missing.text
        done = ok(
            client.post(
                "/project/import",
                json={
                    "from": str(source),
                    "documents": ["analysis.ipynb", "load.py"],
                    "connections": ["Warehouse"],
                },
                headers=AUTH,
            )
        )
        # The project's own analysis.ipynb stays: the copy takes the next free name.
        assert [d["path"] for d in done["documents"]] == ["analysis 2.ipynb", "load.py"]
        assert "made up" in Path(folder, "analysis 2.ipynb").read_text(encoding="utf-8")
        assert "mine" in Path(folder, "analysis.ipynb").read_text(encoding="utf-8")
        assert done["connections"] == ["Warehouse"] and done["needs_password"] == {}
        assert "Warehouse" in {c["name"] for c in ok(client.get("/connections", headers=AUTH))["connections"]}
        # A name the project has is never overwritten: skipped, and said.
        again = ok(
            client.post(
                "/project/import", json={"from": str(source), "connections": ["Warehouse"]}, headers=AUTH
            )
        )
        assert again["connections"] == [] and again["skipped"] == ["Warehouse"]

        # This computer's saved ones.
        computer = ok(client.post("/project/import/sources", json={"from": "computer"}, headers=AUTH))
        assert [c["name"] for c in computer["connections"]] == ["Old warehouse"] and computer[
            "documents"
        ] == []
        ok(
            client.post(
                "/project/import", json={"from": "computer", "connections": ["old warehouse"]}, headers=AUTH
            )
        )
        assert "Old warehouse" in {
            c["name"] for c in ok(client.get("/connections", headers=AUTH))["connections"]
        }

        # A loose notebook from outside: a copy into the project (the original stays where it is).
        loose = tmp_path / "loose.ipynb"
        loose.write_text(notebook("print('loose')"), encoding="utf-8")
        copied = ok(client.post("/project/import", json={"from": str(loose)}, headers=AUTH))
        assert copied["documents"][0]["path"] == "loose.ipynb" and loose.is_file()
        assert Path(copied["documents"][0]["full"]).parent == folder

        # A project folder (today's kind) is a source too.
        project_folder = tmp_path / "folder_project"
        project_folder.mkdir()
        (project_folder / "report.ipynb").write_text(notebook("print('report')"), encoding="utf-8")
        listed = ok(client.post("/project/import/sources", json={"from": str(project_folder)}, headers=AUTH))
        assert [d["path"] for d in listed["documents"]] == ["report.ipynb"]
        ok(
            client.post(
                "/project/import",
                json={"from": str(project_folder), "documents": ["report.ipynb"]},
                headers=AGENT,
            )
        )
        assert (folder / "report.ipynb").is_file()

        # Saved and opened again, the imports are the project's.
        ok(client.post("/project/save", json={}, headers=AUTH))
        inside = entries(target)
        assert {"analysis 2.ipynb", "load.py", "loose.ipynb", "report.ipynb"} <= set(inside)
    with make_client(tmp_path / "elsewhere") as client:
        assert (
            client.post(
                "/project/import", json={"from": str(source), "documents": ["load.py"]}, headers=AUTH
            ).status_code
            == 404
        )


def test_no_password_is_ever_in_the_file_whatever_its_source(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("WAREHOUSE_ENV_PASSWORD", ENV_SECRET)
    with make_client(tmp_path) as client:
        target = tmp_path / "secrets.sab"
        ok(client.post("/project/new", json={"path": str(target)}, headers=AUTH))
        # From the keyring.
        ok(client.post("/connections", json=warehouse(), headers=AUTH))
        # From a vault's entry (the vault's own code is made up: it gives a value it was told).
        vault = {
            "name": "Team vault",
            "kind": "vault",
            "code": "import os\n\ndef get(name):\n    return os.environ.get('MADE_UP_VAULT', '')",
            "variable": "get",
            "vault_mapping": [{"env": "VAULT_PASSWORD", "secret": "warehouse-pw"}],
        }
        ok(client.post("/blades", json=vault, headers=AUTH))
        from_vault = warehouse("Vaulted") | {"secrets": {}}
        from_vault["code"] = (
            'import sqlite3\nassert secret("VAULT_PASSWORD")\nconn = sqlite3.connect(":memory:")\n'
        )
        ok(client.post("/connections", json=from_vault, headers=AUTH))
        # From an environment variable.
        from_env = warehouse("Environment") | {"secrets": {}}
        from_env["code"] = (
            'import sqlite3\nassert secret("WAREHOUSE_ENV_PASSWORD")\nconn = sqlite3.connect(":memory:")\n'
        )
        ok(client.post("/connections", json=from_env, headers=AUTH))
        listed = {c["name"]: c for c in ok(client.get("/connections", headers=AUTH))["connections"]}
        assert all(listed[n]["needs_password"] is None for n in ("Warehouse", "Vaulted", "Environment"))
        ok(client.post("/project/save", json={}, headers=AUTH))
        raw = target.read_bytes()
        everything = b"".join(entries(target).values())
        for value in (KEYRING_SECRET, VAULT_SECRET, ENV_SECRET):
            assert value.encode() not in everything and value.encode() not in raw, value
        assert len([n for n in entries(target) if n.startswith(".sab/blades/")]) == 4
    # Another computer, with none of those: each says so, with its fix.
    monkeypatch.delenv("WAREHOUSE_ENV_PASSWORD")
    with memory_keyring(), make_client(tmp_path / "other") as client:
        ok(client.post("/project/open", json={"path": str(target)}, headers=AUTH))
        listed = {c["name"]: c for c in ok(client.get("/connections", headers=AUTH))["connections"]}
        assert listed["Warehouse"]["needs_password"]["missing"] == ["password"]
        assert listed["Environment"]["needs_password"]["fix"] == {
            "kind": "password",
            "label": "Set the password",
            "connection": "Environment",
        }
        assert listed["Vaulted"]["needs_password"] is None  # its vault came with the project
    assert os.environ.get("WAREHOUSE_ENV_PASSWORD") is None
