"""A project as one .sab file on the running server (services/sab_projects.py): save, close and open
again with everything back (a CSV table with two steps, a SQLite connection's table, a pasted table
ticked and not, a notebook, a canvas, a Sandbox card, the relationships); a missing connection or file
says how to fix it; no secret is ever in the file; the agent's save asks only when it writes rows.
Made-up data only."""

from __future__ import annotations

import json
import sqlite3
import threading
import time
import zipfile
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from starlette.testclient import TestClient

from swissarmybench.domain import notebooks, streamlit_cells
from tests.conftest import AGENT, AUTH, TOKEN, make_client
from tests.fake_keyring import memory_keyring

KEYRING_SECRET = "made-up-keyring-pa55"
VAULT_SECRET = "made-up-vault-s3cret"
TYPED_SECRET = "made-up-typed-passw0rd"

STEPS = [
    {"kind": "filter", "params": {"column": "region", "op": "ne", "value": "East"}},
    {"kind": "sort", "params": {"keys": [["units", "desc"]]}},
]


@pytest.fixture(autouse=True)
def vault() -> Iterator[None]:
    with memory_keyring():
        yield


def ok(response: Any) -> Any:
    assert response.status_code == 200, response.text
    return response.json()


def project(client: TestClient) -> dict[str, Any]:
    return dict(ok(client.get("/project", headers=AUTH)))


def shop(path: Path) -> dict[str, Any]:
    """A SQLite connection whose code needs a password from the keyring (made up)."""
    code = (
        "import sqlite3\nfrom pathlib import Path\n\n"
        f'assert secret("password") == "{KEYRING_SECRET}"\n'
        f'path = Path(r"{path}")\n'
        'conn = sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True)\n'
    )
    return {
        "name": "Shop",
        "kind": "sql",
        "template": "sqlite",
        "dialect": "sqlite",
        "code": code,
        "secrets": {"password": KEYRING_SECRET},
    }


def made_up_files(tmp_path: Path) -> tuple[Path, Path]:
    work = tmp_path / "work"
    work.mkdir()
    csv = work / "orders.csv"
    csv.write_text("order_id,region,units\n1,North,3\n2,East,9\n3,South,5\n4,North,7\n", encoding="utf-8")
    database = tmp_path / "shop.sqlite"
    with sqlite3.connect(database) as made_up:
        made_up.execute("CREATE TABLE customers (customer_id INTEGER, city TEXT)")
        made_up.executemany("INSERT INTO customers VALUES (?, ?)", [(1, "Springfield"), (2, "Shelbyville")])
    return csv, database


def build_project(client: TestClient, tmp_path: Path) -> dict[str, Any]:
    """A project with a CSV table and two steps, a connection's table, two pasted tables, a notebook, a
    canvas, a Sandbox card and a relationship; returns the grids."""
    csv, database = made_up_files(tmp_path)
    orders = ok(client.post("/datasets/orders/load", json={"path": str(csv)}, headers=AUTH))["grid"]
    ok(client.post(f"/grids/{orders}/steps", json={"steps": STEPS}, headers=AUTH))
    ok(client.post("/connections", json=shop(database), headers=AUTH))
    vault = {
        "name": "Team vault",
        "kind": "vault",
        "code": f"def get(name):\n    return '{VAULT_SECRET}'",
        "variable": "get",
        "vault_mapping": [{"env": "WAREHOUSE_PASSWORD", "secret": "warehouse-pw"}],
    }
    ok(client.post("/blades", json=vault, headers=AUTH))
    customers = ok(client.post("/connections/Shop/open", json={"table": "customers"}, headers=AUTH))["grid"]
    kept = ok(
        client.post("/datasets/kept_paste/paste", content="city\tvisits\nOgdenville\t4\n", headers=AUTH)
    )
    ok(client.post("/datasets/lost_paste/paste", content="fruit\tcrates\nPear\t2\n", headers=AUTH))
    ok(
        client.post(
            "/cards",
            json={"kind": "note", "title": "Made-up note", "body": "North sells most."},
            headers=AUTH,
        )
    )
    model = {
        "name": "current",
        "relationships": [
            {"from": "orders", "from_columns": ["order_id"], "to": "customers", "to_columns": ["customer_id"]}
        ],
    }
    ok(client.post("/relationships", json={"model": model, "replace": True}, headers=AUTH))
    return {"orders": orders, "customers": customers, "kept": kept["grid"], "csv": csv}


def entries(path: Path) -> dict[str, bytes]:
    with zipfile.ZipFile(path) as read:
        return {name: read.read(name) for name in read.namelist()}


def test_a_project_saves_closes_and_opens_with_everything_back(tmp_path: Path) -> None:
    with make_client(tmp_path) as client:
        made = build_project(client, tmp_path)
        assert project(client)["loose"] is True  # open work, no project: what opening another would lose
        state = ok(client.post("/project/new", json={"name": "sales"}, headers=AUTH))
        folder = Path(state["project"]["folder"])
        assert folder.name == "sales" and (folder / "data.ipynb").is_file()
        assert state["project"]["dirty"] is True and state["project"]["path"] is None
        # A notebook and a canvas of the project's own, saved into its working folder as the Workbench does.
        cell = notebooks.Cell("code", "from data import orders\nprint(len(orders))")
        cell.outputs = [{"output_type": "stream", "name": "stdout", "text": "North 3 South 5"}]
        (folder / "analysis.ipynb").write_text(notebooks.write_notebook([cell]), encoding="utf-8")
        (folder / "sales.stapp.json").write_text(streamlit_cells.write_app([]), encoding="utf-8")
        (folder / "extra.csv").write_text("a\n1\n", encoding="utf-8")  # a data file: never in the .sab
        # The first save of a project made here needs where it goes.
        assert client.post("/project/save", json={}, headers=AUTH).status_code == 409
        target = tmp_path / "work" / "sales.sab"
        saved = ok(
            client.post(
                "/project/save", json={"path": str(target), "keep_rows": {"kept_paste": True}}, headers=AUTH
            )
        )
        assert saved["saved"] == str(target) and saved["rows"] == ["kept_paste"]
        assert saved["project"]["dirty"] is False and saved["project"]["name"] == "sales"
        inside = entries(target)
        assert {
            "project.json",
            "data.ipynb",
            "data.py",
            "analysis.ipynb",
            "sales.stapp.json",
            "model.tang",
            "sandbox/sandbox.json",
            "data/kept_paste.parquet",
        } <= set(inside)
        assert "extra.csv" not in inside and "data/lost_paste.parquet" not in inside
        assert b"North 3 South 5" not in inside["analysis.ipynb"]  # outputs show rows: never in the file
        manifest = json.loads(inside["project.json"])
        sources = {t["name"]: t["source"] for t in manifest["tables"]}
        assert sources["orders"] == {
            "kind": "file",
            "path": "orders.csv",
            "absolute": str(made["csv"]),
            "sheet": None,
        }
        assert sources["customers"]["kind"] == "connection" and sources["customers"]["connection"] == "Shop"
        assert sources["kept_paste"] == {"kind": "pasted", "rows": True}
        assert sources["lost_paste"] == {"kind": "pasted", "rows": False}
        orders_steps = next(t for t in manifest["tables"] if t["name"] == "orders")["grids"][0]["steps"]
        assert [s["kind"] for s in orders_steps] == ["filter", "sort"]
        assert [r["path"] for r in project(client)["recent"]] == [str(target)]

        # Close: everything goes, the working folder too.
        ok(client.post("/project/close", json={}, headers=AUTH))
        assert not folder.exists() and ok(client.get("/datasets", headers=AUTH))["datasets"] == []
        assert ok(client.get("/cards", headers=AUTH))["cards"] == []

        # Open: the tables read again (the steps applied), the Sandbox, the model, the files.
        opened = ok(client.post("/project/open", json={"path": str(target)}, headers=AUTH))["project"]
        assert opened["dirty"] is False and opened["path"] == str(target)
        names = {d["name"]: d for d in ok(client.get("/datasets", headers=AUTH))["datasets"]}
        assert set(names) == {"orders", "customers", "kept_paste"}
        assert [p["table"] for p in opened["problems"]] == ["lost_paste"]
        assert opened["problems"][0]["fix"]["kind"] == "remove"
        grids = {g["dataset"]: g["grid"] for g in ok(client.get("/grids", headers=AUTH))["grids"]}
        orders = ok(client.get(f"/grids/{grids['orders']}", headers=AUTH))
        assert [s["kind"] for s in orders["steps"]] == ["filter", "sort"]
        assert ok(client.get(f"/grids/{grids['orders']}/count", headers=AUTH))["row_count"] == 3
        assert ok(client.get(f"/grids/{grids['customers']}", headers=AUTH))["row_count"] == 2
        assert ok(client.get(f"/grids/{grids['kept_paste']}", headers=AUTH))["row_count"] == 1
        cards = ok(client.get("/cards", headers=AUTH))["cards"]
        assert [c["title"] for c in cards] == ["Made-up note"]
        relationships = ok(client.get("/relationships", headers=AUTH))
        assert len(relationships["relationships"]) == 1
        work = Path(opened["folder"])
        assert (work / "analysis.ipynb").is_file() and (work / "sales.stapp.json").is_file()
        assert work != folder and work.name == "sales"
        # Remove the table whose rows were not kept: it leaves the project.
        fixed = ok(client.post("/project/fix", json={"table": "lost_paste", "remove": True}, headers=AUTH))
        assert fixed["project"]["problems"] == []


def test_no_secret_token_or_password_is_ever_in_the_file(tmp_path: Path) -> None:
    with make_client(tmp_path) as client:
        build_project(client, tmp_path)
        # A password typed into a connection's form: kept in the keyring, never the file.
        typed = shop(tmp_path / "shop.sqlite") | {"name": "Typed", "secrets": {"password": TYPED_SECRET}}
        typed["code"] = typed["code"].replace(KEYRING_SECRET, TYPED_SECRET)
        ok(client.post("/connections", json=typed, headers=AUTH))
        ok(client.post("/connections/Typed/open", json={"table": "customers"}, headers=AUTH))
        target = tmp_path / "secret_check.sab"
        ok(
            client.post(
                "/project/save", json={"path": str(target), "keep_rows": {"kept_paste": True}}, headers=AUTH
            )
        )
        raw = target.read_bytes()
        everything = b"".join(entries(target).values())
        for value in (KEYRING_SECRET, VAULT_SECRET, TYPED_SECRET, TOKEN):
            assert value.encode() not in everything and value.encode() not in raw, value
        manifest = json.loads(entries(target)["project.json"])
        typed_source = next(
            t["source"] for t in manifest["tables"] if t["source"].get("connection") == "Typed"
        )
        assert set(typed_source) == {"kind", "connection", "database", "schema", "table", "whole"}


def test_a_missing_connection_or_file_gives_the_table_its_fix(tmp_path: Path) -> None:
    target = tmp_path / "work" / "moved.sab"
    with make_client(tmp_path / "first") as client:
        made = build_project(client, tmp_path)
        ok(client.post("/project/save", json={"path": str(target)}, headers=AUTH))
        assert project(client)["project"]["name"] == "moved"
    # Another computer: no Shop connection, and the CSV moved away.
    moved = made["csv"].with_name("orders_moved.csv")
    made["csv"].rename(moved)
    with make_client(tmp_path / "second") as client:
        opened = ok(client.post("/project/open", json={"path": str(target)}, headers=AUTH))["project"]
        problems = {p["table"]: p for p in opened["problems"]}
        assert problems["customers"]["state"] == "no_connection"
        assert problems["customers"]["fix"] == {
            "kind": "add_connection",
            "label": "Add connection Shop",
            "connection": "Shop",
        }
        assert problems["orders"]["fix"]["label"] == "Find orders.csv"
        # Find orders.csv: read from where it is now, with its steps.
        after = ok(client.post("/project/fix", json={"table": "orders", "path": str(moved)}, headers=AUTH))
        assert "orders" not in {p["table"] for p in after["project"]["problems"]}
        grids = {g["dataset"]: g["grid"] for g in ok(client.get("/grids", headers=AUTH))["grids"]}
        assert len(ok(client.get(f"/grids/{grids['orders']}", headers=AUTH))["steps"]) == 2
        # Add connection Shop, then Try again: it comes back.
        ok(client.post("/connections", json=shop(tmp_path / "shop.sqlite"), headers=AUTH))
        again = ok(client.post("/project/fix", json={"table": "customers"}, headers=AUTH))
        assert "customers" not in {p["table"] for p in again["project"]["problems"]}


def test_unsaved_changes_ask_first_and_only_then(tmp_path: Path) -> None:
    with make_client(tmp_path) as client:
        csv, _ = made_up_files(tmp_path)
        first = tmp_path / "first.sab"
        ok(client.post("/datasets/orders/load", json={"path": str(csv)}, headers=AUTH))
        ok(client.post("/project/save", json={"path": str(first)}, headers=AUTH))
        second = tmp_path / "second.sab"
        ok(client.post("/project/new", json={"name": "second"}, headers=AUTH))  # clean: asks nothing
        ok(client.post("/project/save", json={"path": str(second)}, headers=AUTH))
        ok(client.post("/project/open", json={"path": str(first)}, headers=AUTH))  # clean: asks nothing
        grid = ok(client.get("/grids", headers=AUTH))["grids"][0]["grid"]
        ok(client.post(f"/grids/{grid}/steps", json={"steps": STEPS[:1]}, headers=AUTH))
        assert project(client)["project"]["dirty"] is True
        refused = client.post("/project/open", json={"path": str(second)}, headers=AUTH)
        assert refused.status_code == 409 and "unsaved changes" in refused.text
        # Another program asked (a double-click): the page asks the user.
        asked = ok(client.post("/project/open", json={"path": str(second), "ask": True}, headers=AUTH))
        assert asked["asked"] == str(second) and project(client)["asked"] == str(second)
        ok(client.post("/project/open", json={"path": str(second), "discard": True}, headers=AUTH))
        assert project(client)["project"]["name"] == "second" and project(client)["asked"] is None


def test_unknown_fields_survive_a_save_and_a_newer_format_is_read_only(tmp_path: Path) -> None:
    with make_client(tmp_path) as client:
        csv, _ = made_up_files(tmp_path)
        target = tmp_path / "future.sab"
        ok(client.post("/datasets/orders/load", json={"path": str(csv)}, headers=AUTH))
        ok(client.post("/project/save", json={"path": str(target)}, headers=AUTH))
        inside = entries(target)
        manifest = json.loads(inside["project.json"])
        manifest["bookmarks"] = [{"page": "Sales"}]
        manifest["tables"][0]["colour"] = "teal"
        with zipfile.ZipFile(target, "w") as out:
            for name, body in inside.items():
                out.writestr(name, json.dumps(manifest) if name == "project.json" else body)
        ok(client.post("/project/open", json={"path": str(target)}, headers=AUTH))
        ok(client.post("/project/save", json={}, headers=AUTH))
        again = json.loads(entries(target)["project.json"])
        assert again["bookmarks"] == [{"page": "Sales"}] and again["tables"][0]["colour"] == "teal"
        # A newer format: opens, read-only, in plain words.
        again["format"] = 99
        again["app_version"] = "9.9"
        inside = entries(target)
        with zipfile.ZipFile(target, "w") as out:
            for name, body in inside.items():
                out.writestr(name, json.dumps(again) if name == "project.json" else body)
        opened = ok(client.post("/project/open", json={"path": str(target)}, headers=AUTH))["project"]
        assert "read-only" in opened["read_only"]
        refused = client.post("/project/save", json={}, headers=AUTH)
        assert refused.status_code == 403 and "9.9" in refused.text


def test_the_agents_save_asks_only_when_it_writes_rows(tmp_path: Path) -> None:
    with make_client(tmp_path) as client:
        csv, _ = made_up_files(tmp_path)
        ok(client.post("/datasets/orders/load", json={"path": str(csv)}, headers=AUTH))
        ok(client.post("/datasets/pasted/paste", content="a\tb\n1\t2\n", headers=AUTH))
        plain = tmp_path / "plain.sab"
        assert ok(client.post("/project/save", json={"path": str(plain)}, headers=AGENT))["rows"] == []
        assert ok(client.get("/agent/approvals", headers=AUTH))["pending"] == []
        answer: dict[str, Any] = {}

        def save() -> None:
            body = {"keep_rows": {"pasted": True}}
            answer["response"] = client.post("/project/save", json=body, headers=AGENT)

        waiting = threading.Thread(target=save)
        waiting.start()
        for _ in range(100):
            pending = ok(client.get("/agent/approvals", headers=AUTH))["pending"]
            if pending:
                break
            time.sleep(0.05)
        assert pending and "pasted" in pending[0]["detail"]
        ok(client.post(f"/agent/approvals/{pending[0]['id']}", json={"approve": False}, headers=AUTH))
        waiting.join(10)
        assert answer["response"].status_code == 403
        assert "data/pasted.parquet" not in entries(plain)


def test_a_folder_project_opens_and_saves_as_one_file(tmp_path: Path) -> None:
    with make_client(tmp_path) as client:
        csv, _ = made_up_files(tmp_path)
        ok(client.post("/datasets/orders/load", json={"path": str(csv)}, headers=AUTH))
        made = ok(
            client.post(
                "/projects", json={"folder": str(tmp_path), "name": "shop", "app": False}, headers=AUTH
            )
        )
        folder = Path(made["folder"])
        target = tmp_path / "shop.sab"
        saved = ok(
            client.post("/project/save", json={"folder": str(folder), "path": str(target)}, headers=AUTH)
        )
        assert saved["project"]["folder"] == str(folder) and saved["project"]["temporary"] is False
        assert "data.ipynb" in entries(target)
        ok(client.post("/project/close", json={}, headers=AUTH))
        assert folder.is_dir()  # a folder project's folder is the user's own: it stays
        listed = ok(client.post("/project/open", json={"path": str(folder)}, headers=AUTH))["project"]
        assert listed["folder"] == str(folder) and listed["path"] is None


def test_swissarmybench_open_a_sab_asks_the_running_app_and_shows_its_page(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import webbrowser

    from swissarmybench.server import __main__ as command

    target = tmp_path / "sales.sab"
    target.write_bytes(b"made up")
    sent: list[tuple[str, dict[str, Any]]] = []
    opened: list[str] = []

    def post(info: dict[str, Any], route: str, body: dict[str, Any]) -> dict[str, Any]:
        sent.append((route, body))
        return {"page": False}

    monkeypatch.setattr(command, "running_server", lambda path: {"port": 1, "token": "t"})
    monkeypatch.setattr(command, "post_json", post)
    monkeypatch.setattr(webbrowser, "open", opened.append)
    assert command.open_project(str(target), tmp_path / "server.json") == 0
    assert sent == [("/project/open", {"path": str(target.resolve()), "ask": True})]
    assert opened and opened[0].startswith("http://127.0.0.1:1/workspace#token=")
    # A home window open already: it shows the project itself.
    monkeypatch.setattr(command, "post_json", lambda info, route, body: {"page": True})
    assert command.open_project(str(target), tmp_path / "server.json") == 0 and len(opened) == 1
    assert command.open_project(str(tmp_path / "gone.sab"), tmp_path / "server.json") == 1
