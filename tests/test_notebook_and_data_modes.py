# ruff: noqa: F811
"""Notebook mode and Data mode (the Workbench's modes, 2026-11-15): a notebook's run order and its stale
cells (edited, out of date because a name it reads was made again), its Outline; data.ipynb's data
dictionary (plain-word types, descriptions kept in data.ipynb and written into data.py, where each column
comes from). Made-up data only."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pyarrow as pa
import pytest
from starlette.testclient import TestClient

from swissarmybench.domain import dictionary, notebook_flow, notebooks, projects
from tests.conftest import AUTH, push
from tests.test_cli import Live, live  # noqa: F401 (the running server)
from tests.test_cli import run as command

SHIPPED = 'shipped = orders[orders["status"] == "shipped"]'
MONTHLY = 'monthly = shipped.groupby("month").sum()'
BY_REGION = 'by_region = shipped.groupby("region").sum()'


def _cells(*rows: tuple[int, str, str, str | None, int | None]) -> list[dict[str, Any]]:
    return [{"number": n, "kind": k, "source": s, "ran": r, "order": o} for n, k, s, r, o in rows]


def test_edited_and_out_of_date_cells() -> None:
    sent = _cells(
        (1, "markdown", "# Monthly sales", None, None),
        (2, "code", SHIPPED + "  # edited", SHIPPED, 1),
        (3, "code", MONTHLY, MONTHLY, 2),
        (5, "code", BY_REGION, BY_REGION, 3),
        (6, "code", "total = 1", None, None),
    )
    cells = {c.number: c for c in notebook_flow.flow(notebook_flow.read_cells(sent))}
    assert cells[2].state == "edited"
    assert (cells[3].state, cells[3].because) == ("outOfDate", ["shipped"])
    assert cells[5].state == "outOfDate" and cells[6].state == "notRun"
    assert cells[3].reads == ["shipped"] and cells[3].makes == ["monthly"]


def test_a_maker_that_ran_later_makes_its_readers_out_of_date() -> None:
    sent = _cells(
        (2, "code", SHIPPED, SHIPPED, 5),
        (3, "code", MONTHLY, MONTHLY, 2),
        (4, "code", "x = monthly", "x = monthly", 3),
    )
    cells = {c.number: c for c in notebook_flow.flow(notebook_flow.read_cells(sent))}
    assert cells[2].state == "current"
    assert cells[3].state == "outOfDate" and cells[4].state == "outOfDate" and cells[4].because == ["monthly"]
    fresh = _cells((2, "code", SHIPPED, SHIPPED, 1), (3, "code", MONTHLY, MONTHLY, 2))
    assert [c.state for c in notebook_flow.flow(notebook_flow.read_cells(fresh))] == ["current", "current"]
    with pytest.raises(notebook_flow.FlowError):
        notebook_flow.read_cells([{"kind": "code"}])


def test_the_outline_is_the_headings_and_the_named_cells() -> None:
    cells = [
        {"number": 1, "kind": "markdown", "source": "# Monthly sales\nShipped orders only."},
        {"number": 2, "kind": "code", "source": SHIPPED, "name": "shipped"},
        {"number": 4, "kind": "markdown", "source": "## By region"},
        {"number": 5, "kind": "code", "source": BY_REGION},
    ]
    assert notebook_flow.outline(cells) == [
        {"kind": "heading", "level": 1, "text": "Monthly sales", "number": 1},
        {"kind": "cell", "number": 2, "text": "shipped"},
        {"kind": "heading", "level": 2, "text": "By region", "number": 4},
    ]


def test_the_flow_route(client: TestClient) -> None:
    sent = _cells((2, "code", SHIPPED, SHIPPED, 2), (3, "code", MONTHLY, MONTHLY, 1))
    done = client.post("/workbench/notebook/flow", headers=AUTH, json={"cells": sent})
    assert done.status_code == 200, done.text
    assert [c["state"] for c in done.json()["cells"]] == ["current", "outOfDate"]
    assert client.post("/workbench/notebook/flow", headers=AUTH, json={"cells": 3}).status_code == 400


def test_plain_types_and_descriptions() -> None:
    assert [
        dictionary.plain_type(t)
        for t in (
            "BIGINT",
            "DECIMAL(18,2)",
            "VARCHAR",
            "DATE",
            "TIMESTAMP WITH TIME ZONE",
            "BOOLEAN",
            "INTEGER[]",
        )
    ] == [
        "Whole number",
        "Decimal",
        "Text",
        "Date",
        "Date and time",
        "True or false",
        "List",
    ]
    said = dictionary.check(
        {
            "orders": {
                "description": " One row per\norder line. ",
                "columns": {"status": "Shipped or returned", "x": ""},
            }
        }
    )
    assert said == {
        "orders": {"description": "One row per order line.", "columns": {"status": "Shipped or returned"}}
    }
    with pytest.raises(dictionary.DictionaryError, match="at most"):
        dictionary.check({"orders": {"description": "x" * 501}})
    page = dictionary.entry(
        "orders",
        [("order_id", "BIGINT"), ("amount_home", "DOUBLE")],
        [["order_id", "amount"], ["order_id", "amount"], ["order_id", "amount", "amount_home"]],
        "orders.csv",
        12,
        2,
        {"orders": {"description": "One row per order line.", "columns": {"order_id": "One per order."}}},
    )
    assert page["columns"] == [
        {
            "name": "order_id",
            "type": "Whole number",
            "description": "One per order.",
            "comes_from": "orders.csv",
        },
        {"name": "amount_home", "type": "Decimal", "description": "", "comes_from": "Step 2"},
    ]


def test_descriptions_live_in_data_ipynb_and_go_into_data_py() -> None:
    cells = [notebooks.Cell("code", "orders = 1")]
    said = {
        "orders": {"description": "One row per order line.", "columns": {"status": "Shipped or returned"}}
    }
    text = notebooks.write_notebook(cells, dictionary=said)
    assert dictionary.of_notebook(text) == said
    assert json.loads(text)["metadata"]["swissarmybench"]["dictionary"] == said
    made = projects.data_module("sales", [projects.DataCell("code", "orders = 1", "", "orders", 1)], said)
    assert "# Data dictionary (written in data.ipynb's Dictionary):" in made.text
    assert (
        "#   orders: One row per order line." in made.text
        and "#     status: Shipped or returned" in made.text
    )
    compile(made.text, "data.py", "exec")


def test_the_dictionary_route_and_the_workbench_keeps_descriptions(
    client: TestClient, tmp_path: Path
) -> None:
    assert (
        push(client, "orders", pa.table({"order_id": [1, 2], "status": ["shipped", "returned"]})).status_code
        == 200
    )
    grid = client.get("/grids", headers=AUTH).json()["grids"][0]["grid"]
    step = {"kind": "transform", "params": {"column": "status", "op": "upper"}}
    client.post(f"/grids/{grid}/steps", headers=AUTH, json={"steps": [step]})
    said = {
        "orders": {"description": "One row per order line.", "columns": {"status": "Shipped or returned"}}
    }
    done = client.post(
        "/projects/dictionary",
        headers=AUTH,
        json={"tables": [{"name": "orders", "source": "orders.csv"}], "descriptions": said},
    )
    assert done.status_code == 200, done.text
    table = done.json()["tables"][0]
    assert (table["table"], table["rows"], table["source"], table["description"]) == (
        "orders",
        2,
        "orders.csv",
        "One row per order line.",
    )
    assert [(c["name"], c["type"], c["description"]) for c in table["columns"]] == [
        ("order_id", "Whole number", ""),
        ("status", "Text", "Shipped or returned"),
    ]
    path = str(tmp_path / "sales" / "data.ipynb")
    (tmp_path / "sales").mkdir()
    saved = client.post("/workbench/save", headers=AUTH, json={"path": path, "cells": [], "dictionary": said})
    assert saved.status_code == 200, saved.text
    assert client.post("/workbench/open", headers=AUTH, json={"path": path}).json()["dictionary"] == said
    by_folder = client.post("/projects/dictionary", headers=AUTH, json={"folder": str(tmp_path / "sales")})
    assert by_folder.status_code == 200 and by_folder.json()["tables"] == []


def test_the_agent_reads_a_projects_dictionary(live: Live, tmp_path: Path) -> None:
    folder = tmp_path / "shop"
    folder.mkdir()
    said = {"orders": {"description": "Made-up orders.", "columns": {}}}
    (folder / "data.ipynb").write_text(notebooks.write_notebook([], dictionary=said), encoding="utf-8")
    assert command("project_dictionary", folder=str(folder)) == {"tables": []}
