"""What a connection is (the owner, 2026-11-17: "any connection ... exposes tables that we can write duckdb
against" / "that is the definition of a connection here"): every kind lists its tables and reads one
through the one contract (domain/connection_tables.py, services/connection_tables.py).

Every starter (server/blade_templates.py and the built-in starters/) either has a tables kind, and that
kind lists and reads a table here on a made-up stand-in (a SQLite file, the Power BI stand-in, Dataverse's
SQL endpoint at its cursor seam, its Web API stand-in, a Python connection, an API connection, a CSV file,
a workbook, a folder), or is on the no-tables list with the reason. A new kind cannot be added without its
tables. Made-up data only."""

from __future__ import annotations

import sqlite3
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any

import pandas as pd
import pytest
from starlette.testclient import TestClient

from swissarmybench.domain import connection_tables as ct
from swissarmybench.domain import dataverse
from swissarmybench.domain.blades import read_blade
from swissarmybench.domain.connections import connection_kind
from swissarmybench.server.blade_templates import BY_ID, TEMPLATES
from tests import dataverse_standin, dataverse_tds_standin
from tests import powerbi_standin as made_up
from tests.conftest import AGENT, AUTH
from tests.fake_keyring import memory_keyring

STARTERS = Path(__file__).resolve().parents[1] / "src" / "swissarmybench" / "starters"


@pytest.fixture(autouse=True)
def keyring() -> Iterator[None]:
    with memory_keyring():
        yield


def ok(response: Any) -> Any:
    assert response.status_code == 200, response.text
    return response.json()


def kind_of_template(t: Any) -> str | None:
    return ct.tables_kind(t.kind, t.id, t.dialect, t.catalog_language)


# ===== every starter: a tables kind, or no tables and why =====


def test_every_starter_has_tables_or_says_why_not() -> None:
    seen: set[str] = set()
    for t in TEMPLATES:
        found = kind_of_template(t)
        if found is None:
            reason = ct.no_tables_reason(t.kind, t.id)
            assert reason.startswith("not a connection") or reason.startswith("blades"), t.id
        else:
            assert found in ct.TABLE_KINDS, t.id
            seen.add(found)
    assert seen <= set(STOOD_IN), f"kinds with no stand-in test: {seen - set(STOOD_IN)}"
    # The built-in starter pack: snippets and actions, none a connection.
    for path in sorted(STARTERS.glob("*.blade.py")):
        blade = read_blade(path.read_text(encoding="utf-8"))
        assert connection_kind(str(blade["kind"]), blade.get("template")) is None, path.name
        assert ct.tables_kind(str(blade["kind"]), blade.get("template")) is None
    # Every kind of the contract has its stand-in here, and a key vault is not a connection.
    assert set(ct.TABLE_KINDS) == set(STOOD_IN)
    assert (
        ct.no_tables_reason("vault", "azure_key_vault")
        == "not a connection: a source of secrets for variables"
    )
    assert kind_of_template(BY_ID["dataverse"]) == "dataverse"  # the starter reads on the SQL endpoint
    assert ct.tables_kind("other", "python", tags=["api"]) == "api"


# ===== each kind on a made-up stand-in =====


def sqlite_db(tmp_path: Path) -> dict[str, Any]:
    path = tmp_path / "shop.sqlite"
    with sqlite3.connect(path) as made:
        made.execute("CREATE TABLE orders (order_id INTEGER, amount REAL)")
        made.executemany("INSERT INTO orders VALUES (?, ?)", [(1, 10.5), (2, 7.0), (3, 2.5)])
    code = (
        "import sqlite3\nfrom pathlib import Path\n\n"
        f'path = Path(r"{path}")\n'
        'conn = sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True)\n'
    )
    return {
        "name": "Kind",
        "kind": "sql",
        "template": "sqlite",
        "dialect": "sqlite",
        "code": code,
        "catalog": BY_ID["sqlite"].to_json()["catalog"],
    }


def database(client: TestClient, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[str, int]:
    ok(client.post("/connections", json=sqlite_db(tmp_path), headers=AUTH))
    return "orders", 3


def powerbi(client: TestClient, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[str, int]:
    from tests.test_powerbi import saved_connection

    running = made_up.StandIn().start()
    for name, value in running.environment().items():
        monkeypatch.setenv(name, value)
    STOPS.append(running.stop)
    saved_connection(client, "Kind")
    return '"Sales model".Product', 3


def dataverse_sql(client: TestClient, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[str, int]:
    body = {"name": "Kind", "kind": "sql", "template": "dataverse", "dialect": "dataverse"}
    body |= {"code": dataverse_tds_standin.code(tmp_path), "variable": "conn"}
    body |= {"catalog": BY_ID["dataverse"].to_json()["catalog"]}
    ok(client.post("/connections", json=body, headers=AUTH))
    return "account", len(dataverse_tds_standin.ACCOUNTS)


def dataverse_web(client: TestClient, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[str, int]:
    from tests.test_dataverse import saved_connection

    running = dataverse_standin.StandIn().start()
    for name, value in running.environment().items():
        monkeypatch.setenv(name, value)
    STOPS.append(running.stop)
    saved_connection(client, running, name="Kind")
    return "account", len(dataverse_standin.records()["account"])


PYTHON_CODE = """class Source:
    rows = {"orders": [{"order_id": 1, "amount": 10.5}, {"order_id": 2, "amount": 7.0}]}

    def tables(self):
        return [{"table_name": t, "column_name": c} for t, r in self.rows.items() for c in r[0]]

    def read(self, table, limit):
        found = self.rows[table]
        return (found if limit is None else found[:limit]), len(found)


conn = Source()
"""


def python(
    client: TestClient, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, tags: list[str] | None = None
) -> tuple[str, int]:
    body: dict[str, Any] = {"name": "Kind", "kind": "other", "template": "python", "variable": "conn"}
    body["code"] = PYTHON_CODE
    body |= {
        "catalog": {"language": "python", "command": "conn.tables()"},
        "read": {"command": "conn.read(table, limit)"},
    }
    ok(client.post("/connections", json=body | ({"tags": tags} if tags else {}), headers=AUTH))
    return "orders", 2


def api(client: TestClient, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[str, int]:
    """An Add API connection today: a Python connection whose tables are the API's table-returning calls
    (conn.tables(), conn.read(table, limit)); the blades version changes ct.is_api only."""
    return python(client, tmp_path, monkeypatch, tags=["api"])


def file(client: TestClient, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[str, int]:
    path = tmp_path / "budget.xlsx"
    with pd.ExcelWriter(path) as book:
        pd.DataFrame({"region": ["North", "South"], "plan": [10, 20]}).to_excel(
            book, sheet_name="Plan", index=False
        )
        pd.DataFrame({"region": ["North"], "actual": [9]}).to_excel(book, sheet_name="Actual", index=False)
    body = {"name": "Kind", "kind": "other", "template": "excel", "variable": "path"}
    body |= {
        "code": f'from pathlib import Path\n\npath = Path(r"{path}")',
        "catalog": BY_ID["excel"].to_json()["catalog"],
    }
    ok(client.post("/connections", json=body, headers=AUTH))
    return "Plan", 2


def folder(client: TestClient, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[str, int]:
    exports = tmp_path / "exports"
    exports.mkdir()
    (exports / "orders.csv").write_text("order_id,amount\n1,10.5\n2,7.0\n3,1.0\n", encoding="utf-8")
    (exports / "returns.csv").write_text("order_id\n2\n", encoding="utf-8")
    body = {"name": "Kind", "kind": "other", "template": "folder", "variable": "folder"}
    body |= {
        "code": f'from pathlib import Path\n\nfolder = Path(r"{exports}")',
        "catalog": BY_ID["folder"].to_json()["catalog"],
    }
    ok(client.post("/connections", json=body, headers=AUTH))
    return "orders", 3  # orders.csv, by its name without its suffix


def _lake(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Any:
    """The lake and SharePoint stand-in (tests/lake_standins.py), running for this test."""
    from tests import lake_standins

    lake_standins.make_lake(tmp_path / "storage")
    running = lake_standins.StandIn(tmp_path / "storage").start()
    for name, value in running.environment().items():
        monkeypatch.setenv(name, value)
    STOPS.append(running.stop)
    return lake_standins


def _lake_kind(template: str, code: str, client: TestClient, secrets: dict[str, str] | None = None) -> None:
    body: dict[str, Any] = {"name": "Kind", "kind": "sql", "template": template, "dialect": template}
    body |= {"code": code, "variable": "conn", "catalog": BY_ID[template].to_json()["catalog"]}
    ok(client.post("/connections", json=body | ({"secrets": secrets} if secrets else {}), headers=AUTH))


def onelake(client: TestClient, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[str, int]:
    from tests.test_lakes import onelake_code

    _lake(tmp_path, monkeypatch)
    _lake_kind("onelake", onelake_code(), client)
    return "orders", 5


def datalake(client: TestClient, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[str, int]:
    from tests.test_lakes import datalake_code

    made = _lake(tmp_path, monkeypatch)
    _lake_kind("datalake", datalake_code(), client, {"client secret": made.SECRET})
    return "returns", 2


def delta(client: TestClient, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[str, int]:
    from tests.test_lakes import way

    made = _lake(tmp_path, monkeypatch)
    root = tmp_path / "storage" / made.ACCOUNT / made.CONTAINER
    _lake_kind(
        "delta", way("delta", "A folder on this computer").replace('r"C:\\lake"', f'r"{root}"'), client
    )
    return "lake.orders", 5


def sharepoint_lists(client: TestClient, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[str, int]:
    from tests.test_lakes import sharepoint_code

    made = _lake(tmp_path, monkeypatch)
    _lake_kind("sharepoint", sharepoint_code(), client, {"password": made.PASSWORD})
    return "Tasks", 10


def sharepoint_docs(client: TestClient, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[str, int]:
    from tests.test_lakes import sharepoint_code

    made = _lake(tmp_path, monkeypatch)
    _lake_kind("sharepoint_docs", sharepoint_code("sharepoint_docs"), client, {"password": made.PASSWORD})
    return "Documents", 5


STOOD_IN: dict[str, Callable[..., tuple[str, int]]] = {
    "onelake": onelake,
    "datalake": datalake,
    "delta": delta,
    "sharepoint": sharepoint_lists,
    "sharepoint_docs": sharepoint_docs,
    "database": database,
    "powerbi": powerbi,
    "dataverse": dataverse_sql,
    "dataverse_web": dataverse_web,
    "python": python,
    "api": api,
    "file": file,
    "folder": folder,
}
STOPS: list[Callable[[], None]] = []


@pytest.fixture
def stops() -> Iterator[None]:
    yield
    while STOPS:
        STOPS.pop()()


@pytest.mark.parametrize("kind", sorted(STOOD_IN))
def test_each_kind_lists_and_reads_a_table_through_the_contract(
    kind: str, client: TestClient, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, stops: None
) -> None:
    table, count = STOOD_IN[kind](client, tmp_path, monkeypatch)
    tree = ok(client.get("/connections/Kind/tree", headers=AGENT))
    assert tree["kind"] == kind and tree["groups"], tree
    names = [t["table"] for g in tree["groups"] for t in g["tables"]]
    assert names, tree
    made = ok(
        client.post(
            "/datasets/counted/query",
            json={"sql": f"SELECT count(*) AS n FROM [Kind].{table}"},  # noqa: S608 (a test's own name)
            headers=AUTH,
        )
    )
    rows = ok(client.get(f"/grids/{made['grid']}/rows", headers=AUTH))["rows"]
    assert rows == [[count]], (kind, rows)
    assert made["connection_reads"][0]["connection"] == "Kind"


def test_a_dataverse_endpoint_that_is_off_is_said_plainly(client: TestClient, tmp_path: Path) -> None:
    body = {"name": "CRM", "kind": "sql", "template": "dataverse", "dialect": "dataverse", "variable": "conn"}
    body |= {
        "code": dataverse_tds_standin.code(tmp_path, off=True),
        "catalog": BY_ID["dataverse"].to_json()["catalog"],
    }
    ok(client.post("/connections", json=body, headers=AUTH))
    answer = client.post("/datasets/x/query", json={"sql": "SELECT * FROM [CRM].account"}, headers=AUTH)
    assert answer.status_code != 200
    assert "Power Platform admin center" in answer.text and "Web API" not in answer.text


def test_a_dataverse_connection_saved_for_the_web_api_switches_to_the_sql_endpoint(
    client: TestClient, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, stops: None
) -> None:
    dataverse_web(client, tmp_path, monkeypatch)
    card = next(
        c for c in ok(client.get("/connections/usage", headers=AUTH))["connections"] if c["name"] == "Kind"
    )
    assert card["reads"] == dataverse.WEB_API_WORDS and card["tables_kind"] == "dataverse_web"
    assert ok(client.post("/connections/Kind/sql-endpoint", headers=AGENT)) == {
        "name": "Kind",
        "changed": True,
    }
    after = ok(client.get("/connections/Kind", headers=AUTH))
    assert after["catalog"]["language"] == "sql"
    card = next(
        c for c in ok(client.get("/connections/usage", headers=AUTH))["connections"] if c["name"] == "Kind"
    )
    assert card["reads"] == "" and card["tables_kind"] == "dataverse"
