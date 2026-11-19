"""`${NAME}` at use, over HTTP (12.7): the preview, SQL as a bound parameter, a path, the missing error, a
connection's Test, and the first start's password move. Made-up values only."""

from __future__ import annotations

import json
import os
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pyarrow as pa
import pytest

from swissarmybench.domain import variable_refs as refs
from tests.conftest import AGENT, AUTH, grid_id, make_client, push
from tests.fake_keyring import memory_keyring

SECRET = "made-up-Pw-91x"


@pytest.fixture(autouse=True)
def keyring() -> Iterator[None]:
    with memory_keyring():
        yield


def _ok(response: Any) -> Any:
    assert response.status_code == 200, response.text
    return response.json()


def test_the_preview_masks_a_secret_and_says_what_is_missing(tmp_path: Path) -> None:
    with make_client(tmp_path) as client:
        _ok(client.put("/variables", json={"name": "TENANT", "value": "contoso"}, headers=AUTH))
        _ok(
            client.put(
                "/variables", json={"name": "SHOP_PASSWORD", "value": SECRET, "from": "keyring"}, headers=AUTH
            )
        )
        for headers in (AUTH, AGENT):
            shown = _ok(
                client.post(
                    "/variables/resolve",
                    json={"text": "https://${TENANT}.example.com/${SHOP_PASSWORD}/${NOPE}/$${KEPT}"},
                    headers=headers,
                )
            )
            assert SECRET not in json.dumps(shown)
            assert shown["value"] == "https://contoso.example.com/••••••••/${NOPE}/${KEPT}"
            assert shown["missing"] == ["NOPE"]
            assert shown["error"]["fixes"][0]["label"] == "Set it"
            words = {v["name"]: v["words"] for v in shown["variables"]}
            assert words == {
                "TENANT": "Plain value",
                "SHOP_PASSWORD": "This computer's keyring",
                "NOPE": "Not set",
            }


def test_sql_with_a_reference_binds_a_parameter(tmp_path: Path) -> None:
    with make_client(tmp_path) as client:
        people = pa.table({"name": ["Ana", "Bo", "Cy"], "region": ["North", "South", "North"]})
        grid = grid_id(push(client, "people", people))
        _ok(client.put("/variables", json={"name": "REGION", "value": "North"}, headers=AUTH))
        found = _ok(
            client.post(
                f"/grids/{grid}/sql",
                json={"sql": "SELECT name FROM grid WHERE region = ${REGION} ORDER BY name"},
                headers=AUTH,
            )
        )
        assert found["rows"] == [["Ana"], ["Cy"]]
        # A value with a quote cannot change what the query does.
        _ok(client.put("/variables", json={"name": "REGION", "value": "x' OR '1'='1"}, headers=AUTH))
        none = _ok(
            client.post(
                f"/grids/{grid}/sql",
                json={"sql": "SELECT name FROM grid WHERE region = ${REGION}"},
                headers=AGENT,
            )
        )
        assert none["rows"] == []
        # Inside a string it is the text as typed.
        literal = _ok(
            client.post(f"/grids/{grid}/sql", json={"sql": "SELECT '${REGION}' AS t"}, headers=AUTH)
        )
        assert literal["rows"] == [["${REGION}"]]
        # The "+" tab's query: the same rule; the query kept is the typed text.
        _ok(client.put("/variables", json={"name": "REGION", "value": "South"}, headers=AUTH))
        made = _ok(
            client.post(
                "/datasets/south/query",
                json={"sql": "SELECT * FROM people WHERE region = ${REGION}"},
                headers=AUTH,
            )
        )
        assert made["rows"] == 1
        # A name where a table's name goes is refused, never pasted.
        refused = client.post(f"/grids/{grid}/sql", json={"sql": "SELECT * FROM ${REGION}"}, headers=AUTH)
        assert refused.status_code == 400 and "never pasted" in refused.text


def test_a_missing_variable_is_the_one_error(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("NOT_SET_HERE", raising=False)
    with make_client(tmp_path) as client:
        grid = grid_id(push(client, "t", pa.table({"a": [1]})))
        missing = client.post(f"/grids/{grid}/sql", json={"sql": "SELECT ${NOT_SET_HERE}"}, headers=AUTH)
        assert missing.status_code == 422
        shape = missing.json()
        assert shape["error"] == "NOT_SET_HERE is not set on this computer (t)."
        assert shape["missing_variables"] == ["NOT_SET_HERE"]
        assert shape["fixes"] == [
            {"label": "Set it", "command": "variables_set", "page": "variables", "name": "NOT_SET_HERE"}
        ]


def test_a_path_reads_its_variable(tmp_path: Path) -> None:
    folder = tmp_path / "data"
    folder.mkdir()
    (folder / "orders.csv").write_text("id,amount\n1,10\n2,20\n", encoding="utf-8")
    with make_client(tmp_path) as client:
        _ok(client.put("/variables", json={"name": "DATA_FOLDER", "value": str(folder)}, headers=AUTH))
        loaded = client.post(
            "/datasets/orders/load", json={"path": "${DATA_FOLDER}/orders.csv"}, headers=AUTH
        )
        assert loaded.status_code == 200, loaded.text


def test_a_connections_test_says_a_setting_variable_is_not_set(tmp_path: Path) -> None:
    code = 'import os\nimport sqlite3\n\nconn = sqlite3.connect(database=os.environ["SHOP_DB_FILE"])\n'
    form = {"name": "Shop", "kind": "sql", "dialect": "sqlite", "code": code, "variable": "conn"}
    os.environ.pop("SHOP_DB_FILE", None)
    with make_client(tmp_path) as client:
        missing = client.post("/connections/test", json=form, headers=AUTH)
        assert missing.status_code == 422, missing.text
        assert missing.json()["error"] == "SHOP_DB_FILE is not set on this computer (Shop)."
        _ok(client.put("/variables", json={"name": "SHOP_DB_FILE", "value": ":memory:"}, headers=AUTH))
        tested = client.post("/connections/test", json=form, headers=AUTH)
        assert tested.status_code == 200, tested.text
        uses = _ok(client.get("/variables/uses", params={"name": "SHOP_DB_FILE"}, headers=AGENT))
        assert uses["uses"] == []  # a draft is not saved: nothing reads it yet
        _ok(client.post("/blades", json=form, headers=AUTH))
        uses = _ok(client.get("/variables/uses", params={"name": "SHOP_DB_FILE"}, headers=AGENT))
        assert uses["uses"] == [{"kind": "connection", "name": "Shop", "how": "database"}]


def test_the_first_start_makes_each_saved_password_a_variable(tmp_path: Path) -> None:
    code = "import sqlite3\npw = secret('password')\nconn = sqlite3.connect(':memory:')\n"
    blade = {"name": "Sales DB", "kind": "sql", "dialect": "sqlite", "code": code, "variable": "conn"}
    with make_client(tmp_path) as client:
        _ok(client.post("/blades", json=blade | {"secrets": {"password": SECRET}}, headers=AUTH))
    library = tmp_path / "state" / "library"
    before = {p.name: p.read_bytes() for p in (library / "connections").iterdir()}
    with make_client(tmp_path) as client:
        saved = _ok(client.get("/blades/Sales DB", headers=AUTH))
        assert "secret('SALES_DB_PASSWORD')" in json.dumps(saved)
        listed = {v["name"]: v for v in _ok(client.get("/variables", headers=AUTH))["variables"]}
        assert listed["SALES_DB_PASSWORD"]["from"] == "keyring"
        assert listed["SALES_DB_PASSWORD"]["editable"] is True
        shown = _ok(client.post("/variables/reveal", json={"name": "SALES_DB_PASSWORD"}, headers=AUTH))
        assert shown["value"] == SECRET
        notices = _ok(client.get("/library", headers=AUTH))["notices"]
        assert any("Sales DB's password as SALES_DB_PASSWORD" in n["text"] for n in notices)
        assert SECRET not in json.dumps(notices)
        backup = next((tmp_path / "state" / "backup").glob("before-variables-*"))
        assert {p.name: p.read_bytes() for p in backup.iterdir()} == before
        for written in library.rglob("*"):
            if written.is_file():
                assert SECRET.encode() not in written.read_bytes()
    after = {p.name: p.read_bytes() for p in (library / "connections").iterdir()}
    with make_client(tmp_path):
        pass  # a second start moves nothing: no byte changes
    assert {p.name: p.read_bytes() for p in (library / "connections").iterdir()} == after


def test_saved_text_that_now_names_a_variable_is_said_once(tmp_path: Path) -> None:
    code = 'import sqlite3\nconn = sqlite3.connect(database="C:/data/${YEAR}/shop.db")\n'
    blade = {"name": "Shop", "kind": "sql", "dialect": "sqlite", "code": code, "variable": "conn"}
    with make_client(tmp_path) as client:
        _ok(client.post("/blades", json=blade, headers=AUTH))
    assert not (
        tmp_path / "state" / "variable_refs.json"
    ).exists()  # the list is said once something holds one
    with make_client(tmp_path) as client:
        notices = _ok(client.get("/library", headers=AUTH))["notices"]
        assert any("Shop: database (${YEAR})" in n["text"] for n in notices)
    with make_client(tmp_path) as client:
        notices = _ok(client.get("/library", headers=AUTH))["notices"]
        assert not any("${YEAR}" in n["text"] for n in notices)


def test_a_sql_cell_binds_in_the_drivers_style(monkeypatch: pytest.MonkeyPatch) -> None:
    """%%sql and sab.sql in a kernel: sqlite3 (qmark) and DuckDB ($1), the value from the environment."""
    import sqlite3

    import duckdb

    from swissarmybench.client import sql_cell

    monkeypatch.setenv("WHO", "Ana' OR '1'='1")
    lite = sqlite3.connect(":memory:")
    lite.execute("CREATE TABLE people (name TEXT)")
    lite.executemany("INSERT INTO people VALUES (?)", [("Ana",), ("Bo",)])
    rows = sql_cell._run_database(lite, "SELECT count(*) AS n FROM people WHERE name = ${WHO}")
    assert list(rows["n"]) == [0]
    monkeypatch.setenv("WHO", "Ana")
    rows = sql_cell._run_database(lite, "SELECT count(*) AS n FROM people WHERE name = ${WHO} -- ${NOT_READ}")
    assert list(rows["n"]) == [1]
    duck = duckdb.connect()
    assert list(sql_cell._run_database(duck, "SELECT ${WHO} AS who")["who"]) == ["Ana"]
    monkeypatch.delenv("NOT_SET_HERE", raising=False)
    with pytest.raises(refs.MissingVariables, match="NOT_SET_HERE is not set on this computer"):
        sql_cell._run_database(duck, "SELECT ${NOT_SET_HERE}")


def test_the_agent_tools_exist() -> None:
    from swissarmybench.cli.commands import REGISTRY

    names = set(REGISTRY)
    assert {"variables_resolve", "variables_uses"} <= names
    assert refs.MissingVariables(["A"]).to_json()["error"] == "A is not set on this computer."
