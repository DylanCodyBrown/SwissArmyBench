"""What belongs to the open project (services/project_scope.py, services/sab_projects.py; the owner,
2026-11-16): a new project is saved first; autosave saves after a change, and not when off; notebooks,
scripts, apps and saved dashboards are each project's own, while connections and blades are the library's
(Plans/library.plan.md, 2026-11-17: every project has them); importing copies documents in and an older
project's connections and blades into the library; a .sab never holds a password, whether it comes from
the keyring, a vault or an environment variable. Made-up data only."""

from __future__ import annotations

import json
import os
import time
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


def entries(folder: Path) -> dict[str, bytes]:
    """A project folder's files, by their path in it."""
    return {
        p.relative_to(folder).as_posix(): p.read_bytes() for p in sorted(folder.rglob("*")) if p.is_file()
    }


def manifest_of(folder: Path) -> dict[str, Any]:
    return dict(json.loads((folder / ".sab" / "project.json").read_text(encoding="utf-8")))


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
    # Test app one (BI review): the scaffold's own files are made too (the outline listed adapter.py's
    # every name as a deliverable script of the user's); a script of the user's is not.
    scaffold = rules.documents([(f, 1, 0.0) for f in ("adapter.py", "connections.py", "sandbox_data.py",
                                                      "scripts/adapter.py", "report.py")])  # fmt: skip
    assert {d["path"]: d["made"] for d in scaffold} == {
        "adapter.py": True, "connections.py": True, "sandbox_data.py": True, "scripts/adapter.py": False,
        "report.py": False,
    }  # fmt: skip
    assert [d["path"] for d in rules.documents([("a.py", 1, 0.0), ("b.ipynb", 1, 0.0)], "script")] == ["a.py"]
    # The project scaffold's made files, the sandbox mirror and an API export are made too (the landing page
    # and the agent's project_documents never offer adapter.py as a script of the user's); API.py is theirs.
    scaffold = ["adapter.py", "connections.py", "sandbox_data.py", "sandbox_connections.py"]
    files = [*scaffold, "exports/api/fastapi/main.py", "API.py", "scripts/visits.py"]
    made = {d["path"]: d["made"] for d in rules.documents([(f, 1, 0.0) for f in files], "script")}
    assert made == dict.fromkeys([*scaffold, "exports/api/fastapi/main.py"], True) | {
        "API.py": False,
        "scripts/visits.py": False,
    }
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
        assert refused.status_code == 400 and "name" in refused.text
        old = client.post("/project/new", json={"path": str(tmp_path / "nowhere" / "a.sab")}, headers=AUTH)
        assert old.status_code == 400 and state(client)["project"] is None
        target = tmp_path / "plans"
        made = ok(client.post("/project/new", json={"path": str(target), "autosave": False}, headers=AUTH))
        assert made["saved"] == str(target) and (target / ".sab" / "project.json").is_file()
        assert made["project"]["name"] == "plans" and made["project"]["dirty"] is False
        assert made["project"]["autosave"] is False
        assert json.loads((target / ".sab" / "project.json").read_text())["autosave"] is False
        assert [r["path"] for r in made["recent"]] == [str(target)]


def test_autosave_saves_after_a_change_and_not_when_off(tmp_path: Path) -> None:
    with make_client(tmp_path, autosave_seconds=0.05) as client:
        target = tmp_path / "auto"
        ok(client.post("/project/new", json={"path": str(target), "autosave": False}, headers=AUTH))
        # Off: a change stays unsaved.
        ok(client.post("/datasets/orders/load", json={"path": str(csv_file(tmp_path))}, headers=AUTH))
        time.sleep(0.6)
        assert state(client)["project"]["dirty"] is True
        assert "orders" not in json.dumps(manifest_of(target)["tables"])
        # On: kept in the file at once (project.json only), then the change saves quietly.
        switched = ok(client.post("/project/autosave", json={"on": True}, headers=AUTH))["project"]
        assert switched["autosave"] is True
        for _ in range(100):
            if not state(client)["project"]["dirty"]:
                break
            time.sleep(0.05)
        manifest = manifest_of(target)
        assert manifest["autosave"] is True and [t["name"] for t in manifest["tables"]] == ["orders"]
        # Off again: the switch is kept, the next change waits for Save.
        ok(client.post("/project/autosave", json={"on": False}, headers=AUTH))
        assert manifest_of(target)["autosave"] is False
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


def test_a_projects_notebooks_are_its_data_notebook_and_plain_ones() -> None:
    """In a project, data.ipynb (at its top) is THE data notebook; every other notebook is plain (app
    notebooks went, 2026-11-21: widgets on the Canvas replaced them)."""
    listed = [
        {"path": "data.ipynb", "kind": "notebook"},
        {"path": "views/sales.ipynb", "kind": "notebook"},
        {"path": "scratch.ipynb", "kind": "notebook"},
        {"path": "Data.IPYNB", "kind": "notebook"},
        {"path": "more/data.ipynb", "kind": "notebook"},
        {"path": "tidy.py", "kind": "script"},
        {"path": "shop.stapp.json", "kind": "app"},
    ]
    assert rules.notebook_roles(listed) == {
        "data.ipynb": "data",
        "Data.IPYNB": "data",  # one data notebook: the project's own, at its top (more/data.ipynb is plain)
    }


def test_a_notebooks_kind_inside_a_project_and_outside_one() -> None:
    """A notebook's kind by its whole path and the open project's folder: outside a project a notebook
    is plain (data.ipynb stays the data notebook: its Data mode is its own)."""
    folder = "/work/orchard"
    assert rules.notebook_kind("/work/orchard/data.ipynb", folder) == "data"
    assert rules.notebook_kind("/work/orchard/views/sales.ipynb", folder) == ""
    assert rules.notebook_kind("/work/orchard/views/data.ipynb", folder) == ""
    assert rules.notebook_kind("/elsewhere/scratch.ipynb", folder) == ""
    assert rules.notebook_kind("/elsewhere/scratch.ipynb", None) == ""
    assert rules.notebook_kind("/elsewhere/data.ipynb", None) == "data"
    assert rules.notebook_kind("C:\\work\\orchard\\one.ipynb", "C:\\work\\orchard") == ""
    assert rules.notebook_kind("/work/orchardist/one.ipynb", folder) == ""
    assert rules.notebook_kind("/work/orchard/tidy.py", folder) is None  # not a notebook


# ===== scope =====


def test_documents_and_dashboards_are_each_projects_own_connections_and_blades_the_librarys(
    tmp_path: Path,
) -> None:
    with make_client(tmp_path) as client:
        first = tmp_path / "first"
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
        assert [d.get("role") for d in documents["documents"]] == [None, "data"]
        assert documents["documents"][0]["full"] == str(Path(made["folder"]) / "analysis.ipynb")
        assert client.get("/project/documents?kind=sheet", headers=AUTH).status_code == 400
        ok(client.post("/project/save", json={}, headers=AUTH))
        inside = entries(first)
        assert not any(n.startswith(".sab/blades/") for n in inside)  # the library's, never the project's
        assert any(n.startswith(".sab/visualizations/") for n in inside)

        second = tmp_path / "second"
        ok(client.post("/project/new", json={"path": str(second)}, headers=AUTH))
        names = {b["name"] for b in ok(client.get("/blades", headers=AUTH))["blades"]}
        assert {"Warehouse", "Typed"} <= names  # every project has the library
        assert [c["name"] for c in ok(client.get("/connections", headers=AUTH))["connections"]] == [
            "Warehouse"
        ]
        assert ok(client.get("/dashboards", headers=AUTH))["dashboards"] == []
        listed = ok(client.get("/project/documents", headers=AUTH))["documents"]
        assert "analysis.ipynb" not in {d["path"] for d in listed}

        # The first again: its dashboards are back, from its file.
        ok(client.post("/project/open", json={"path": str(first)}, headers=AUTH))
        assert [d["name"] for d in ok(client.get("/dashboards", headers=AUTH))["dashboards"]] == ["Quarter"]
        ok(client.post("/project/close", json={"discard": True}, headers=AUTH))
        assert {"Warehouse", "Typed"} <= {
            b["name"] for b in ok(client.get("/blades", headers=AUTH))["blades"]
        }
        assert ok(client.get("/project/documents", headers=AUTH)) == {"project": None, "documents": []}


def _with_own_blades(path: Path, blades: list[dict[str, Any]]) -> None:
    """An older app's project: its own connections and blades in .sab/blades."""
    (path / ".sab" / "blades").mkdir(parents=True, exist_ok=True)
    for i, blade in enumerate(blades):
        (path / ".sab" / "blades" / f"blade-{i}.json").write_text(json.dumps(blade), encoding="utf-8")


# ===== import =====


def test_import_copies_documents_connections_and_blades(tmp_path: Path) -> None:
    with make_client(tmp_path) as client:
        source = tmp_path / "source"
        made = ok(client.post("/project/new", json={"path": str(source)}, headers=AUTH))["project"]
        Path(made["folder"], "analysis.ipynb").write_text(notebook("print('made up')"), encoding="utf-8")
        Path(made["folder"], "load.py").write_text("print('load')\n", encoding="utf-8")
        ok(client.post("/project/save", json={}, headers=AUTH))
        ok(client.post("/project/close", json={"discard": True}, headers=AUTH))
        # An older app's project: its own connection and blade in the file.
        shop = warehouse() | {"variable": "conn", "catalog": None}
        shop.pop("secrets")
        _with_own_blades(source, [shop, {"name": "Typed", "kind": "secret", "env_names": ["API_KEY"]}])

        target = tmp_path / "target"
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
        # Into the library: its password is this computer's keyring's, by the connection's name (none yet).
        assert done["connections"] == ["Warehouse"] and done["needs_password"]["Warehouse"]["missing"] == [
            "password"
        ]
        assert "Warehouse" in {c["name"] for c in ok(client.get("/connections", headers=AUTH))["connections"]}
        # The same one again: skipped, and said (never overwritten).
        again = ok(
            client.post(
                "/project/import", json={"from": str(source), "connections": ["Warehouse"]}, headers=AUTH
            )
        )
        assert again["connections"] == [] and again["skipped"] == ["Warehouse"]
        # "This computer" is no place to import from: its connections are the library's.
        assert (
            client.post("/project/import/sources", json={"from": "computer"}, headers=AUTH).status_code == 400
        )

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
            == 404  # no project open to copy into
        )


def test_no_password_is_ever_in_the_file_whatever_its_source(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("WAREHOUSE_ENV_PASSWORD", ENV_SECRET)
    with make_client(tmp_path) as client:
        target = tmp_path / "secrets"
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
        everything = b"".join(entries(target).values())
        for value in (KEYRING_SECRET, VAULT_SECRET, ENV_SECRET):
            assert value.encode() not in everything, value
        assert [n for n in entries(target) if n.startswith(".sab/blades/")] == []
        library = b"".join(p.read_bytes() for p in (tmp_path / "state" / "library").rglob("*") if p.is_file())
        for value in (KEYRING_SECRET, VAULT_SECRET, ENV_SECRET):
            assert value.encode() not in library, value
    monkeypatch.delenv("WAREHOUSE_ENV_PASSWORD")
    assert os.environ.get("WAREHOUSE_ENV_PASSWORD") is None
