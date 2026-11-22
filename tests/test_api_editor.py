"""API.py in its editor (the owner approved the critic's proposal 8, 2026-11-21): its own problems as
squiggles (the APIs page's rules, a connection with no sandbox table, SQL the mock would refuse: never
run); sab_api's names and the sandbox's tables and columns in completion; Jedi reading sab_api as the app's
runtime. Made-up data."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from starlette.testclient import TestClient

from swissarmybench.domain import intellisense as rules
from swissarmybench.domain import local_api as api_rules
from tests.conftest import AUTH, make_client

API = """from sab_api import connection, endpoint, records


@endpoint("GET", "/orders/{region}")
def orders_in(region: str) -> list[dict]:
    db = connection("Sandbox")
    cur = db.cursor()
    cur.execute("SELECT order_id FROM orders WHERE region = ?", [region])
    return records(cur)


@endpoint("POST", "/orders/merge")
def merge_orders() -> dict:
    connection("Sandbox").execute(\"\"\"
        MERGE INTO orders USING orders AS o ON orders.order_id = o.order_id
        WHEN MATCHED THEN UPDATE SET region = o.region\"\"\")
    return {}


@endpoint("GET", "/stock")
def stock() -> list[dict]:
    return records(connection("Warehouse").cursor())


@endpoint("GET", "/orders/{region}")
def again(region: str) -> list[dict]:
    return []
"""


def test_the_editors_checks_are_the_api_pages_rules_and_the_mocks() -> None:
    mocks = {"Sandbox": ("duckdb", ["orders"])}
    found = api_rules.editor_problems(API, mocks)
    words = {p["line"]: p["message"] for p in found}
    lines = API.splitlines()
    assert any(w.startswith("The sandbox's mock cannot run MERGE") for w in words.values())
    stock = next(i + 1 for i, line in enumerate(lines) if 'connection("Warehouse")' in line)
    assert "no table read from Warehouse yet" in words[stock]
    assert any("/orders/{region}" in w for w in words.values())  # two endpoints on one path (the page's rule)
    assert not any("order_id FROM orders" in lines[line - 1] for line in words)  # its ? comes at run time
    assert api_rules.is_api_file("/p/shop/API.py") and api_rules.is_api_file("C:\\shop\\API.py")
    assert not api_rules.is_api_file("/p/api.py")
    # SQL made at run time (an f-string, as the wizard's Reconcile writes its query around a constant) is not
    # read as SQL here: it was marked "could not read this DuckDB SQL" on the wizard's own code (2026-11-22).
    made = (
        'from sab_api import connection, endpoint, records\n\nCOMPARED = "SELECT order_id FROM orders"\n\n\n'
        '@endpoint("GET", "/compared")\ndef compared() -> list[dict]:\n'
        '    return records(connection("Sandbox").query(f"WITH c AS ({COMPARED}) SELECT * FROM c"))\n'
    )
    assert api_rules.editor_problems(made, mocks) == []


def test_sql_strings_and_sab_api_complete_and_jedi_reads_sab_api() -> None:
    text = 'cur.execute("SELECT re FROM orders")'
    q = rules.quoted_context(text, text.index("re ") + 2)
    assert q is not None and q.kind == "sandbox_column" and q.tables == ("orders",) and q.typed == "re"
    many = 'cur.execute("""\n  SELECT o.region\n  FROM ord'
    q2 = rules.quoted_context(many, len(many))
    assert q2 is not None and (q2.kind, q2.typed) == ("sandbox_table", "ord")
    assert rules.quoted_context('x = cur.execute("SELECT 1")\ny', 30) is None
    assert [i["label"] for i in rules.sab_api_names()] == ["endpoint", "connection", "records", "ApiError"]
    jedi = rules.sab_api_for_jedi("from sab_api import endpoint\nx = 1\nfrom sab_api import ", 2)
    assert jedi.split("\n") == [
        "from swissarmybench.server.api_runtime import endpoint",
        "x = 1",
        "from sab_api import ",
    ]


@pytest.fixture
def shop(tmp_path: Path) -> Iterator[tuple[TestClient, Path]]:
    with make_client(tmp_path) as client:
        folder = tmp_path / "shop"
        assert client.post("/project/new", json={"path": str(folder)}, headers=AUTH).status_code == 200
        csv = tmp_path / "orders.csv"
        csv.write_text("order_id,region,amount\n1,West,10.5\n2,East,7\n", encoding="utf-8")
        assert (
            client.post("/sandbox/tables", json={"from": "file", "path": str(csv)}, headers=AUTH).status_code
            == 200
        )
        (folder / "API.py").write_text(API, encoding="utf-8")
        yield client, folder


def _labels(answer: dict[str, Any]) -> list[str]:
    return [str(i["label"]) for i in answer["items"]]


def test_api_py_in_the_editor_squiggles_and_completes(shop: tuple[TestClient, Path]) -> None:
    client, folder = shop
    path = str(folder / "API.py")
    lint = client.post("/workbench/intel/lint", json={"text": API, "path": path}, headers=AUTH).json()
    ours = [p for p in lint["problems"] if p["source"] == "API.py"]
    assert {p["code"] for p in ours} == {"API"} and len(ours) >= 3, ours
    assert any("Warehouse" in p["message"] for p in ours) and any("MERGE" in p["message"] for p in ours)
    # Another script with the same text: no API.py rules on it.
    other = client.post(
        "/workbench/intel/lint", json={"text": API, "path": str(folder / "etl.py")}, headers=AUTH
    ).json()
    assert not [p for p in other["problems"] if p["source"] == "API.py"]
    sql = 'cur.execute("SELECT re FROM orders")'
    columns = client.post(
        "/workbench/intel/complete",
        json={"text": sql, "offset": sql.index("re ") + 2, "path": path},
        headers=AUTH,
    ).json()
    assert _labels(columns) == ["region"]
    imported = "from sab_api import endpoint, re"
    names = client.post(
        "/workbench/intel/complete",
        json={"text": imported, "offset": len(imported), "path": path},
        headers=AUTH,
    ).json()
    assert _labels(names) == ["records"]
    hover_text = "from sab_api import connection\n\nconnection"
    hover = client.post(
        "/workbench/intel/hover",
        json={"text": hover_text, "offset": len(hover_text) - 3, "path": path},
        headers=AUTH,
    ).json()
    assert "connection's calls" in str(hover.get("hover")), hover
