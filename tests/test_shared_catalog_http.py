"""The shared catalog over HTTP (services/shared_catalog.py): the library's catalog/<connection>.json,
written on the events (a connection saved, its tables listed, relationships imported or deleted, a project
saved), pruned (a connection deleted, a table no longer listed; never after a failed listing), and read again
when the user's pull changes the folder (the pages told). A bad file is said and never written over.
Made-up data only."""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pyarrow as pa
import pytest
from starlette.testclient import TestClient

from tests.conftest import AGENT, AUTH, PORT, make_client, push
from tests.fake_keyring import memory_keyring

HOST = {"Host": f"127.0.0.1:{PORT}"}
PASSWORD = "made-up-catalog-pa55"
ROW_VALUE = "Zanzibar-Gold-77"
CATALOG = (
    "SELECT 'main' AS table_schema, m.name AS table_name, m.type AS table_type, p.name AS column_name, "
    "p.type AS data_type, 'YES' AS is_nullable, p.cid + 1 AS ordinal_position "
    "FROM sqlite_master AS m JOIN pragma_table_info(m.name) AS p "
    "WHERE m.type = 'table' ORDER BY m.name, p.cid"
)


@pytest.fixture(autouse=True)
def vault() -> Iterator[None]:
    with memory_keyring():
        yield


def ok(response: Any) -> Any:
    assert response.status_code == 200, response.text
    return response.json()


def database(path: Path) -> None:
    with sqlite3.connect(path) as made:
        made.execute("CREATE TABLE orders (id INTEGER PRIMARY KEY, customer_id INTEGER, label TEXT)")
        made.execute("CREATE TABLE customers (id INTEGER PRIMARY KEY, region TEXT)")
        made.execute("INSERT INTO orders VALUES (1, 1, ?)", (ROW_VALUE,))
        made.execute("INSERT INTO customers VALUES (1, 'North')")


def warehouse(client: TestClient, path: Path) -> None:
    body = {
        "name": "Warehouse",
        "kind": "sql",
        "template": "sqlite",
        "dialect": "sqlite",
        "code": (
            "import sqlite3\nfrom pathlib import Path\n\n"
            'assert secret("password")\n'
            f'path = Path(r"{path}")\n'
            'conn = sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True)\n'
        ),
        "catalog": {"language": "sql", "command": CATALOG},
        "secrets": {"password": PASSWORD},
    }
    ok(client.post("/connections", json=body, headers=AUTH))


def catalog_file(tmp_path: Path, name: str = "warehouse.json") -> Path:
    return tmp_path / "state" / "library" / "catalog" / name


def test_saved_listed_imported_deleted_and_never_a_value_or_a_secret(tmp_path: Path) -> None:
    db = tmp_path / "warehouse.sqlite"
    database(db)
    with make_client(tmp_path) as client:
        warehouse(client, db)
        file = catalog_file(tmp_path)
        saved = json.loads(file.read_text())
        assert (saved["connection"], saved["kind"], saved["template"], saved["tables"]) == (
            "Warehouse",
            "database",
            "sqlite",
            {},
        )
        ok(client.post("/blades/Warehouse/refresh", json={}, headers=AUTH))
        listed = json.loads(file.read_text())["tables"]
        assert set(listed) == {"main.customers", "main.orders"}
        assert [c["name"] for c in listed["main.orders"]["columns"]] == ["id", "customer_id", "label"]
        text = file.read_text()
        assert PASSWORD not in text and ROW_VALUE not in text and "North" not in text
        assert str(db) not in text  # the connection's own file holds where it is, not the catalog

        # The relationships in use: added to its tables, keys marked; a deleted one goes.
        model = {
            "name": "Warehouse keys",
            "tables": {
                "orders": {"primary_key": ["id"], "source": "connection:Warehouse"},
                "customers": {"primary_key": ["id"], "source": "connection:Warehouse"},
            },
            "relationships": [
                {"from": "orders", "from_columns": ["customer_id"], "to": "customers", "to_columns": ["id"]}
            ],
        }
        ok(client.post("/relationships", json={"model": model}, headers=AGENT))
        orders = json.loads(file.read_text())["tables"]["main.orders"]
        assert orders["primary_key"] == ["id"]
        assert orders["relationships"][0]["to"] == "customers"
        assert {c["name"]: c.get("key") for c in orders["columns"]}["customer_id"] == "foreign"
        # The agent reads what the user reads.
        shared = ok(client.get("/shared-catalog", headers=AGENT))
        assert shared["connections"][0]["connection"] == "Warehouse" and shared["connections"][0]["here"]
        one = ok(client.get("/shared-catalog/table?connection=warehouse&table=orders", headers=AGENT))
        assert one["key"] == "main.orders" and one["relationships"][0]["from_columns"] == ["customer_id"]
        assert (
            client.get("/shared-catalog/table?connection=Warehouse&table=nope", headers=AGENT).status_code
            == 404
        )
        joins = [{"from": "orders", "from_columns": ["customer_id"], "to": "customers", "to_columns": ["id"]}]
        ok(client.post("/relationships/delete", json={"joins": joins}, headers=AUTH))
        assert json.loads(file.read_text())["tables"]["main.orders"]["relationships"] == []

        # A table dropped at the source: the next successful listing marks it gone since today.
        with sqlite3.connect(db) as made:
            made.execute("DROP TABLE customers")
        ok(client.post("/blades/Warehouse/refresh", json={}, headers=AUTH))
        customers = json.loads(file.read_text())["tables"]["main.customers"]
        assert customers["state"] == "gone" and customers["gone_since"]
        # A listing that fails (the database is not there) changes nothing.
        before = file.read_bytes()
        db.rename(tmp_path / "moved.sqlite")
        assert client.post("/blades/Warehouse/refresh", json={}, headers=AUTH).status_code != 200
        assert file.read_bytes() == before

        # The connection deleted: its file goes.
        ok(client.delete("/blades/Warehouse", headers=AUTH))
        assert not file.exists()
        assert ok(client.get("/shared-catalog", headers=AUTH))["connections"] == []


def teammate(tables: dict[str, Any] | None = None) -> str:
    """A teammate's catalog file, as their app wrote it (made-up)."""
    found = tables or {
        "dbo.Invoices": {
            "name": "Invoices",
            "schema": "dbo",
            "database": "",
            "kind": "table",
            "columns": [
                {"name": "InvoiceId", "type": "INT", "key": "primary"},
                {"name": "CedantId", "type": "INT"},
            ],
            "primary_key": ["InvoiceId"],
            "relationships": [],
            "used_by": ["Cession statements"],
            "state": "present",
        }
    }
    return json.dumps(
        {
            "format": 1,
            "connection": "Finance Captive",
            "kind": "database",
            "template": "sqlserver",
            "tables": found,
        },
        indent=2,
    )


def test_a_pull_is_picked_up_and_told_and_a_bad_file_is_said_and_left_alone(tmp_path: Path) -> None:
    db = tmp_path / "warehouse.sqlite"
    database(db)
    with make_client(tmp_path) as client:
        warehouse(client, db)
        ok(client.post("/blades/Warehouse/refresh", json={}, headers=AUTH))
        folder = catalog_file(tmp_path).parent
        with client.websocket_connect("/ws?catalog=1", headers=AUTH | HOST) as page:
            (folder / "finance_captive.json").write_text(teammate(), encoding="utf-8")
            answer = ok(client.post("/shared-catalog/refresh", headers=AGENT))
            assert answer["changed"] == ["catalog/finance_captive.json"]
            while (notice := page.receive_json())["type"] != "catalog_changed":
                pass
            assert notice["words"] == "Catalog updated from the library: 1 connection changed"
        shared = ok(client.get("/shared-catalog", headers=AUTH))
        finance = next(c for c in shared["connections"] if c["connection"] == "Finance Captive")
        assert not finance["here"] and finance["tables_list"][0]["used_by"] == ["Cession statements"]
        assert shared["not_here"] == ["Finance Captive"]
        info = ok(client.get("/library", headers=AUTH))["catalog"]
        assert (info["connections"], info["tables"]) == (2, 3) and info["picked_up"]
        # Explorer search finds a teammate's table before anything is loaded.
        found = ok(client.get("/explorer/search?q=invoices", headers=AUTH))
        results = [r for g in found["groups"] for r in g["results"]]
        invoices = next(r for r in results if r.get("shared") and r["name"] == "Invoices")
        assert invoices["detail"].endswith("From the shared catalog: not connected here")
        assert not invoices["here"] and invoices["sql"] == "[Finance Captive].Invoices"
        browse = ok(client.get("/explorer/browse", headers=AUTH))
        shared_section = next(s for s in browse["sections"] if s["kind"] == "shared")
        assert [c["name"] for c in shared_section["items"][0]["children"]] == ["InvoiceId", "CedantId"]

        # The ERD's All tables draws a teammate's tables too; context.md names them.
        erd = ok(client.get("/relationships/erd?scope=all", headers=AUTH))
        assert "Invoices" in erd["tables"] and "InvoiceId" in erd["mermaid"]
        context = ok(client.get("/claude/context", headers=AGENT))["text"]
        assert "## Shared catalog" in context and "`Finance Captive` (not connected here" in context

        # A merge left its markers: said with the file's name, and never written over.
        bad = "<<<<<<< ours\n" + (folder / "warehouse.json").read_text() + "=======\n{}\n>>>>>>> theirs\n"
        (folder / "warehouse.json").write_text(bad, encoding="utf-8")
        problems = ok(client.post("/shared-catalog/refresh", headers=AUTH))["problems"]
        assert problems[0]["file"] == "catalog/warehouse.json" and "merge conflict" in problems[0]["error"]
        ok(client.post("/blades/Warehouse/refresh", json={}, headers=AUTH))
        assert (folder / "warehouse.json").read_text() == bad
        # The user finishes the merge: read again, and written by the next event.
        (folder / "warehouse.json").write_text(
            teammate({}).replace("Finance Captive", "Warehouse"), encoding="utf-8"
        )
        assert ok(client.post("/shared-catalog/refresh", headers=AUTH))["problems"] == []
        ok(client.post("/blades/Warehouse/refresh", json={}, headers=AUTH))
        assert "main.orders" in json.loads((folder / "warehouse.json").read_text())["tables"]


def test_used_by_follows_the_open_project(tmp_path: Path) -> None:
    db = tmp_path / "warehouse.sqlite"
    database(db)
    project = tmp_path / "work" / "Sales review"
    with make_client(tmp_path) as client:
        warehouse(client, db)
        ok(client.post("/blades/Warehouse/refresh", json={}, headers=AUTH))
        ok(client.post("/project/new", json={"path": str(project)}, headers=AUTH))
        (project / "look.py").write_text('import swissarmybench as sab\nsab.sql("SELECT * FROM customers")\n')
        push(client, "orders", pa.table({"id": [1, 2]}))
        ok(client.post("/project/save", json={}, headers=AUTH))
        tables = json.loads(catalog_file(tmp_path).read_text())["tables"]
        assert tables["main.orders"]["used_by"] == ["Sales review"]
        assert tables["main.customers"]["used_by"] == ["Sales review"]  # named in the project's code
        (project / "look.py").unlink()
        ok(client.post("/project/save", json={}, headers=AUTH))
        tables = json.loads(catalog_file(tmp_path).read_text())["tables"]
        assert tables["main.customers"]["used_by"] == []
        assert tables["main.orders"]["used_by"] == ["Sales review"]
