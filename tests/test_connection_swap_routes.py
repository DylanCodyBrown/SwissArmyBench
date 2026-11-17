"""A table's connection swapped on the running server (services/connection_swap.py), the owner's case
(2026-11-16): two connections, EDP (an ODBC one made by mistake) and Trino, stood in for by two SQLite
files with the same tables in another schema and case. A table with steps moves with its steps; a query
is reviewed, then run; a deleted connection's tables move at once; the code that named EDP points at
Trino only where ticked; the undo; the agent's commands. Made-up data only."""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from starlette.testclient import TestClient

from tests.conftest import AGENT, AUTH, make_client
from tests.fake_keyring import memory_keyring

STEPS = [
    {"kind": "filter", "params": {"column": "region", "op": "ne", "value": "East"}},
    {"kind": "sort", "params": {"keys": [["units", "desc"]]}},
]
ROWS = [(1, "North", 3), (2, "East", 9), (3, "South", 5), (4, "North", 7)]


@pytest.fixture(autouse=True)
def vault() -> Iterator[None]:
    with memory_keyring():
        yield


def ok(response: Any) -> Any:
    assert response.status_code == 200, response.text
    return response.json()


def connections(tmp_path: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    """EDP: ORDERS in SQLite's main schema, upper case. Trino: orders (and a second table) in a schema
    called sales, lower case, one row more."""
    edp_file, trino_file, sales_file = (
        tmp_path / "edp.sqlite",
        tmp_path / "trino.sqlite",
        tmp_path / "sales.sqlite",
    )
    with sqlite3.connect(edp_file) as made_up:
        made_up.execute("CREATE TABLE ORDERS (order_id INTEGER, region TEXT, units INTEGER)")
        made_up.executemany("INSERT INTO ORDERS VALUES (?, ?, ?)", ROWS)
    with sqlite3.connect(trino_file) as made_up:
        made_up.execute("CREATE TABLE placeholder (x INTEGER)")
    with sqlite3.connect(sales_file) as made_up:
        made_up.execute("CREATE TABLE orders (order_id INTEGER, region TEXT, units INTEGER)")
        made_up.executemany("INSERT INTO orders VALUES (?, ?, ?)", [*ROWS, (5, "West", 2)])
        made_up.execute("CREATE TABLE items (item_id INTEGER, name TEXT)")
    edp = {
        "name": "EDP",
        "kind": "sql",
        "template": "sqlite",
        "dialect": "sqlite",
        "code": (
            "import sqlite3\nfrom pathlib import Path\n\n"
            f'path = Path(r"{edp_file}")\n'
            'conn = sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True)\n'
        ),
    }
    catalog = (
        "SELECT 'sales' AS table_schema, m.name AS table_name, m.type AS table_type, p.name AS column_name, "
        "p.type AS data_type, 'YES' AS is_nullable, p.cid + 1 AS ordinal_position "
        "FROM sales.sqlite_master AS m JOIN pragma_table_info(m.name, 'sales') AS p "
        "WHERE m.type = 'table' ORDER BY m.name, p.cid"
    )
    trino = {
        "name": "Trino",
        "kind": "sql",
        "template": "sqlite",
        "dialect": "sqlite",
        "code": (
            "import sqlite3\nfrom pathlib import Path\n\n"
            f'path = Path(r"{trino_file}")\n'
            f'sales = Path(r"{sales_file}").resolve().as_uri() + "?mode=ro"\n'
            'conn = sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True)\n'
            'conn.execute("ATTACH DATABASE ? AS sales", (sales,))\n'
        ),
        "catalog": {"language": "sql", "command": catalog},
    }
    return edp, trino


def ids(client: TestClient, grid: str) -> list[Any]:
    return [r[0] for r in ok(client.get(f"/grids/{grid}/rows", headers=AUTH))["rows"]]


def test_a_table_moves_to_the_other_connection_with_its_steps_and_back(tmp_path: Path) -> None:
    with make_client(tmp_path) as client:
        edp, trino = connections(tmp_path)
        ok(client.post("/connections", json=edp, headers=AUTH))
        ok(client.post("/connections", json=trino, headers=AUTH))
        opened = ok(
            client.post("/connections/EDP/open", json={"schema": "main", "table": "ORDERS"}, headers=AUTH)
        )
        grid, name = opened["grid"], opened["dataset"]
        ok(client.post(f"/grids/{grid}/steps", json={"steps": STEPS}, headers=AUTH))
        assert ids(client, grid) == [4, 3, 1]

        state = ok(client.get(f"/tables/{name}/connection", headers=AUTH))
        assert state["connection"] == "EDP" and state["exists"] is True and state["how"] == "table"
        assert state["place"]["table"] == "ORDERS" and state["others"] == ["Trino"] and state["undo"] is False

        swapped = ok(client.post(f"/tables/{name}/connection", json={"to": "Trino"}, headers=AUTH))["swapped"]
        assert swapped["place"] == {"database": "", "schema": "sales", "table": "orders"}
        assert swapped["grids"] == [grid] and swapped["steps_problems"] == []
        # The same tab, the same steps, Trino's rows: one more, in the West, not East so it stays.
        assert ok(client.get(f"/grids/{grid}", headers=AUTH))["steps"][0]["kind"] == "filter"
        assert ids(client, grid) == [4, 3, 1, 5]
        state = ok(client.get(f"/tables/{name}/connection", headers=AUTH))
        assert state["connection"] == "Trino" and state["undo"] is True and state["undo_connection"] == "EDP"
        # Its Workbench cell reads it from Trino now.
        cells = ok(client.get("/workbench/tables", headers=AUTH))
        assert "Trino" in json.dumps(cells) and "'EDP'" not in json.dumps(cells)

        undone = ok(client.post(f"/tables/{name}/connection/undo", headers=AUTH))
        assert undone == {"undone": name, "connection": "EDP"}
        assert ids(client, grid) == [4, 3, 1]
        assert ok(client.get(f"/tables/{name}/connection", headers=AUTH))["connection"] == "EDP"
        assert client.post(f"/tables/{name}/connection/undo", headers=AUTH).status_code == 404


def test_a_table_not_found_by_name_asks_to_pick_or_runs_a_reviewed_query(tmp_path: Path) -> None:
    with make_client(tmp_path) as client:
        edp, trino = connections(tmp_path)
        with sqlite3.connect(tmp_path / "edp.sqlite") as made_up:
            made_up.execute("CREATE TABLE sales_items (item_id INTEGER, name TEXT)")
            made_up.execute("INSERT INTO sales_items VALUES (1, 'Pear')")
        ok(client.post("/connections", json=edp, headers=AUTH))
        ok(client.post("/connections", json=trino, headers=AUTH))
        opened = ok(
            client.post(
                "/connections/EDP/open", json={"schema": "main", "table": "sales_items"}, headers=AUTH
            )
        )
        name = opened["dataset"]
        pick = ok(client.post(f"/tables/{name}/connection", json={"to": "Trino"}, headers=AUTH))["pick"]
        assert pick["candidates"] == [] and pick["to"] == "Trino"
        assert any(s["schema"] == "sales" for s in pick["schemas"]) and "sales_items" in pick["sql"]
        # Picked from the catalog tree.
        place = {"database": "", "schema": "sales", "table": "items"}
        ok(client.post(f"/tables/{name}/connection", json={"to": "Trino", "place": place}, headers=AUTH))
        # Or a query, looked over in the SQL window: only a read runs.
        sql = "SELECT item_id, upper(name) AS name FROM sales.items"
        refused = client.post(
            f"/tables/{name}/connection", json={"to": "Trino", "sql": "DELETE FROM sales.items"}, headers=AUTH
        )
        assert refused.status_code == 400
        swapped = ok(
            client.post(f"/tables/{name}/connection", json={"to": "Trino", "sql": sql}, headers=AUTH)
        )
        assert swapped["swapped"]["how"] == "query"
        state = ok(client.get(f"/tables/{name}/connection", headers=AUTH))
        assert state["how"] == "query" and state["sql"] == sql and state["connection"] == "Trino"
        # A query table asks for review when it moves again.
        review = ok(client.post(f"/tables/{name}/connection", json={"to": "EDP"}, headers=AUTH))["review"]
        assert review == {"table": name, "to": "EDP", "from": "Trino", "sql": sql}


def test_a_deleted_connections_tables_all_move_and_a_project_reopens_them_from_trino(tmp_path: Path) -> None:
    target = tmp_path / "work"
    with make_client(tmp_path) as client:
        edp, trino = connections(tmp_path)
        ok(client.post("/connections", json=edp, headers=AUTH))
        ok(client.post("/connections", json=trino, headers=AUTH))
        ok(client.post("/project/new", json={"path": str(target)}, headers=AUTH))  # the library's connections
        grid = ok(
            client.post("/connections/EDP/open", json={"schema": "main", "table": "ORDERS"}, headers=AUTH)
        )["grid"]
        ok(client.post(f"/grids/{grid}/steps", json={"steps": STEPS}, headers=AUTH))
        # EDP is deleted from the library; saved, closed and opened again, ORDERS waits for it.
        ok(client.delete("/blades/EDP", headers=AUTH))
        ok(client.post("/project/save", json={}, headers=AUTH))
        ok(client.post("/project/close", json={"discard": True}, headers=AUTH))
        opened = ok(client.post("/project/open", json={"path": str(target)}, headers=AUTH))
        problems = ok(client.get("/project", headers=AUTH))["project"]["problems"]
        assert [(p["table"], p["state"]) for p in problems] == [("ORDERS", "no_connection")], opened
        state = ok(client.get("/tables/ORDERS/connection", headers=AUTH))
        assert state["exists"] is False and state["open"] is False and state["others"] == ["Trino"]

        moved = ok(client.post("/connections/EDP/move", json={"to": "Trino"}, headers=AUTH))
        assert [m["table"] for m in moved["moved"]] == ["ORDERS"] and not moved["failed"]
        now = ok(client.get("/project", headers=AUTH))["project"]
        assert now["problems"] == []
        grid = ok(client.get("/grids", headers=AUTH))["grids"][0]["grid"]
        assert ids(client, grid) == [4, 3, 1, 5]  # its steps, Trino's rows
        ok(client.post("/project/save", json={}, headers=AUTH))
        manifest = json.loads((target / ".sab" / "project.json").read_text(encoding="utf-8"))
        source = manifest["tables"][0]["source"]
        assert source["connection"] == "Trino" and source["schema"] == "sales" and source["table"] == "orders"


def test_queries_of_a_deleted_connection_review_or_run_as_they_are(tmp_path: Path) -> None:
    with make_client(tmp_path) as client:
        edp, trino = connections(tmp_path)
        ok(client.post("/connections", json=edp, headers=AUTH))
        ok(client.post("/connections", json=trino, headers=AUTH))
        opened = ok(
            client.post("/connections/EDP/open", json={"schema": "main", "table": "ORDERS"}, headers=AUTH)
        )
        # A query table on EDP (made by a swap onto EDP from itself, as the SQL window does).
        sql = "SELECT * FROM sales.orders WHERE units > 2"
        name = opened["dataset"]
        ok(client.post(f"/tables/{name}/connection", json={"to": "Trino", "sql": sql}, headers=AUTH))
        ok(client.delete("/blades/EDP", headers=AUTH))
        ok(client.post("/connections", json=edp | {"name": "Archive"}, headers=AUTH))
        moved = ok(client.post("/connections/Trino/move", json={"to": "Archive"}, headers=AUTH))
        assert moved["review"] == [{"table": name, "to": "Archive", "from": "Trino", "sql": sql}]
        failed = ok(
            client.post("/connections/Trino/move", json={"to": "Archive", "run_as_is": True}, headers=AUTH)
        )
        # Archive has no sales schema: the query fails there in the source's own words; nothing is lost.
        assert failed["failed"] and failed["failed"][0]["table"] == name
        assert ok(client.get(f"/tables/{name}/connection", headers=AUTH))["connection"] == "Trino"


def test_the_code_follows_only_where_ticked(tmp_path: Path) -> None:
    with make_client(tmp_path) as client:
        edp, trino = connections(tmp_path)
        ok(client.post("/connections", json=edp, headers=AUTH))
        ok(client.post("/connections", json=trino, headers=AUTH))
        book = tmp_path / "orders.ipynb"
        cells = [
            {"kind": "sql", "source": "SELECT * FROM ORDERS", "connection": "EDP"},
            {"kind": "code", "source": "note = 'EDP is gone'\nprint('EDP')"},
            {"kind": "code", "source": "import swissarmybench as sab\ntotals = sab.sql('EDP', 'SELECT 1')"},
            {"kind": "sql", "source": "SELECT 2", "connection": "EDP"},
        ]
        ok(client.post("/workbench/save", json={"path": str(book), "cells": cells}, headers=AUTH))
        client.post("/workbench/open", json={"path": str(book)}, headers=AUTH)
        ok(client.delete("/blades/EDP", headers=AUTH))
        listed = ok(client.get("/connections/EDP/references", headers=AUTH))["references"]
        numbers = sorted(r["cell"] for r in listed if r["pickable"])
        assert numbers == [1, 3, 4]
        picks = [{"document": str(book), "cell": 1}, {"document": str(book), "cell": 3}]
        done = ok(client.post("/connections/EDP/repoint", json={"to": "Trino", "picks": picks}, headers=AUTH))
        assert done["cells"] == 2 and done["changed"][0]["cells"] == [1, 3]
        saved = json.loads(book.read_text(encoding="utf-8"))["cells"]
        texts = ["".join(c["source"]) for c in saved]
        assert texts[0].startswith("%%sql Trino\n")
        assert texts[1] == "note = 'EDP is gone'\nprint('EDP')"
        assert "sab.sql('Trino', 'SELECT 1')" in texts[2]
        assert texts[3].startswith("%%sql EDP\n")
        left = ok(client.get("/connections/EDP/references", headers=AUTH))["references"]
        assert [r["cell"] for r in left if r["pickable"]] == [4]
        assert (
            client.post("/connections/EDP/repoint", json={"to": "Nowhere"}, headers=AUTH).status_code == 404
        )


def test_the_agent_swaps_moves_and_points_the_code_too(tmp_path: Path) -> None:
    with make_client(tmp_path) as client:
        edp, trino = connections(tmp_path)
        ok(client.post("/connections", json=edp, headers=AUTH))
        ok(client.post("/connections", json=trino, headers=AUTH))
        opened = ok(
            client.post("/connections/EDP/open", json={"schema": "main", "table": "ORDERS"}, headers=AGENT)
        )
        name = opened["dataset"]
        assert ok(client.post(f"/tables/{name}/connection", json={"to": "Trino"}, headers=AGENT))["swapped"]
        ok(client.post(f"/tables/{name}/connection/undo", headers=AGENT))
        moved = ok(client.post("/connections/EDP/move", json={"to": "Trino"}, headers=AGENT))
        assert [m["table"] for m in moved["moved"]] == [name]
        assert "references" in ok(client.get("/connections/EDP/references", headers=AGENT))
        rewrite = {"kind": "line", "text": "%%sql EDP", "from": "EDP", "to": "Trino"}
        assert ok(client.post("/connections/rewrite", json=rewrite, headers=AGENT))["text"] == "%%sql Trino"
