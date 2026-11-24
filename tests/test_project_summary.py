"""Home's summary of the open project (the owner, 2026-11-24: "The project home page should become a
summary of the current open project"; domain/project_summary.py, services/project_summary.py,
GET /project/summary).

The rules on canned answers, then a made-up project (a table from a CSV file, a notebook, a script, a made-up
SQLite connection its notebook names) summarised through the route, and none open. Made-up data only."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

from swissarmybench.domain import notebooks
from swissarmybench.domain import project_summary as rules
from tests.conftest import AUTH, make_client
from tests.fake_keyring import memory_keyring


@pytest.fixture(autouse=True)
def vault() -> Iterator[None]:
    with memory_keyring():
        yield


def ok(response: Any) -> Any:
    assert response.status_code == 200, response.text
    return response.json()


def test_the_tables_take_their_rows_from_the_store_and_keep_the_projects_order() -> None:
    kept = [{"name": "orders", "from": "orders.csv", "kind": "file"}, {"name": "regions", "kind": "paste"}]
    shown = rules.tables(kept, [{"name": "orders", "rows": 12, "columns": 3}])
    assert shown == [
        {"name": "orders", "from": "orders.csv", "kind": "file", "rows": 12, "columns": 3},
        {"name": "regions", "from": "", "kind": "paste", "rows": None, "columns": None},
    ]


def test_documents_put_data_ipynb_and_api_py_first_and_leave_the_made_files_out() -> None:
    listed: list[dict[str, Any]] = [
        {"path": "analysis.ipynb", "name": "analysis.ipynb", "kind": "notebook"},
        {"path": "data.ipynb", "name": "data.ipynb", "kind": "notebook"},
        {"path": "load.py", "name": "load.py", "kind": "script"},
        {"path": "API.py", "name": "API.py", "kind": "script"},
        {"path": "data.py", "name": "data.py", "kind": "script", "made": True},
        {"path": "sales.canvas.json", "name": "sales.canvas.json", "kind": "app"},
    ]
    shown = rules.documents(listed)
    assert [d["path"] for d in shown] == [
        "data.ipynb",
        "analysis.ipynb",
        "API.py",
        "load.py",
        "sales.canvas.json",
    ]
    assert [d["page"] for d in shown] == ["notebooks", "notebooks", "scripts", "scripts", "canvas"]
    assert [d["api"] for d in shown] == [False, False, True, False, False]


def test_connections_take_their_status_and_colour_and_counts_each_section() -> None:
    cards = [{"name": "Warehouse", "type": "SQLite", "status": "Ready"}]
    colours = [{"name": "warehouse", "colour": "#2f6fd6"}]
    used = rules.connections(["Warehouse", "Lake", "Warehouse"], cards, colours)
    assert used == [
        {"name": "Warehouse", "type": "SQLite", "status": "Ready", "colour": "#2f6fd6"},
        {"name": "Lake", "type": "", "status": "", "colour": ""},
    ]
    counts = rules.counts({"tables": [{}], "documents": rules.documents([]), "connections": used})
    assert counts == {"tables": 1, "notebooks": 0, "scripts": 0, "apps": 0, "structures": 0, "connections": 2}


def test_the_summary_of_a_made_up_project_and_of_none(tmp_path: Path) -> None:
    with make_client(tmp_path) as client:
        assert ok(client.get("/project/summary", headers=AUTH)) == {"project": None}
        folder = tmp_path / "Captive"
        made = ok(client.post("/project/new", json={"path": str(folder)}, headers=AUTH))["project"]
        csv = tmp_path / "orders.csv"
        csv.write_text("order_id,region,units\n1,North,3\n2,East,9\n", encoding="utf-8")
        ok(client.post("/datasets/orders/load", json={"path": str(csv)}, headers=AUTH))
        code = 'import sqlite3\nconn = sqlite3.connect(":memory:")\n'
        warehouse = {
            "name": "Warehouse",
            "kind": "sql",
            "template": "sqlite",
            "dialect": "sqlite",
            "code": code,
        }
        ok(client.post("/connections", json=warehouse, headers=AUTH))
        cells = [notebooks.Cell("code", "%%sql Warehouse\nSELECT 1")]
        Path(made["folder"], "analysis.ipynb").write_text(notebooks.write_notebook(cells), encoding="utf-8")
        Path(made["folder"], "load.py").write_text("print('made-up')\n", encoding="utf-8")

        summary = ok(client.get("/project/summary", headers=AUTH))
        project = summary["project"]
        assert project["name"] == "Captive" and project["path"] == made["folder"]
        assert project["where"] == "local" and project["type_name"]
        assert [t["name"] for t in summary["tables"]] == ["orders"]
        assert summary["tables"][0]["rows"] == 2
        assert [d["path"] for d in summary["documents"]][:2] == ["data.ipynb", "analysis.ipynb"]
        assert "load.py" in {d["path"] for d in summary["documents"]}
        assert [c["name"] for c in summary["connections"]] == ["Warehouse"]
        assert summary["connections"][0]["status"]
        assert summary["counts"]["tables"] == 1 and summary["counts"]["connections"] == 1
        assert summary["python"]["status"]
        assert isinstance(summary["recent"], list)  # the Session page's last entries, as it words them

        ok(client.post("/project/close", json={"discard": True}, headers=AUTH))
        assert ok(client.get("/project/summary", headers=AUTH)) == {"project": None}
