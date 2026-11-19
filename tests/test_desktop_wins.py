"""The desktop app's browser keys and files (the owner, 2026-11-18: "Agreed"): Ctrl+Shift+T reopens the
last closed table (its steps kept), a file opened with the app (`swissarmybench open <file>`), a file that
changed on disk (Reload, steps kept). Made-up data only."""

from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path
from typing import Any

import pytest

from swissarmybench.domain.grids import ClosedTab, GridRegistry
from swissarmybench.domain.steps import Step, ViewSettings
from tests.conftest import AGENT, AUTH, PORT, make_client

ORDERS = "order_id,region,amount\n1,North,120.5\n2,South,80\n3,East,42.25\n"


NORTH = {"kind": "filter", "params": {"column": "region", "op": "eq", "value": "North"}}


def step() -> Step:
    return Step.from_json(NORTH, 0)


def agent_through(client: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    """The agent's commands (cli/commands.py) sent to this test's server, as the agent."""
    from swissarmybench.cli import api
    from swissarmybench.cli.api import CommandError

    def call(method: str, path: str, body: Any = None, **_: Any) -> Any:
        answer = client.request(method, path, json=body, headers=AGENT)
        if answer.status_code >= 400:
            raise CommandError(answer.text)
        return answer.json()

    monkeypatch.setattr(api, "call", call)


# ===== the rule: which closed tab comes back =====


def test_the_newest_closed_tab_that_can_come_back_comes_back() -> None:
    grids = GridRegistry(10)
    first = grids.create("orders", [step()], ViewSettings())
    second = grids.create("pasted")
    grids.remember_closed(first, serial=1, path="/data/orders.csv")
    grids.remember_closed(second, serial=2)
    # "pasted" is still open (serial 2): its tab comes back first.
    found = grids.take_closed(lambda name: {"orders": None, "pasted": 2}[name])
    assert found is not None and found.dataset == "pasted" and found.path is None
    # "orders" is closed, but its file can be read again: it comes back next, its steps with it.
    found = grids.take_closed(lambda name: None)
    assert found is not None and found.dataset == "orders" and found.path == "/data/orders.csv"
    assert [s.params["value"] for s in found.steps] == ["North"]
    assert grids.take_closed(lambda name: None) is None


def test_a_closed_tab_that_cannot_come_back_is_passed_over() -> None:
    grids = GridRegistry(10)
    for name, serial in (("orders", 1), ("pasted", 2)):
        grids.remember_closed(grids.create(name), serial=serial)
    # "pasted" was closed and had no file; "orders" is another table by now (another serial).
    assert grids.take_closed(lambda name: {"orders": 7, "pasted": None}[name]) is None
    # A name taken by another table is never replaced by reading the old file again.
    grids.remember_closed(grids.create("orders"), serial=1, path="/data/orders.csv")
    assert grids.take_closed(lambda name: 9) is None


def test_only_the_last_twenty_are_kept() -> None:
    grids = GridRegistry(100)
    for i in range(25):
        grids.remember_closed(grids.create(f"t{i}"), serial=i)
    kept: list[ClosedTab] = []
    while (tab := grids.take_closed(lambda name: int(name[1:]))) is not None:
        kept.append(tab)
    assert [t.dataset for t in kept] == [f"t{i}" for i in range(24, 4, -1)]


# ===== the door: POST /grids/reopen and the agent's tabs_reopen =====


def test_reopen_brings_back_a_closed_tab_and_a_closed_file_with_their_steps(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    csv = tmp_path / "orders.csv"
    csv.write_text(ORDERS, encoding="utf-8")
    with make_client(tmp_path) as client:
        loaded = client.post("/datasets/orders/load", headers=AUTH, json={"path": str(csv)}).json()
        grid = loaded["grid"]
        added = client.post(f"/grids/{grid}/steps", headers=AUTH, json={"steps": [NORTH]})
        assert added.status_code == 200, added.text
        assert client.post("/grids/reopen", headers=AUTH).status_code == 404  # nothing closed yet
        # The tab closed (the table stays open): it comes back with its step.
        assert client.delete(f"/grids/{grid}", headers=AUTH).status_code == 200
        back = client.post("/grids/reopen", headers=AUTH).json()
        assert back["dataset"] == "orders" and back["grid"] != grid
        steps: list[dict[str, Any]] = client.get(f"/grids/{back['grid']}", headers=AUTH).json()["steps"]
        assert [s["params"]["value"] for s in steps] == ["North"]
        # The table closed too: read again from its file, the step kept; the agent's command does it.
        assert client.delete("/datasets/orders", headers=AUTH).status_code == 200
        from swissarmybench.cli import commands

        agent_through(client, monkeypatch)
        again = json.loads(commands.execute("tabs_reopen", {}))
        assert again["dataset"] == "orders"
        steps = client.get(f"/grids/{again['grid']}", headers=AUTH).json()["steps"]
        assert [s["params"]["value"] for s in steps] == ["North"]
        rows = client.get(f"/grids/{again['grid']}/count", headers=AGENT).json()["row_count"]
        assert rows == 1


# ===== files that refresh themselves: Changed on disk, Reload (steps kept), Not now =====


def test_a_file_that_changed_on_disk_is_said_and_reloaded_with_its_steps(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    csv = tmp_path / "orders.csv"
    csv.write_text(ORDERS, encoding="utf-8")
    with make_client(tmp_path) as client:
        watch = client.app.state.ctx.file_watch  # type: ignore[attr-defined]

        def look() -> list[str]:
            said: list[str] = asyncio.run(watch.look())
            return said

        grid = client.post("/datasets/orders/load", headers=AUTH, json={"path": str(csv)}).json()["grid"]
        client.post(f"/grids/{grid}/steps", headers=AUTH, json={"steps": [NORTH]})
        client.post("/datasets/pasted/paste", headers=AUTH, content="a\tb\n1\t2\n")  # no file: not watched
        assert look() == []  # the first look stamps each file as it is
        assert look() == []
        with client.websocket_connect("/ws?catalog=1", headers=AUTH | {"Host": f"127.0.0.1:{PORT}"}) as page:
            csv.write_text(ORDERS + "4,North,310.75\n", encoding="utf-8")
            assert look() == ["orders"] and look() == []  # said once
            notice = page.receive_json()
            assert notice == {"type": "file_changed", "dataset": "orders", "changed": True}
        datasets = client.get("/datasets", headers=AUTH).json()["datasets"]
        assert {d["name"]: d["changed_on_disk"] for d in datasets} == {"orders": True, "pasted": False}
        # Never reloaded by itself: still the one North row of three.
        assert client.get(f"/grids/{grid}/count", headers=AUTH).json()["row_count"] == 1
        # Reload (the agent's tabs_reload): read again in place, the same grid, its step kept.
        agent_through(client, monkeypatch)
        from swissarmybench.cli import commands

        reloaded = json.loads(commands.execute("tabs_reload", {"dataset": "orders"}))
        assert reloaded["grid"] == grid and reloaded["reloaded"] == "orders"
        assert client.get(f"/grids/{grid}/count", headers=AUTH).json()["row_count"] == 2
        look()
        assert not watch.changed("orders")
        # Not now: kept as it is; said again only when the file changes again.
        csv.write_text(ORDERS + "5,West,1\n", encoding="utf-8")
        assert look() == ["orders"]
        said = client.post("/datasets/orders/reload", headers=AUTH, json={"not_now": True}).json()
        assert said == {"dataset": "orders", "changed": False}
        assert look() == [] and not watch.changed("orders")
        os.utime(csv, ns=(1, 2))
        assert look() == ["orders"]
        # A table not read from a file cannot be reloaded.
        assert client.post("/datasets/pasted/reload", headers=AUTH).status_code == 404


# ===== a file opened with the app: the rules, the channel, file_page, the command line, the installers =====


def test_what_opening_a_file_does() -> None:
    from swissarmybench.domain import desktop as rules

    assert rules.file_kind("orders.csv", False, False) == rules.TABLE
    assert rules.file_kind("Sales Q3.XLSX", False, False) == rules.TABLE
    assert rules.file_kind("events.parquet", False, False) == rules.TABLE
    assert rules.file_kind("data.ipynb", False, False) == rules.NOTEBOOK
    assert rules.file_kind("warehouse.blade.py", False, False) == rules.BLADE
    assert rules.file_kind("sales", True, True) == rules.PROJECT
    assert rules.file_kind("notes.docx", False, False) == "" and rules.file_kind("run.py", False, False) == ""
    # The table's name: the file's, made a dataset name; never an open table's (none is replaced).
    assert rules.table_name("orders.csv", []) == "orders"
    assert rules.table_name("Sales Q3 (final).xlsx", ["x"]) == "Sales_Q3_final"
    assert rules.table_name("orders.csv", ["orders", "Orders_2"]) == "orders_3"
    assert rules.table_name("....csv", []) == "data"
    assert rules.blade_stem("warehouse.blade.py") == "warehouse"


def test_the_channel_takes_a_files_full_path_only() -> None:
    from swissarmybench.domain import desktop as rules

    key = "k" * 43
    said = rules.read_message(rules.message(key, {"file": "/home/me/orders.csv"}), key)
    assert said == {"file": "/home/me/orders.csv"}
    windows = rules.read_message(rules.message(key, {"file": "C:\\Users\\me\\orders.csv"}), key)
    assert windows["file"].endswith(".csv")
    for bad in ("orders.csv", "", "/a\nb", 3, "/" + "x" * 5000):
        with pytest.raises(rules.ShellError):
            rules.read_message(rules.message(key, {"file": bad}), key)


def server_through(client: Any, monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    """server/desktop.py's GET and POST sent to this test's server (as the user)."""
    from swissarmybench.server import desktop as launch

    def answer(response: Any) -> Any:
        if response.status_code >= 400:
            raise OSError(response.text)
        return response.json()

    def get(info: Any, route: str, timeout: float = 30) -> Any:
        return answer(client.get(route, headers=AUTH))

    def post(info: Any, route: str, body: Any, timeout: float = 120) -> Any:
        return answer(client.post(route, headers=AUTH, json=body))

    monkeypatch.setattr(launch, "get_json", get)
    monkeypatch.setattr(launch, "post_json", post)
    return {"port": PORT, "token": "t"}


def test_a_file_opened_with_the_app_is_read_by_its_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from swissarmybench.domain import desktop as rules
    from swissarmybench.server import desktop as launch

    csv = tmp_path / "orders.csv"
    csv.write_text(ORDERS, encoding="utf-8")
    notebook = tmp_path / "analysis.ipynb"
    notebook.write_text('{"cells": [], "metadata": {}, "nbformat": 4, "nbformat_minor": 5}', encoding="utf-8")
    (tmp_path / "notes.docx").write_text("x", encoding="utf-8")
    with make_client(tmp_path) as client:
        info = server_through(client, monkeypatch)
        page = launch.file_page(str(csv), info)
        grid = page.split("#grid=")[1]
        # A table: read by its path, so its origin is the file (a project reads it again; the watch sees it).
        assert client.get(f"/grids/{grid}", headers=AUTH).json()["dataset"] == "orders"
        origins = client.app.state.ctx.datasets.origins  # type: ignore[attr-defined]
        assert origins.get("orders").path == str(csv.resolve())
        # The same file again: another table beside it, never the first replaced.
        assert "#grid=" in launch.file_page(str(csv), info)
        names = sorted(d["name"] for d in client.get("/datasets", headers=AUTH).json()["datasets"])
        assert names == ["orders", "orders_2"]
        # A notebook with no Workbench window open: a Workbench window that opens it (no token in the page).
        page = launch.file_page(str(notebook), info)
        assert page.startswith("/workbench?file=") and "analysis.ipynb" in page
        assert rules.page_of(page) == page
        with pytest.raises(rules.ShellError, match="opens CSV"):
            launch.file_page(str(tmp_path / "notes.docx"), info)
        with pytest.raises(rules.ShellError, match="is not there"):
            launch.file_page(str(tmp_path / "gone.csv"), info)


def test_swissarmybench_open_a_file_goes_to_the_running_app(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    import sys

    from swissarmybench.server import __main__ as command
    from swissarmybench.server import desktop as launch

    csv = tmp_path / "orders.csv"
    csv.write_text(ORDERS, encoding="utf-8")
    monkeypatch.setenv("SWISSARMYBENCH_INFO", str(tmp_path / "server.json"))
    handed: list[str] = []

    def hand(path: str, info: Any = None) -> bool:
        handed.append(path)
        return True

    monkeypatch.setattr(launch, "can_run", lambda: True)
    monkeypatch.setattr(launch, "hand_file", hand)

    def run(*argv: str) -> int:
        monkeypatch.setattr(sys, "argv", ["swissarmybench", *argv])
        try:
            command.main()
        except SystemExit as stopped:
            return int(stopped.code or 0)
        return 0

    assert run("open", str(csv)) == 0 and handed == [str(csv.resolve())]
    assert "Opening orders.csv" in capsys.readouterr().out
    (tmp_path / "notes.docx").write_text("x", encoding="utf-8")
    assert run("open", str(tmp_path / "notes.docx")) == 1 and "opens CSV" in capsys.readouterr().err
    # --browser (or no app here): the server reads it, the browser shows it.
    browsed: list[str] = []

    def browse(address: str) -> bool:
        browsed.append(address)
        return True

    monkeypatch.setattr(command, "running_server", lambda path: {"port": PORT, "token": "t"})
    monkeypatch.setattr(launch, "file_page", lambda path, info: "/workspace#grid=g1")
    monkeypatch.setattr("webbrowser.open", browse)
    assert run("open", str(csv), "--browser") == 0
    assert browsed == [f"http://127.0.0.1:{PORT}/workspace#token=t&grid=g1"]


def test_hand_file_starts_the_app_when_none_runs(monkeypatch: pytest.MonkeyPatch) -> None:
    from swissarmybench.server import desktop as launch

    said: list[Any] = []
    started: list[Any] = []
    answers = iter([None, {"ok": True}])

    def tell(message: Any, info: Any = None, wait: float = 0.0) -> Any:
        said.append((message, wait))
        return next(answers)

    monkeypatch.setattr(launch, "tell", tell)
    monkeypatch.setattr(launch, "lock_free", lambda info=None: True)
    monkeypatch.setattr(launch, "start_app", started.append)
    assert launch.hand_file("/home/me/orders.csv") is True
    assert started == [None] and [m for m, _ in said] == [{"file": "/home/me/orders.csv"}] * 2
    assert said[1][1] == launch.RECORD_WAIT_SECONDS


def test_the_installers_register_open_with_for_this_user_only() -> None:
    root = Path(__file__).resolve().parents[1]
    ps1 = (root / "installer" / "install.ps1").read_text(encoding="utf-8")
    assert '$Classes = "HKCU:\\Software\\Classes"' in ps1 and "HKLM" not in ps1
    assert '$OpenWithTypes = @(".csv", ".parquet", ".xlsx", ".ipynb", ".py")' in ps1
    assert "OpenWithProgids" in ps1 and '-m swissarmybench.server open `"%1`"' in ps1
    # Offered, never the default: no extension's own (default) value is written.
    assert 'New-Item -Path "$Classes\\$ext" -Value' not in ps1
    assert "try { UnregisterOpenWith } catch { }" in ps1  # -Uninstall takes it away
    sh = (root / "installer" / "install.sh").read_text(encoding="utf-8")
    for extension in ("csv", "parquet", "xlsx", "ipynb"):
        assert f"<string>{extension}</string>" in sh  # macOS: the bundle's document types
    assert "<string>Alternate</string>" in sh and "<string>blade.py</string>" in sh
