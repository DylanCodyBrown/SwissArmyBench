"""The change log through the app (services/changes.py; Plans/changes.plan.md): a table's steps and columns, a
table's data arriving again with other columns, a connection's settings, a variable by name, a notebook's
cells; each one event the Session page shows too; .sab/changes.jsonl written as it happens with a project
open; the agent's changes tool. Never a value. Made-up data only."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pyarrow as pa
from starlette.testclient import TestClient

from tests.conftest import AGENT, AUTH, grid_id, push
from tests.test_connection_tables import sqlite_connection


def ok(response: Any) -> Any:
    assert response.status_code == 200, response.text
    return response.json()


def last(client: TestClient, obj: str) -> Any:
    return ok(client.get("/changes", params={"action": "last", "object": obj}, headers=AGENT))["change"]


def test_a_tables_steps_and_columns_and_its_data_again(client: TestClient, tmp_path: Path) -> None:
    project = tmp_path / "shop"
    ok(client.post("/project/new", json={"path": str(project)}, headers=AUTH))
    orders = pa.table({"id": [1, 2, 3], "region": ["North", "South", "North"], "amount": [9.5, 3.0, 7.25]})
    grid = grid_id(push(client, "orders", orders))
    step = {"kind": "filter", "params": {"column": "region", "op": "=", "value": "North"}}
    ok(client.post(f"/grids/{grid}/steps", json={"steps": [step]}, headers=AGENT))
    change = last(client, "table:orders")
    assert change["who"] == "agent" and change["diff"]["steps"]["added"] == ["1 filter"]
    assert "North" not in json.dumps(change)  # a step's value is fingerprinted, never kept
    # The same table arrives again with a column more: its structure changed.
    wider = orders.append_column("segment", pa.array(["Gold", "Silver", "Gold"]))
    push(client, "orders", wider)
    again = last(client, "orders")
    assert again["diff"]["columns"]["added"] == ["segment"] and "Gold" not in json.dumps(again)
    history = ok(client.get("/changes", params={"action": "history", "object": "orders"}, headers=AGENT))
    assert len(history["changes"]) >= 3  # opened, its step, its new column
    lines = (project / ".sab" / "changes.jsonl").read_text(encoding="utf-8").splitlines()
    assert len(lines) == len(history["changes"]) and all(json.loads(line)["at"] for line in lines)
    # The Session page reads the same events: Changes shows only the entries that changed something.
    session = ok(client.get("/session-log", params={"who": "agent", "changes": "1"}, headers=AUTH))
    assert session["entries"] and all(e.get("change") for e in session["entries"])


def test_a_connection_a_variable_and_a_notebook(client: TestClient, tmp_path: Path) -> None:
    sqlite_connection(client, tmp_path, "Shop", {"orders": ("id INTEGER", [(1,), (2,)])})
    made = last(client, "connection:Shop")
    assert made is not None and made["object"] == {"kind": "connection", "name": "Shop"}
    ok(client.put("/variables", json={"name": "SALES_REGION", "value": "North"}, headers=AUTH))
    variable = last(client, "variable:SALES_REGION")
    assert variable["words"] == "Added the variable SALES_REGION (value)"
    assert "North" not in json.dumps(variable)  # its value never comes along
    notebook = tmp_path / "sales.ipynb"
    cells = [{"kind": "code", "source": "x = 1", "number": 1}]
    ok(client.post("/workbench/save", json={"path": str(notebook), "cells": cells}, headers=AUTH))
    cells.append({"kind": "code", "source": "y = 2", "number": 2})
    ok(client.post("/workbench/save", json={"path": str(notebook), "cells": cells}, headers=AUTH))
    saved = last(client, "notebook:sales.ipynb")
    assert saved["diff"]["cells"]["added"] == ["cell 2"] and "y = 2" not in json.dumps(saved)
    found = ok(client.get("/changes", params={"action": "search", "kind": "variable"}, headers=AGENT))
    assert [c["object"]["name"] for c in found["changes"]] == ["SALES_REGION"]
    assert client.get("/changes", params={"action": "nonsense"}, headers=AGENT).status_code == 400
