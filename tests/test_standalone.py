"""A saved notebook runs without the app (client/standalone.py): sab.sql, sab.connection and sab.blade
find a connection on this computer, in a blade folder, beside the notebook or in the starter pack, with
its password from the keyring or an environment variable. Also: a table that came whole is read whole
again by its notebook cell (no LIMIT to cut a scheduled run short). Made-up data only."""

from __future__ import annotations

import os
import sqlite3
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from starlette.testclient import TestClient

from swissarmybench.adapters.blade_run import BladeRunError
from swissarmybench.client import blades_client, sql_cell, standalone
from swissarmybench.client.push_client import ServerNotRunningError
from swissarmybench.domain.blades import write_blade
from tests.conftest import AUTH, make_client
from tests.fake_keyring import memory_keyring
from tests.test_connections import sqlite_connection


@pytest.fixture
def made_up_shop(tmp_path: Path) -> Path:
    database = tmp_path / "shop.sqlite"
    with sqlite3.connect(database) as db:
        db.execute("CREATE TABLE orders (order_id INTEGER, status TEXT)")
        db.executemany(
            "INSERT INTO orders VALUES (?, ?)", [(i, " Shipped" if i % 2 else "test") for i in range(7)]
        )
    return database


@pytest.fixture
def no_app(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Path]:
    """No server answers; the app's own folder is a fresh one; the current folder is the notebook's."""
    state = tmp_path / "state"
    monkeypatch.setenv("SWISSARMYBENCH_INFO", str(tmp_path / "nobody" / "server.json"))
    monkeypatch.setenv("SWISSARMYBENCH_STATE", str(state))
    monkeypatch.delenv("SWISSARMYBENCH_BLADE_FOLDERS", raising=False)
    notebook = tmp_path / "function"
    notebook.mkdir()
    monkeypatch.chdir(notebook)
    sql_cell._connections.clear()
    yield state
    sql_cell._connections.clear()


def password_connection(database: Path) -> dict[str, Any]:
    """The SQLite connection, with a made-up password its code asks for (SQLite needs none: the code
    checks it, as a server would)."""
    made = sqlite_connection(database)
    made["code"] += 'if secret("password") != "made-up-password":\n    raise ValueError("wrong password")\n'
    return made


def test_without_the_app_a_saved_connection_runs_with_its_password_from_the_keyring(
    made_up_shop: Path, no_app: Path
) -> None:
    with memory_keyring():
        with make_client(no_app.parent) as client:
            saved = client.post("/connections", json=password_connection(made_up_shop), headers=AUTH)
            assert saved.status_code == 200, saved.text
            put = client.put("/blades/Shop/secrets", json={"password": "made-up-password"}, headers=AUTH)
            assert put.status_code == 200, put.text
        # The app is closed (no connection file names a server): the notebook's line runs as it is.
        with pytest.raises(ServerNotRunningError):
            blades_client._call("GET", "/connections")
        frame = sql_cell.sql("Shop", "SELECT order_id FROM orders WHERE status = 'test'")
        assert list(frame["order_id"]) == [0, 2, 4, 6]
        assert standalone.spec("shop")["secrets"] == {"password": "made-up-password"}


def test_without_the_app_a_password_saved_in_the_form_is_its_keyring_variable_and_is_found(
    made_up_shop: Path, no_app: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A password saved through the connection form is a keyring variable of the library
    (`secret("SHOP_PASSWORD")`, variables.toml's `from = "keyring"`): the app gives it to what it starts
    while it runs, and a scheduled run on this computer with the app closed finds it the same way. A
    plain variable the code reads through os.environ (a setting's ${NAME}) is found too; a value the
    run's own environment sets wins."""
    made = sqlite_connection(made_up_shop)
    made["code"] = (
        "import os\n"
        + made["code"]
        + (
            'if secret("SHOP_PASSWORD") != "made-up-password":\n    raise ValueError("wrong password")\n'
            'if os.environ["SHOP_REGION"] != "North":\n    raise ValueError("wrong region")\n'
        )
    )
    for name in ("SHOP_PASSWORD", "SHOP_REGION"):  # set, then taken away: put back as they were after
        monkeypatch.setenv(name, "")
        monkeypatch.delenv(name)
    with memory_keyring():
        with make_client(no_app.parent) as client:
            for variable in (
                {"name": "SHOP_PASSWORD", "value": "made-up-password", "from": "keyring"},
                {"name": "SHOP_REGION", "value": "North", "from": "value", "local": True},
            ):
                put = client.put("/variables", json=variable, headers=AUTH)
                assert put.status_code == 200, put.text
            saved = client.post("/connections", json=made, headers=AUTH)
            assert saved.status_code == 200, saved.text
        assert "SHOP_PASSWORD" not in os.environ  # the app's values went with it
        frame = sql_cell.sql("Shop", "SELECT count(*) AS n FROM orders")
        assert int(frame["n"][0]) == 7
        assert standalone.spec("Shop")["secrets"] == {"SHOP_PASSWORD": "made-up-password"}
        assert os.environ["SHOP_REGION"] == "North" and "SHOP_PASSWORD" not in os.environ
        monkeypatch.setenv("SHOP_PASSWORD", "from the run")  # the run's own setting first
        assert standalone.spec("Shop")["secrets"] == {"SHOP_PASSWORD": "from the run"}


def test_without_the_app_an_exported_connection_beside_the_notebook_takes_its_password_from_the_environment(
    made_up_shop: Path, no_app: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An Azure Function: no saved connections, no keyring; the connection's exported file in the
    function's folder (or its blades/ folder) and the password in the function's settings."""
    exported = write_blade(password_connection(made_up_shop) | {"variable": "conn"})
    (Path.cwd() / "blades").mkdir()
    (Path.cwd() / "blades" / "shop.blade.py").write_text(exported, encoding="utf-8")
    with pytest.raises(BladeRunError, match=r"SHOP_PASSWORD|password"):
        blades_client.blade("Shop")  # no value anywhere: the code's own secret() says so
    monkeypatch.setenv("SHOP_PASSWORD", "made-up-password")  # the connection's name, then the secret's
    frame = sql_cell.sql("Shop", "SELECT count(*) AS n FROM orders")
    assert int(frame["n"][0]) == 7
    assert standalone.record("Shop")["connection"] == "database"
    assert [r["name"] for r in standalone.records()] == ["Shop"]


def test_without_the_app_blade_folders_and_starters_are_found_and_a_missing_name_says_where_it_looked(
    no_app: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    folder = tmp_path / "team blades"
    folder.mkdir()
    (folder / "greeting.py").write_text(
        write_blade({"name": "Greeting", "kind": "other", "variable": "hello", "code": 'hello = "made up"'}),
        encoding="utf-8",
    )
    monkeypatch.setenv("SWISSARMYBENCH_BLADE_FOLDERS", str(folder))
    assert blades_client.blade("Greeting") == "made up"
    copy_template = blades_client.blade("Excel copy template")  # a starter, shipped in the package
    assert callable(copy_template)
    with pytest.raises(LookupError, match=r"not running.*Nothing here"):
        blades_client.blade("Nothing here")
    with pytest.raises(sql_cell.SqlCellError, match="Nothing here"):
        sql_cell.sql("Nothing here", "SELECT 1")


def test_a_table_that_came_whole_is_read_whole_again_by_its_notebook_cell(
    tmp_path: Path, made_up_shop: Path
) -> None:
    """Rows to open is 10,000: the 7-row table came whole, so its cell has no LIMIT (a scheduled run a
    year later, with 20,000 rows, must not stop at 10,000 without a word). A table that was cut keeps
    the LIMIT the grid shows."""
    with make_client(tmp_path) as client:
        client.post("/connections", json=sqlite_connection(made_up_shop), headers=AUTH)
        assert (
            client.post("/connections/Shop/open", json={"table": "orders"}, headers=AUTH).status_code == 200
        )
        whole = cell_text(client, "orders")
        assert 'sab.sql(\'Shop\', """\nSELECT *\nFROM "orders"\n"""' in whole and "LIMIT" not in whole
        client.post(
            "/connections", json=sqlite_connection(made_up_shop, 3) | {"name": "Shop 3"}, headers=AUTH
        )
        cut = client.post("/connections/Shop%203/open", json={"table": "orders"}, headers=AUTH).json()
        assert cut["shown"] == 3 and cut["total"] == 7
        assert "LIMIT 3" in cell_text(client, cut["dataset"])


def cell_text(client: TestClient, table: str) -> str:
    listed = client.get("/workbench/tables", headers=AUTH).json()["tables"]
    return "\n".join(str(t["loaded"]) for t in listed if t["name"] == table)


def test_the_standalone_spec_matches_the_apps_own(made_up_shop: Path, no_app: Path) -> None:
    """The two places that build what sab.blade() runs say the same thing (services/blades.py for_python
    and client/standalone.py spec)."""
    with memory_keyring():
        with make_client(no_app.parent) as client:
            client.post("/connections", json=password_connection(made_up_shop), headers=AUTH)
            client.put("/blades/Shop/secrets", json={"password": "made-up-password"}, headers=AUTH)
            app_spec = client.get("/blades/Shop/python", headers=AUTH).json()
        local = standalone.spec("Shop")
    assert local == app_spec
    assert local["secrets"] == {"password": "made-up-password"} and local["vaults"] == []
    assert os.environ.get("SHOP_PASSWORD") is None
