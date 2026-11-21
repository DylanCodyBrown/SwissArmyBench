"""A project is a folder (services/sab_projects.py; the owner, 2026-11-17): New scaffolds it (.sab/,
.gitignore, README.md), save writes .sab/ (an unchanged save changes no byte), close and open again with
everything back (a CSV table with two steps, a SQLite connection's table, a pasted table ticked and not,
a Visualizations card, the relationships); a folder made a project around its files (nothing written
over); Keep its rows into .sab/data/ (ignored by Git); Copy project to; no way left to import an old .sab
file (the owner, 2026-11-17); recent projects as folders; a missing connection or file says how to
fix it; no secret is ever written; the agent's save asks only when it keeps rows. Made-up data only."""

from __future__ import annotations

import json
import shutil
import sqlite3
import threading
import time
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from starlette.testclient import TestClient

from swissarmybench.domain import notebooks
from swissarmybench_streamlit.domain import canvas_model
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
        'assert secret("password")\n'
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
    canvas, a Visualizations card and a relationship; returns the grids."""
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


def state_files(folder: Path) -> dict[str, bytes]:
    """The project's .sab/ files, by their path in it."""
    app = folder / ".sab"
    return {p.relative_to(folder).as_posix(): p.read_bytes() for p in sorted(app.rglob("*")) if p.is_file()}


def manifest_of(folder: Path) -> dict[str, Any]:
    return dict(json.loads((folder / ".sab" / "project.json").read_text(encoding="utf-8")))


def test_a_project_folder_is_made_saved_closed_and_opened_with_everything_back(tmp_path: Path) -> None:
    with make_client(tmp_path) as client:
        made = build_project(client, tmp_path)
        assert project(client)["loose"] is True  # open work, no project: what opening another would lose
        refused = client.post(
            "/project/new", json={"path": str(tmp_path / "work" / "sales.sab")}, headers=AUTH
        )
        assert refused.status_code == 400 and "folder" in refused.text
        target = tmp_path / "work" / "sales"
        state = ok(client.post("/project/new", json={"path": str(target)}, headers=AUTH))
        folder = Path(state["project"]["folder"])
        assert folder == target and state["project"]["path"] == str(target)
        assert state["project"]["dirty"] is False and state["project"]["autosave"] is True
        # The scaffold: the data notebook and its export, Git's files, and the app's own .sab/.
        for name in (
            "data.ipynb",
            "data.py",
            ".gitignore",
            "README.md",
            ".sab/project.json",
            ".sab/.gitignore",
        ):
            assert (folder / name).is_file(), name
        assert (
            ".sab/data/" in (folder / ".gitignore").read_text()
            and "data/" in (folder / ".sab/.gitignore").read_text()
        )
        assert "remove" in (folder / "README.md").read_text().lower()
        # The project's own documents are files the Workbench saves; .sab/ holds the app's state.
        cell = notebooks.Cell("code", "from data import orders\nprint(len(orders))")
        (folder / "analysis.ipynb").write_text(notebooks.write_notebook([cell]), encoding="utf-8")
        (folder / "sales.canvas.json").write_text(
            canvas_model.write(canvas_model.new_canvas("sales")), encoding="utf-8"
        )
        saved = ok(client.post("/project/save", json={"keep_rows": {"kept_paste": True}}, headers=AUTH))
        assert saved["saved"] == str(target) and saved["rows"] == ["kept_paste"]
        assert saved["project"]["dirty"] is False and saved["project"]["name"] == "sales"
        inside = state_files(folder)
        assert {
            ".sab/project.json",
            ".sab/.gitignore",
            ".sab/model.json",
            ".sab/visualizations.json",
            ".sab/data/kept_paste.parquet",
        } <= set(inside)
        assert ".sab/data/lost_paste.parquet" not in inside
        manifest = manifest_of(folder)
        assert "saved" not in manifest and "name" not in manifest  # no timestamp; the name is the folder's
        sources = {t["name"]: t["source"] for t in manifest["tables"]}
        assert sources["orders"] == {
            "kind": "file",
            "path": str(made["csv"]),
            "absolute": str(made["csv"]),
            "sheet": None,
        }
        assert sources["customers"]["kind"] == "connection" and sources["customers"]["connection"] == "Shop"
        assert sources["kept_paste"] == {"kind": "pasted", "rows": True}
        assert sources["lost_paste"] == {"kind": "pasted", "rows": False}
        orders_steps = next(t for t in manifest["tables"] if t["name"] == "orders")["grids"][0]["steps"]
        assert [s["kind"] for s in orders_steps] == ["filter", "sort"]
        assert [r["path"] for r in project(client)["recent"]] == [str(target)]
        # A save that changes nothing changes no byte.
        before = {p: (folder / p).stat().st_mtime_ns for p in inside}
        again = ok(client.post("/project/save", json={}, headers=AUTH))
        assert again["written"] == [] and state_files(folder) == inside
        assert {p: (folder / p).stat().st_mtime_ns for p in inside} == before

        # Close: everything goes from the app; the folder is the user's and stays.
        ok(client.post("/project/close", json={}, headers=AUTH))
        assert folder.is_dir() and ok(client.get("/datasets", headers=AUTH))["datasets"] == []
        assert ok(client.get("/cards", headers=AUTH))["cards"] == []

        # Open: the tables read again (the steps applied), Visualizations, the model.
        opened = ok(client.post("/project/open", json={"path": str(target)}, headers=AUTH))["project"]
        assert opened["dirty"] is False and opened["folder"] == str(target)
        names = {d["name"]: d for d in ok(client.get("/datasets", headers=AUTH))["datasets"]}
        assert set(names) == {"orders", "customers", "kept_paste"}
        assert [p["table"] for p in opened["problems"]] == ["lost_paste"]
        grids = {g["dataset"]: g["grid"] for g in ok(client.get("/grids", headers=AUTH))["grids"]}
        orders = ok(client.get(f"/grids/{grids['orders']}", headers=AUTH))
        assert [s["kind"] for s in orders["steps"]] == ["filter", "sort"]
        assert ok(client.get(f"/grids/{grids['orders']}/count", headers=AUTH))["row_count"] == 3
        assert ok(client.get(f"/grids/{grids['customers']}", headers=AUTH))["row_count"] == 2
        assert ok(client.get(f"/grids/{grids['kept_paste']}", headers=AUTH))["row_count"] == 1
        assert [c["title"] for c in ok(client.get("/cards", headers=AUTH))["cards"]] == ["Made-up note"]
        assert len(ok(client.get("/relationships", headers=AUTH))["relationships"]) == 1
        # Remove the table whose rows were not kept; untick the kept one: its rows leave .sab/data.
        ok(client.post("/project/fix", json={"table": "lost_paste", "remove": True}, headers=AUTH))
        ok(client.post("/project/save", json={"keep_rows": {"kept_paste": False}}, headers=AUTH))
        assert not (folder / ".sab" / "data" / "kept_paste.parquet").exists()


def test_autosave_keeps_sab_current_once_a_change_settles(tmp_path: Path) -> None:
    with make_client(tmp_path, autosave_seconds=0.05) as client:
        csv, _ = made_up_files(tmp_path)
        target = tmp_path / "auto"
        ok(client.post("/project/new", json={"path": str(target)}, headers=AUTH))
        before = (target / ".sab" / "project.json").read_bytes()
        ok(client.post("/datasets/orders/load", json={"path": str(csv)}, headers=AUTH))
        for _ in range(100):
            if (target / ".sab" / "project.json").read_bytes() != before:
                break
            time.sleep(0.05)
        assert [t["name"] for t in manifest_of(target)["tables"]] == ["orders"]
        assert project(client)["project"]["dirty"] is False
        # Off: kept in .sab/project.json at once, and nothing more is written by itself.
        ok(client.post("/project/autosave", json={"on": False}, headers=AUTH))
        assert manifest_of(target)["autosave"] is False
        grid = ok(client.get("/grids", headers=AUTH))["grids"][0]["grid"]
        ok(client.post(f"/grids/{grid}/steps", json={"steps": STEPS[:1]}, headers=AUTH))
        time.sleep(0.4)
        assert manifest_of(target)["tables"][0]["grids"][0]["steps"] == []


def test_new_project_goes_into_the_projects_folder_by_name(tmp_path: Path) -> None:
    with make_client(tmp_path) as client:
        made = ok(client.post("/project/new", json={"name": "Quarterly"}, headers=AUTH))
        folder = tmp_path / "home" / "Swiss Army Bench Projects" / "Quarterly"
        assert made["project"]["folder"] == str(folder) and (folder / "data.ipynb").is_file()
        # A folder that holds something is not a new project's.
        taken = client.post("/project/new", json={"path": str(folder), "discard": True}, headers=AUTH)
        assert taken.status_code == 409 and "not empty" in taken.text


def test_a_folder_is_made_a_project_around_its_files_writing_nothing_over(tmp_path: Path) -> None:
    folder = tmp_path / "existing"
    folder.mkdir()
    (folder / "notes.md").write_text("# Made-up notes\n", encoding="utf-8")
    (folder / ".gitignore").write_text("secret.txt\n", encoding="utf-8")
    (folder / "README.md").write_text("Mine.\n", encoding="utf-8")
    with make_client(tmp_path) as client:
        asked = ok(client.post("/project/open", json={"path": str(folder)}, headers=AUTH))
        assert asked["not_a_project"] == str(folder) and asked["project"] is None
        made = ok(client.post("/project/open", json={"path": str(folder), "make": True}, headers=AUTH))
        assert made["project"]["folder"] == str(folder)
        assert set(made["made"]) == {"data.ipynb", ".sab/.gitignore", ".sab/project.json"}
        assert (folder / ".gitignore").read_text() == "secret.txt\n" and (
            folder / "README.md"
        ).read_text() == "Mine.\n"
        assert (folder / "notes.md").read_text() == "# Made-up notes\n"
        # A folder with the scaffold but no .sab/ yet (made before this version) opens as a project.
        older = tmp_path / "older"
        older.mkdir()
        (older / "data.ipynb").write_text(notebooks.write_notebook([]), encoding="utf-8")
        opened = ok(client.post("/project/open", json={"path": str(older)}, headers=AUTH))
        assert opened["project"]["folder"] == str(older)


def test_copy_project_to_another_folder_rows_only_on_a_tick(tmp_path: Path) -> None:
    with make_client(tmp_path) as client:
        ok(client.post("/datasets/pasted/paste", content="a\tb\n1\t2\n", headers=AUTH))
        source = tmp_path / "first"
        ok(client.post("/project/new", json={"path": str(source)}, headers=AUTH))
        ok(client.post("/project/save", json={"keep_rows": {"pasted": True}}, headers=AUTH))
        (source / "__pycache__").mkdir()
        (source / "__pycache__" / "x.pyc").write_bytes(b"made up")
        plain = ok(client.post("/project/copy", json={"path": str(tmp_path / "plain")}, headers=AUTH))
        assert plain["copied"] == str(tmp_path / "plain")
        assert (tmp_path / "plain" / ".sab" / "project.json").is_file()
        assert (
            not (tmp_path / "plain" / ".sab" / "data").exists()
            and not (tmp_path / "plain" / "__pycache__").exists()
        )
        ok(client.post("/project/copy", json={"path": str(tmp_path / "whole"), "data": True}, headers=AUTH))
        assert (tmp_path / "whole" / ".sab" / "data" / "pasted.parquet").is_file()
        again = client.post("/project/copy", json={"path": str(tmp_path / "whole")}, headers=AUTH)
        assert again.status_code == 409
        recent = [r["path"] for r in project(client)["recent"]]
        assert str(tmp_path / "whole") in recent and str(source) in recent


def test_no_secret_token_or_password_is_ever_written(tmp_path: Path) -> None:
    with make_client(tmp_path) as client:
        build_project(client, tmp_path)
        typed = shop(tmp_path / "shop.sqlite") | {"name": "Typed", "secrets": {"password": TYPED_SECRET}}
        typed["code"] = typed["code"].replace(KEYRING_SECRET, TYPED_SECRET)
        ok(client.post("/connections", json=typed, headers=AUTH))
        ok(client.post("/connections/Typed/open", json={"table": "customers"}, headers=AUTH))
        target = tmp_path / "secret_check"
        ok(
            client.post(
                "/project/save", json={"path": str(target), "keep_rows": {"kept_paste": True}}, headers=AUTH
            )
        )
        everything = b"".join(p.read_bytes() for p in target.rglob("*") if p.is_file())
        for value in (KEYRING_SECRET, VAULT_SECRET, TYPED_SECRET, TOKEN):
            assert value.encode() not in everything, value
        typed_source = next(
            t["source"] for t in manifest_of(target)["tables"] if t["source"].get("connection") == "Typed"
        )
        assert set(typed_source) == {"kind", "connection", "database", "schema", "table", "whole"}


def test_a_missing_connection_or_file_gives_the_table_its_fix(tmp_path: Path) -> None:
    target = tmp_path / "work" / "moved"
    with make_client(tmp_path / "first") as client:
        made = build_project(client, tmp_path)
        ok(client.post("/project/save", json={"path": str(target)}, headers=AUTH))
        assert project(client)["project"]["name"] == "moved"
    moved = made["csv"].with_name("orders_moved.csv")
    made["csv"].rename(moved)
    shutil.copytree(tmp_path / "first" / "state" / "library", tmp_path / "second" / "state" / "library")
    with memory_keyring(), make_client(tmp_path / "second") as client:
        opened = ok(client.post("/project/open", json={"path": str(target)}, headers=AUTH))["project"]
        problems = {p["table"]: p for p in opened["problems"]}
        assert problems["customers"]["state"] == "needs_password"
        assert problems["customers"]["fix"] == {
            "kind": "password",
            "label": "Set the password",
            "connection": "Shop",
        }
        assert problems["orders"]["fix"]["label"] == "Find orders.csv"
        after = ok(client.post("/project/fix", json={"table": "orders", "path": str(moved)}, headers=AUTH))
        assert "orders" not in {p["table"] for p in after["project"]["problems"]}
        grids = {g["dataset"]: g["grid"] for g in ok(client.get("/grids", headers=AUTH))["grids"]}
        assert len(ok(client.get(f"/grids/{grids['orders']}", headers=AUTH))["steps"]) == 2
        ok(client.put("/blades/Shop/secrets", json={"password": KEYRING_SECRET}, headers=AUTH))
        again = ok(client.post("/project/fix", json={"table": "customers"}, headers=AUTH))
        assert "customers" not in {p["table"] for p in again["project"]["problems"]}


def test_a_project_without_its_connection_offers_to_add_it(tmp_path: Path) -> None:
    target = tmp_path / "work" / "bare"
    with make_client(tmp_path / "first") as client:
        build_project(client, tmp_path)
        ok(client.post("/project/save", json={"path": str(target)}, headers=AUTH))
    with make_client(tmp_path / "second") as client:
        opened = ok(client.post("/project/open", json={"path": str(target)}, headers=AUTH))["project"]
        problems = {p["table"]: p for p in opened["problems"]}
        assert problems["customers"]["fix"] == {
            "kind": "add_connection",
            "label": "Add connection Shop",
            "connection": "Shop",
        }
        ok(client.post("/connections", json=shop(tmp_path / "shop.sqlite"), headers=AUTH))
        again = ok(client.post("/project/fix", json={"table": "customers"}, headers=AUTH))
        assert "customers" not in {p["table"] for p in again["project"]["problems"]}


def test_unsaved_changes_ask_first_and_only_then(tmp_path: Path) -> None:
    with make_client(tmp_path) as client:
        csv, _ = made_up_files(tmp_path)
        first = tmp_path / "first"
        ok(client.post("/datasets/orders/load", json={"path": str(csv)}, headers=AUTH))
        ok(client.post("/project/save", json={"path": str(first), "autosave": False}, headers=AUTH))
        second = tmp_path / "second"
        ok(client.post("/project/new", json={"path": str(second)}, headers=AUTH))  # clean: asks nothing
        ok(client.post("/project/open", json={"path": str(first)}, headers=AUTH))  # clean: asks nothing
        grid = ok(client.get("/grids", headers=AUTH))["grids"][0]["grid"]
        ok(client.post(f"/grids/{grid}/steps", json={"steps": STEPS[:1]}, headers=AUTH))
        assert project(client)["project"]["dirty"] is True
        refused = client.post("/project/open", json={"path": str(second)}, headers=AUTH)
        assert refused.status_code == 409 and "unsaved changes" in refused.text
        asked = ok(client.post("/project/open", json={"path": str(second), "ask": True}, headers=AUTH))
        assert asked["asked"] == str(second) and project(client)["asked"] == str(second)
        ok(client.post("/project/open", json={"path": str(second), "discard": True}, headers=AUTH))
        assert project(client)["project"]["name"] == "second" and project(client)["asked"] is None


def test_unknown_fields_survive_a_save_and_a_newer_format_is_read_only(tmp_path: Path) -> None:
    with make_client(tmp_path) as client:
        csv, _ = made_up_files(tmp_path)
        target = tmp_path / "future"
        ok(client.post("/datasets/orders/load", json={"path": str(csv)}, headers=AUTH))
        ok(client.post("/project/save", json={"path": str(target)}, headers=AUTH))
        manifest = manifest_of(target)
        manifest["bookmarks"] = [{"page": "Sales"}]
        manifest["tables"][0]["colour"] = "teal"
        (target / ".sab" / "project.json").write_text(json.dumps(manifest), encoding="utf-8")
        ok(client.post("/project/open", json={"path": str(target), "discard": True}, headers=AUTH))
        ok(client.post("/project/save", json={}, headers=AUTH))
        again = manifest_of(target)
        assert again["bookmarks"] == [{"page": "Sales"}] and again["tables"][0]["colour"] == "teal"
        again["format"] = 99
        again["app_version"] = "9.9"
        (target / ".sab" / "project.json").write_text(json.dumps(again), encoding="utf-8")
        opened = ok(client.post("/project/open", json={"path": str(target), "discard": True}, headers=AUTH))
        assert "read-only" in opened["project"]["read_only"]
        refused = client.post("/project/save", json={}, headers=AUTH)
        assert refused.status_code == 403 and "9.9" in refused.text


def test_the_agents_save_asks_only_when_it_keeps_rows(tmp_path: Path) -> None:
    with make_client(tmp_path) as client:
        csv, _ = made_up_files(tmp_path)
        ok(client.post("/datasets/orders/load", json={"path": str(csv)}, headers=AUTH))
        ok(client.post("/datasets/pasted/paste", content="a\tb\n1\t2\n", headers=AUTH))
        plain = tmp_path / "plain"
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
        assert not (plain / ".sab" / "data").exists()


def test_swissarmybench_open_a_folder_asks_the_running_app_and_shows_its_page(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import webbrowser

    from swissarmybench.server import __main__ as command

    target = tmp_path / "sales"
    target.mkdir()
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
    assert command.open_project(str(tmp_path / "gone"), tmp_path / "server.json") == 1


def test_swissarmybench_open_an_old_sab_file_says_one_line_and_starts_nothing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """The .sab conversion is removed (the owner, 2026-11-17): `swissarmybench open x.sab` answers in one
    plain line, there or not, and neither starts the app nor asks it anything."""
    from swissarmybench.server import __main__ as command

    old = tmp_path / "legacy.sab"
    old.write_bytes(b"PK made up")
    called: list[str] = []

    def note(what: str) -> Any:
        def noted(*args: Any, **kwargs: Any) -> Any:
            called.append(what)
            return None

        return noted

    for name in ("running_server", "start_in_background", "post_json"):
        monkeypatch.setattr(command, name, note(name))
    for target in (old, tmp_path / "gone.SAB"):
        assert command.open_project(str(target), tmp_path / "server.json") == 1
        said = capsys.readouterr()
        lines = (said.out + said.err).strip().splitlines()
        assert lines == [f"{target.name}: this version opens project folders only."]
    assert called == []


def test_no_route_or_command_imports_an_old_sab_file(tmp_path: Path) -> None:
    """Neither the server's routes nor the agent's commands offer an old .sab's import any more."""
    from swissarmybench.cli.commands import REGISTRY

    with make_client(tmp_path) as client:
        paths = [str(getattr(r, "path", "")) for r in client.app.routes]  # type: ignore[attr-defined]
        assert "/project/open" in paths
        assert not [p for p in paths if "sab" in p.lower()]
        gone = client.post("/project/import-sab", json={"path": str(tmp_path / "x.sab")}, headers=AUTH)
        assert gone.status_code in (404, 405)
        old = tmp_path / "legacy.sab"
        old.write_bytes(b"PK made up")
        answer = client.post("/project/open", json={"path": str(old)}, headers=AUTH)
        assert answer.status_code == 400 and "folder" in answer.text and not (tmp_path / "legacy").exists()
    for name, spec in REGISTRY.items():
        said = f"{name} {spec}".lower()
        assert "import_sab" not in said and "import-sab" not in said and "a .sab" not in said, name
