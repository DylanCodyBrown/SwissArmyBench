"""The Environment (the owner, 2026-11-21/22; Plans/environment.plan.md) over HTTP: one list of everything
the project holds, where each thing is used, Remove, Rename, Clear, Keep, and the project's libraries (Pin,
Update, Install) with the agent waiting for the user's Allow. Made-up data only; the installs and the index
are stood in."""

from __future__ import annotations

import json
import threading
import time
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pyarrow as pa
import pytest
from starlette.testclient import TestClient

from swissarmybench.adapters import environment as environment_files
from swissarmybench.cli import commands
from swissarmybench.server import environments
from tests.conftest import AGENT, AUTH, PORT, push
from tests.fake_keyring import memory_keyring

ORDERS = pa.table(
    {
        "order_id": [100001, 100002, 100003],
        "customer_id": [4417, 2093, None],
        "amount": [12.5, 9840.0, 77.25],
    }
)
CUSTOMERS = pa.table({"customer_id": [4417, 2093], "name": ["Avery Lane", "Brook Tide"]})


def _cell(source: str) -> dict[str, Any]:
    return {"cell_type": "code", "metadata": {}, "source": source, "outputs": [], "execution_count": None}


NOTEBOOK = {
    "nbformat": 4,
    "nbformat_minor": 5,
    "metadata": {},
    "cells": [_cell("import duckdb\nimport pandas as pd"), _cell("late = orders[orders.amount > 50]")],
}
SECRET = {"name": "WAREHOUSE_PASSWORD", "value": "made-up-Zx81", "from": "keyring"}
RATES = {"text": '{"regions": {"North": {"rate": 0.0825}}}', "name": "rates"}


@pytest.fixture(autouse=True)
def vault() -> Iterator[None]:
    with memory_keyring():
        yield


def ok(response: Any) -> Any:
    assert response.status_code == 200, response.text
    return response.json()


def rows(client: TestClient, search: str = "") -> dict[str, dict[str, Any]]:
    listing = ok(client.get("/environment", params={"search": search}, headers=AUTH))
    return {r["id"]: r for r in listing["items"]}


def fake_venv(project: Path, libraries: dict[str, str]) -> None:
    """A project's .venv as the Libraries tab reads it: a Python's place and each library's metadata."""
    python = environment_files.venv_python(project)
    python.parent.mkdir(parents=True)
    python.write_text("", encoding="utf-8")
    (project / ".venv" / "pyvenv.cfg").write_text("version = 3.12.7\n", encoding="utf-8")
    site = project / ".venv" / "lib" / "python3.12" / "site-packages"
    for name, version in libraries.items():
        folder = site / f"{name.replace('-', '_')}-{version}.dist-info"
        if folder.parent.exists():
            for old in site.glob(f"{name.replace('-', '_')}-*.dist-info"):
                (old / "METADATA").unlink()
                old.rmdir()
        folder.mkdir(parents=True)
        (folder / "METADATA").write_text(f"Metadata-Version: 2.1\nName: {name}\nVersion: {version}\n")


@pytest.fixture
def project(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Where a made-up project goes; installs write the stand-in venv, the index answers made-up versions."""
    folder = tmp_path / "work" / "month_end"
    index = {"duckdb": "1.4.3", "pandas": "2.3.3", "polars": "1.36.0"}
    monkeypatch.setattr(environment_files, "_newest", lambda _index, name: index.get(name.lower()))

    async def install(python: str, specs: list[str], upgrade: bool = False) -> tuple[int | None, str]:
        wanted = {}
        for spec in specs:
            name, _, version = spec.partition("==")
            wanted[name] = version or index.get(name, "1.0.0")
        fake_venv_update(Path(python).parent.parent.parent, wanted)
        return 0, "Installed"

    monkeypatch.setattr(environments, "install", install)
    return folder


def fake_venv_update(project: Path, libraries: dict[str, str]) -> None:
    site = project / ".venv" / "lib" / "python3.12" / "site-packages"
    for name, version in libraries.items():
        for old in site.glob(f"{name.replace('-', '_')}-*.dist-info"):
            (old / "METADATA").unlink()
            old.rmdir()
        folder = site / f"{name.replace('-', '_')}-{version}.dist-info"
        folder.mkdir(parents=True)
        (folder / "METADATA").write_text(f"Metadata-Version: 2.1\nName: {name}\nVersion: {version}\n")


def open_project(client: TestClient, folder: Path) -> None:
    ok(client.post("/project/new", json={"path": str(folder)}, headers=AUTH))
    (folder / "analysis.ipynb").write_text(json.dumps(NOTEBOOK), encoding="utf-8")


def test_one_list_holds_every_kind_with_where_each_is_used(client: TestClient, project: Path) -> None:
    open_project(client, project)
    grid = ok(push(client, "orders", ORDERS))["grid"]
    ok(push(client, "customers", CUSTOMERS))
    ok(
        client.put(
            "/variables", json={"name": "WAREHOUSE_HOST", "value": "sql.larkfield.example"}, headers=AUTH
        )
    )
    ok(client.put("/variables", json=SECRET, headers=AUTH))
    ok(client.post("/structures/paste", json=RATES, headers=AUTH))
    listing = ok(client.get("/environment", headers=AUTH))
    assert [t["name"] for t in listing["tabs"]] == [
        "Tables",
        "Variables",
        "Structures",
        "Settings and secrets",
        "Libraries",
    ]
    assert listing["tabs"][0]["columns"] == ["Name", "Rows by columns", "Columns", "Grids", "Used in", "From"]
    assert listing["counts"]["table"] == 2 and listing["counts"]["structure"] == 1
    assert listing["project"]["name"] == "month_end"
    found = {r["id"]: r for r in listing["items"]}
    orders = found["table:orders"]
    assert orders["size"] == "3 × 3" and orders["value"] == "order_id, customer_id, amount"
    # A grid is a view of the table, never a copy: the row says which grids show it.
    assert orders["grids"] == [{"id": grid, "name": "orders", "steps": 0}]
    used = {(u["kind"], u["words"]) for u in orders["used"]}
    assert ("grid", "orders") in used and ("cell", "analysis.ipynb · cell 2") in used
    link = next(u["link"] for u in orders["used"] if u["kind"] == "cell")
    assert link["to"] == "document" and link["cell"] == 2 and link["path"].endswith("analysis.ipynb")
    assert orders["kids"][0] == ["order_id", "whole number", ""]
    # A secret's value is never in the list; a plain setting's is.
    text = json.dumps(listing)
    assert "made-up-Zx81" not in text and "sql.larkfield.example" in text
    assert found["setting:WAREHOUSE_PASSWORD"]["type"] == "Secret"
    assert found["structure:rates"]["kids"][0][0].startswith("$.regions")
    # A table unfolds to its columns with their ranges and blanks; show gives the same, whole.
    columns = ok(client.get("/environment/columns", params={"name": "orders"}, headers=AUTH))["columns"]
    assert columns[1] == ["customer_id", "whole number", "2093 to 4417 · 1 blank"]
    shown = ok(client.get("/environment/show", params={"kind": "table", "name": "orders"}, headers=AUTH))
    assert shown["kids"] == columns
    assert (
        client.get("/environment/show", params={"kind": "table", "name": "nope"}, headers=AUTH).status_code
        == 404
    )


def test_one_search_runs_over_every_tab(client: TestClient, project: Path) -> None:
    open_project(client, project)
    ok(push(client, "orders", ORDERS))
    ok(push(client, "customers", CUSTOMERS))
    ok(client.put("/variables", json={"name": "CUSTOMER_API", "value": "https://api.example"}, headers=AUTH))
    listing = ok(client.get("/environment", params={"search": "cust"}, headers=AUTH))
    assert listing["counts"] == {"table": 2, "variable": 0, "structure": 0, "setting": 1, "library": 0}
    found = {r["id"]: r for r in listing["items"]}
    assert found["table:orders"]["match"] == {"own": True, "kids": [1]}  # customer_id, inside
    assert found["table:customers"]["match"]["own"] is True
    assert set(found) == {"table:orders", "table:customers", "setting:CUSTOMER_API"}
    assert rows(client, "amount late") == {} or "table:orders" in rows(client, "amount")


def test_remove_rename_and_clear(client: TestClient, project: Path) -> None:
    open_project(client, project)
    ok(push(client, "orders", ORDERS))
    ok(push(client, "scratch", CUSTOMERS))
    renamed = ok(
        client.post(
            "/environment/rename", json={"kind": "table", "name": "scratch", "to": "people"}, headers=AUTH
        )
    )
    assert renamed["name"] == "people" and "table:people" in rows(client)
    ok(client.post("/environment/remove", json={"kind": "table", "name": "people"}, headers=AUTH))
    assert "table:people" not in rows(client)
    assert client.get("/datasets", headers=AUTH).json()["datasets"][0]["name"] == "orders"
    # Clear…: the ticks; a dry run says what each would take; the agent's waits for the user's Allow.
    would = ok(client.post("/environment/clear", json={"dry_run": True}, headers=AUTH))["would"]
    assert would == {"tables": ["orders"], "variables": [], "structures": []}
    assert client.post("/environment/clear", json={}, headers=AUTH).status_code == 400
    answer: dict[str, Any] = {}
    waiting = threading.Thread(
        target=lambda: answer.update(
            r=client.post("/environment/clear", json={"tables": True}, headers=AGENT)
        )
    )
    waiting.start()
    pending: list[Any] = []
    for _ in range(100):
        pending = ok(client.get("/agent/approvals", headers=AUTH))["pending"]
        if pending:
            break
        time.sleep(0.05)
    assert pending and pending[0]["detail"] == "Clear 1 table"
    ok(client.post(f"/agent/approvals/{pending[0]['id']}", json={"approve": False}, headers=AUTH))
    waiting.join(10)
    assert answer["r"].status_code == 403 and "table:orders" in rows(client)
    cleared = ok(client.post("/environment/clear", json={"tables": True}, headers=AUTH))
    assert cleared == {"cleared": {"tables": ["orders"]}} and rows(client).keys().isdisjoint({"table:orders"})


def test_a_table_python_holds_is_listed_and_a_change_is_said_once(client: TestClient, project: Path) -> None:
    table = {"name": "monthly", "kind": "dataframe", "rows": 12, "columns": 4}
    body = {"label": "data.ipynb", "pid": 4242, "tables": [table]}
    with client.websocket_connect("/ws?catalog=1", headers=AUTH | {"Host": f"127.0.0.1:{PORT}"}) as socket:
        ok(client.post("/processes/s1/sync", json=body, headers=AUTH))
        heard = []
        for _ in range(20):
            notice = socket.receive_json()
            heard.append(notice["type"])
            if notice["type"] == "environment_changed":
                break
        assert heard[-1] == "environment_changed" and "processes_changed" in heard
    monthly = rows(client)["table:monthly"]
    assert (
        monthly["type"] == "pandas table" and monthly["size"] == "12 × 4" and monthly["from"] == "data.ipynb"
    )
    assert monthly["tags"] == ["In Python"] and monthly["grids"] == []
    # Only in Python: Remove needs the tick; Open asks its session to send it (the grid arrives by itself).
    refused = client.post("/environment/remove", json={"kind": "table", "name": "monthly"}, headers=AUTH)
    assert refused.status_code == 409 and "Also delete it in Python" in refused.json()["error"]
    opened = ok(client.post("/environment/open", json={"kind": "table", "name": "monthly"}, headers=AUTH))
    assert opened == {"link": {"to": "python", "name": "monthly"}}
    asked = ok(client.get("/processes/s1/requests?wait=0", headers=AUTH))["requests"]
    assert asked == [{"action": "load", "name": "monthly"}]


def test_open_a_table_makes_a_view_never_a_copy_and_insert_gives_code(client: TestClient) -> None:
    grid = ok(push(client, "orders", ORDERS))["grid"]
    link = ok(client.post("/environment/open", json={"kind": "table", "name": "orders"}, headers=AUTH))[
        "link"
    ]
    assert link["to"] == "grid" and link["grid"] == grid
    assert len(ok(client.get("/datasets", headers=AUTH))["datasets"]) == 1
    code = ok(client.post("/environment/insert", json={"kind": "table", "name": "orders"}, headers=AUTH))
    assert code == {"sql": "SELECT * FROM orders", "python": "orders"}
    code = ok(client.post("/environment/insert", json={"kind": "library", "name": "pandas"}, headers=AUTH))
    assert code == {"python": "import pandas as pd"}


def test_libraries_pin_update_and_install(client: TestClient, project: Path) -> None:
    open_project(client, project)
    fake_venv(project, {"duckdb": "1.4.2", "pandas": "2.3.3", "pip": "25.0"})
    (project / "requirements.txt").write_text("duckdb\npandas\n", encoding="utf-8")
    listed = ok(client.get("/environment/libraries", headers=AUTH))
    assert listed["python"]["own"] is True and listed["python"]["version"] == "3.12" and not listed["checked"]
    by = {r["name"]: r for r in listed["libraries"]}
    assert list(by) == ["duckdb", "pandas"]  # pip: nobody chose it
    assert by["duckdb"]["version"] == "1.4.2" and by["duckdb"]["latest"] is None
    assert [u["words"] for u in by["pandas"]["used"]] == ["analysis.ipynb · cell 1"]
    # The index is asked only when the tab opens (check): never by the plain list.
    checked = ok(client.get("/environment/libraries", params={"check": "1"}, headers=AUTH))
    by = {r["name"]: r for r in checked["libraries"]}
    assert by["duckdb"]["latest"] == "1.4.3" and by["pandas"]["latest"] is None
    assert checked["outdated"] == ["duckdb"] and checked["checked"]
    # Pin keeps it at its version in requirements.txt; Update all skips a pinned one.
    pinned = ok(client.post("/environment/libraries/pin", json={"name": "duckdb"}, headers=AUTH))
    assert pinned == {"name": "duckdb", "pinned": True, "changed": True}
    assert (project / "requirements.txt").read_text() == "duckdb==1.4.2\npandas\n"
    assert ok(client.post("/environment/libraries/update", json={"all": True}, headers=AUTH)) == {
        "updated": []
    }
    # Updated by name, a pinned library is pinned at its new version.
    updated = ok(client.post("/environment/libraries/update", json={"name": "duckdb"}, headers=AUTH))
    assert updated == {"updated": [{"name": "duckdb", "version": "1.4.3"}]}
    assert (project / "requirements.txt").read_text() == "duckdb==1.4.3\npandas\n"
    ok(client.post("/environment/libraries/pin", json={"name": "duckdb", "pinned": False}, headers=AUTH))
    assert (project / "requirements.txt").read_text() == "duckdb\npandas\n"
    # Install a library…: into the project's Python and requirements.txt.
    assert ok(client.post("/environment/libraries/install", json={"name": "polars"}, headers=AUTH)) == {
        "installed": "polars"
    }
    assert (project / "requirements.txt").read_text() == "duckdb\npandas\npolars\n"
    assert "library:polars" in rows(client)
    bad = client.post("/environment/libraries/install", json={"name": "polars --index-url x"}, headers=AUTH)
    assert bad.status_code == 400


def test_the_agents_install_waits_for_allow(client: TestClient, project: Path) -> None:
    open_project(client, project)
    fake_venv(project, {"duckdb": "1.4.2"})
    answer: dict[str, Any] = {}
    waiting = threading.Thread(
        target=lambda: answer.update(
            r=client.post("/environment/libraries/install", json={"name": "polars"}, headers=AGENT)
        )
    )
    waiting.start()
    pending: list[Any] = []
    for _ in range(100):
        pending = ok(client.get("/agent/approvals", headers=AUTH))["pending"]
        if pending:
            break
        time.sleep(0.05)
    assert pending and pending[0]["detail"] == "Install polars"
    ok(client.post(f"/agent/approvals/{pending[0]['id']}", json={"approve": True}, headers=AUTH))
    waiting.join(10)
    assert answer["r"].status_code == 200 and "polars" in (project / "requirements.txt").read_text()


def test_the_agents_one_tool_names_every_action() -> None:
    tool = commands.REGISTRY["environment"]
    assert set(commands._ENVIRONMENT) == {
        "list", "show", "libraries", "open", "rename", "keep", "insert", "remove", "clear", "install",
        "update", "pin", "python", "set_python",
    }  # fmt: skip
    assert "Allow" in tool.summary
    with pytest.raises(commands.CommandError, match="action is one of"):
        tool.run({"action": "refresh"})


def test_a_cell_that_ran_says_so_and_a_sessions_variables_are_listed_by_name_and_size(
    client: TestClient,
) -> None:
    held = [
        {"name": "tax_rate", "type": "float", "size": ""},
        {"name": "regions", "type": "list", "size": "5"},
    ]
    body: dict[str, Any] = {"label": "month_end.py", "pid": 4242, "tables": [], "variables": held, "ran": 1}
    with client.websocket_connect("/ws?catalog=1", headers=AUTH | {"Host": f"127.0.0.1:{PORT}"}) as socket:
        ok(client.post("/processes/s2/sync", json=body, headers=AUTH))
        heard = [socket.receive_json()["type"] for _ in range(2)]
        assert heard == ["processes_changed", "environment_changed"]
        # The same again is a heartbeat: nothing is said. A cell that ran (no table changed) is.
        ok(client.post("/processes/s2/sync", json=body, headers=AUTH))
        ok(client.post("/processes/s2/sync", json=body | {"ran": 2}, headers=AUTH))
        assert socket.receive_json()["type"] == "environment_changed"
    found = rows(client)
    assert found["variable:tax_rate"]["type"] == "Number"
    assert found["variable:tax_rate"]["from"] == "month_end.py"
    assert found["variable:regions"]["size"] == "5 items" and found["variable:regions"]["value"] == ""
    # What the page's Open list reads is as it was: no new field.
    listed = ok(client.get("/processes", headers=AUTH))["processes"]
    assert set(listed[0]) == {"id", "label", "pid", "tables"}


def test_the_kernels_helpers_never_copy_and_never_touch_private_names() -> None:
    from swissarmybench.client import kernel_variables

    orders = [1, 2, 3]
    namespace: dict[str, Any] = {
        "orders": orders,
        "tax_rate": 0.0825,
        "_hidden": 1,
        "payload": {"paid": False},
    }
    assert kernel_variables.names(namespace) == [
        {"name": "orders", "type": "list", "size": "3"},
        {"name": "payload", "type": "dict", "size": "1"},
        {"name": "tax_rate", "type": "float", "size": ""},
    ]
    assert json.loads(kernel_variables.rename("orders", "sales", namespace)) == {"renamed": True}
    assert namespace["sales"] is orders and "orders" not in namespace  # the same object, never a copy
    taken = json.loads(kernel_variables.rename("sales", "tax_rate", namespace))
    assert not taken["renamed"] and "already a variable" in taken["why"]
    assert json.loads(kernel_variables.forget(["sales", "_hidden", "gone"], namespace)) == ["sales"]
    assert set(namespace) == {"tax_rate", "_hidden", "payload"}
    shown = json.loads(kernel_variables.snapshot([], namespace))["variables"]
    assert shown[0]["name"] == "payload" and shown[0]["kids"] == [["paid", "bool", "False"]]


def test_the_watcher_looks_at_once_after_a_cell_runs() -> None:
    from swissarmybench.client.watcher import Watcher

    namespace: dict[str, Any] = {"tax_rate": 0.0825}
    watcher = Watcher(lambda: namespace, "data.ipynb", scan_seconds=30.0)
    sent: list[dict[str, Any]] = []

    def call(method: str, path: str, body: Any = None, timeout: float = 10.0) -> Any:
        sent.append(body)
        return {"following": []}

    watcher._call = call  # type: ignore[method-assign]
    scan = threading.Thread(target=watcher._scan_loop, daemon=True)
    scan.start()
    try:
        watcher.ran()  # the post-run hook's call: no waiting for the 30 second timer
        for _ in range(100):
            if sent:
                break
            time.sleep(0.02)
        assert sent and sent[0]["ran"] == 1
        assert sent[0]["variables"] == [{"name": "tax_rate", "type": "float", "size": ""}]
        assert "0.0825" not in json.dumps(sent[0])  # names, types and sizes only: never a value
    finally:
        watcher.stop()
        scan.join(5)
