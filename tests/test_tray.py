"""The tray: its menu as data (what items, in what order, with an update or without), pystray's menu built
from it (its dummy backend: no desktop here), each item's action against a stand-in server, the icon and
its dot, Start with Windows' shortcut, where a tray can show, and one tray at a time."""

from __future__ import annotations

import importlib
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

from swissarmybench.domain.updates import MENU_MAX_ITEMS, TrayState, tooltip, tray_menu
from swissarmybench.server import tray as tray_module
from swissarmybench.server.tray import Tray, Watchdog, state_from, tray_available


def lines(state: TrayState) -> list[str]:
    return ["—" if item.separator else item.text for item in tray_menu(state)]


def test_the_menu_without_an_update() -> None:
    state = TrayState(
        running=True, tables=(("g1", "orders"), ("g2", "customers")), documents=(("0", "sales.ipynb", False),)
    )
    assert lines(state) == [
        "Open",
        "—",
        "orders",
        "customers",
        "—",
        "sales.ipynb",
        "—",
        "Open the Workbench",
        "Open the blades page",
        "—",
        "Restart",
        "Stop and quit",
    ]
    assert [i.id for i in tray_menu(state) if not i.separator][:4] == [
        "open",
        "table:g1",
        "table:g2",
        "document:0",
    ]
    assert [i for i in tray_menu(state) if i.default] == [tray_menu(state)[0]]  # the left click: Open
    assert tooltip(state) == "Swiss Army Bench"


def test_an_update_comes_first_with_whats_new() -> None:
    state = TrayState(running=True, update="0.0.2", startup=False)
    assert lines(state) == [
        "Update to 0.0.2",
        "What's new",
        "—",
        "Open",
        "—",
        "Open the Workbench",
        "Open the blades page",
        "—",
        "Restart",
        "Start with Windows",
        "Stop and quit",
    ]
    assert tooltip(state) == "Update available: 0.0.2"
    startup = next(i for i in tray_menu(state) if i.id == "startup")
    assert startup.checked is False
    assert next(i for i in tray_menu(TrayState(running=True, startup=True)) if i.id == "startup").checked


def test_with_the_server_stopped_the_menu_offers_start() -> None:
    state = TrayState(running=False, update="0.0.2")
    assert lines(state) == ["Start", "—", "Quit"]
    assert tooltip(state) == "Swiss Army Bench: stopped"


def test_a_long_list_ends_in_one_more_item_and_unsaved_documents_are_marked() -> None:
    tables = tuple((f"g{i}", f"t{i}") for i in range(MENU_MAX_ITEMS + 3))
    state = TrayState(running=True, tables=tables, documents=(("1", "load.py", True),))
    shown = lines(state)
    assert "t0" in shown and f"t{MENU_MAX_ITEMS}" not in shown and "3 more…" in shown
    assert "load.py •" in shown


def test_the_menus_state_comes_from_the_servers_answer() -> None:
    answer = {
        "available": True,
        "version": "0.0.2",
        "tables": [{"grid": "g1", "name": "orders"}, {"name": "no grid"}],
        "documents": [{"key": 0, "title": "sales.ipynb", "unsaved": True}],
        "failed": {"version": "0.0.2", "reason": "uv could not reach PyPI."},
    }
    state = state_from(answer, None)
    assert state.running and state.update == "0.0.2" and state.tables == (("g1", "orders"),)
    assert state.documents == (("0", "sales.ipynb", True),)
    assert state.failed == "Update to 0.0.2 failed: uv could not reach PyPI."
    assert state_from(None, True) == TrayState(running=False, startup=True)
    assert state_from(None, False, "Open at login", gave_up=True).gave_up


@pytest.fixture
def pystray(monkeypatch: pytest.MonkeyPatch) -> Any:
    pytest.importorskip("PIL")
    monkeypatch.setenv("PYSTRAY_BACKEND", "dummy")  # no desktop in a test
    for name in [m for m in sys.modules if m == "pystray" or m.startswith("pystray.")]:
        monkeypatch.delitem(sys.modules, name)
    try:
        return importlib.import_module("pystray")
    except ImportError:
        pytest.skip("pystray is not installed")


class StandInServer:
    """The server as the tray sees it: what it answers, and what the tray sent."""

    def __init__(self, answer: dict[str, Any] | None = None, install: list[Any] | None = None) -> None:
        self.answer = answer
        self.installs = list(install or [])
        self.sent: list[tuple[str, str, Any]] = []
        self.up = answer is not None

    def call(self, method: str, path: str, body: Any = None, timeout: float = 5.0) -> Any:
        self.sent.append((method, path, body))
        if not self.up:
            raise ConnectionError("not running")
        if path == "/updates/tray":
            return self.answer
        if path == "/updates":
            return {"url": "https://github.com/DylanCodyBrown/SwissArmyBench/releases/tag/v0.0.2"}
        if path == "/updates/install":
            return self.installs.pop(0)
        if path == "/shutdown":
            self.up = False
        return {}

    def running(self) -> bool:
        return self.up

    def page(self, path: str = "/workspace", extra: str = "") -> str:
        return f"http://127.0.0.1:8790{path}#token=t{extra}"

    dead: int | None = None  # the process id of a server that died (its connection file left behind)

    def died(self) -> int | None:
        return self.dead

    def info(self) -> dict[str, Any] | None:
        return {"pid": self.dead} if self.dead else ({"pid": 1} if self.up else None)


class FakeAutostart:
    label = "Start with Windows"

    def __init__(self, on: bool = True) -> None:
        self.on = on

    def status(self) -> bool:
        return self.on

    def set(self, on: bool) -> bool:
        self.on = on
        return on


def make_tray(server: StandInServer, **kwargs: Any) -> tuple[Tray, list[str], list[str]]:
    opened: list[str] = []
    started: list[str] = []
    tray = Tray(
        server,  # type: ignore[arg-type]
        kwargs.pop("autostart", None) or FakeAutostart(),  # type: ignore[arg-type]
        open_url=opened.append,
        start_server=lambda: started.append("start"),
        **kwargs,
    )
    tray.refresh()
    return tray, opened, started


def test_pystrays_menu_is_built_from_the_model_and_runs_each_items_action(pystray: Any) -> None:
    server = StandInServer(
        {"available": True, "version": "0.0.2", "tables": [{"grid": "g1", "name": "orders"}]}
    )
    tray, opened, _ = make_tray(server)
    menu = tray_module.menu_items(tray, pystray)
    built = list(menu.items)
    texts = [str(item) if item is not pystray.Menu.SEPARATOR else "—" for item in built]
    assert texts == lines(tray.state)
    assert [item.default for item in built if item is not pystray.Menu.SEPARATOR].count(True) == 1
    icon = pystray.Icon("swissarmybench", tray_module.draw_icon(16), "t", menu)
    orders = next(item for item in built if str(item) == "orders")
    orders(icon)
    assert opened == ["http://127.0.0.1:8790/workspace#token=t&grid=g1"]
    # Read fresh: the menu is a function of the tray's state, evaluated as it is drawn.
    server.answer = {"available": False, "tables": []}
    tray.refresh()
    assert "orders" not in [str(item) for item in menu.items]


def test_each_item_does_its_one_thing() -> None:
    server = StandInServer(
        {"available": True, "version": "0.0.2", "documents": [{"key": 2, "title": "a.ipynb"}]},
        install=[{"updating": "0.0.2"}],
    )
    tray, opened, started = make_tray(server)
    stopped: list[bool] = []
    tray.stop_tray = lambda: stopped.append(True)
    for item in ("open", "workbench", "blades", "whats_new"):
        tray.act(item)
    assert opened == [
        "http://127.0.0.1:8790/workspace#token=t",
        "http://127.0.0.1:8790/workbench#token=t",
        "http://127.0.0.1:8790/catalog#token=t",
        "https://github.com/DylanCodyBrown/SwissArmyBench/releases/tag/v0.0.2",
    ]
    tray.act("document:2")
    assert server.sent[-1] == ("POST", "/workbench/window", {"command": "doc.show", "args": {"index": 2}})
    tray.act("update")
    assert ("POST", "/updates/install", {"version": "0.0.2"}) in server.sent and stopped == [True]
    tray.act("restart")
    assert ("POST", "/shutdown", None) in server.sent and started == ["start"]
    tray.act("quit")
    assert stopped == [True, True]


def test_update_asks_in_the_systems_box_only_when_the_server_says_so() -> None:
    confirm = {"confirm": {"unsaved": ["sales.ipynb"], "kernels": 0}, "version": "0.0.2"}
    asked: list[tuple[str, str]] = []

    def no(title: str, text: str) -> bool:
        asked.append((title, text))
        return False

    server = StandInServer({"available": True, "version": "0.0.2"}, install=[confirm])
    tray, _, _ = make_tray(server, confirm=no)
    tray.act("update")
    assert asked[0][0] == "Update to 0.0.2" and "sales.ipynb" in asked[0][1]
    assert [s for s in server.sent if s[1] == "/updates/install"] == [
        ("POST", "/updates/install", {"version": "0.0.2"})
    ]

    server = StandInServer({"available": True, "version": "0.0.2"}, install=[confirm, {"updating": "0.0.2"}])
    tray, _, _ = make_tray(server, confirm=lambda title, text: True)
    stopped: list[bool] = []
    tray.stop_tray = lambda: stopped.append(True)
    tray.act("update")
    assert (
        server.sent[-1] == ("POST", "/updates/install", {"version": "0.0.2", "confirmed": True}) and stopped
    )


def test_the_tray_ends_itself_while_the_app_updates_and_says_a_failure_once() -> None:
    said: list[str] = []
    server = StandInServer({"available": False, "failed": {"version": "0.0.2", "reason": "no network"}})
    tray, _, _ = make_tray(server)
    tray.said = said.append
    tray.refresh()
    tray.refresh()
    assert said == ["Update to 0.0.2 failed: no network"]
    stopped: list[bool] = []
    tray.stop_tray = lambda: stopped.append(True)
    server.answer = {"available": False, "updating": "0.0.2"}
    tray.refresh()
    assert stopped == [True]


def test_with_the_server_stopped_start_starts_it() -> None:
    server = StandInServer(None)
    tray, _, started = make_tray(server)
    assert not tray.state.running
    tray.act("start")
    assert started == ["start"]


def test_the_icon_is_the_mark_and_an_update_adds_a_blue_dot() -> None:
    pytest.importorskip("PIL")
    plain, dotted = tray_module.draw_icon(64), tray_module.draw_icon(64, dot=True)
    assert plain.size == (64, 64) and plain.getpixel((32, 32)) == (255, 255, 255, 255)  # the cross
    assert plain.getpixel((12, 50)) == tray_module.MARK_RED
    corner = (64 - 15, 15)
    assert plain.getpixel(corner) == tray_module.MARK_RED and dotted.getpixel(corner) == tray_module.DOT_BLUE


def test_the_start_at_sign_in_item_switches_it() -> None:
    autostart = FakeAutostart(on=True)
    tray, _, _ = make_tray(StandInServer({"available": False}), autostart=autostart)
    item = next(i for i in tray.menu() if i.id == "startup")
    assert item.text == "Start with Windows" and item.checked is True
    tray.act("startup")
    assert autostart.on is False
    tray.refresh()
    assert next(i for i in tray.menu() if i.id == "startup").checked is False


def test_the_watchdog_restarts_at_most_three_times_in_five_minutes() -> None:
    clock = [0.0]
    dog = Watchdog(clock=lambda: clock[0])
    assert [dog.may_restart() for _ in range(3)] == [True, True, True]
    clock[0] = 100.0
    assert dog.may_restart() is False and dog.gave_up
    dog.reset()
    assert dog.may_restart() is True
    # Restarts more than five minutes apart never add up to giving up.
    spaced = Watchdog(clock=lambda: clock[0])
    for minute in range(10):
        clock[0] = 1000.0 + minute * 120.0
        assert spaced.may_restart() is True


def test_a_server_that_dies_is_started_again_then_the_tray_gives_up_and_says_so(tmp_path: Path) -> None:
    """A stand-in server whose process dies again and again: three restarts, then the menu's
    "Swiss Army Bench stopped: Restart", and the events noted for the beta log."""
    events = tmp_path / "server_events.json"
    server = StandInServer(None)
    tray, _, started = make_tray(server, events_file=events)
    for pid in (101, 102, 103, 104):
        server.dead = pid
        tray.refresh()
        tray.refresh()  # the same dead server seen twice is counted once
    assert started == ["start", "start", "start"]
    assert lines(tray.state)[0] == "Swiss Army Bench stopped: Restart"
    noted = [e["event"] for e in json.loads(events.read_text())]
    assert noted == ["crash", "restart"] * 3 + ["crash", "failed"]
    tray.act("start")  # the user's Restart counts afresh
    assert started == ["start"] * 4 and not tray.watchdog.gave_up


def test_a_server_stopped_on_purpose_is_left_stopped() -> None:
    server = StandInServer(None)  # no connection file: stopped by Stop and quit or `swissarmybench stop`
    tray, _, started = make_tray(server)
    tray.refresh()
    assert started == [] and lines(tray.state)[0] == "Start"


def test_at_sign_in_the_tray_starts_the_server_when_none_runs() -> None:
    server = StandInServer(None)
    tray, _, started = make_tray(server)
    tray.ensure_server()
    assert started == ["start"]
    running = StandInServer({"available": False})
    tray, _, started = make_tray(running)
    tray.ensure_server()
    assert started == []


def test_the_tray_and_background_start_the_server_detached_with_no_browser() -> None:
    assert tray_module.server_command()[-4:] == [
        "swissarmybench.server",
        "start",
        "--no-browser",
        "--no-tray",
    ]
    assert tray_module.server_command(8790, browser=True, tray=True)[-3:] == ["start", "--port", "8790"]
    assert tray_module.console_python("C:/nowhere/pythonw.exe") == "C:/nowhere/pythonw.exe"  # none beside it


def test_a_tray_shows_on_windows_and_macos_and_on_a_linux_desktop(monkeypatch: pytest.MonkeyPatch) -> None:
    pytest.importorskip("PIL")
    pytest.importorskip("pystray._base")
    assert tray_available("win32", {}) and tray_available("darwin", {})
    assert tray_available("linux", {"DISPLAY": ":0"}) and tray_available("linux", {"WAYLAND_DISPLAY": "w"})
    assert not tray_available("linux", {})


def test_start_says_nothing_where_no_tray_can_show(monkeypatch: pytest.MonkeyPatch) -> None:
    spawned: list[list[str]] = []
    monkeypatch.setattr(tray_module, "tray_available", lambda: False)
    monkeypatch.setattr(tray_module, "detached", lambda command: spawned.append(command))
    assert tray_module.start_tray() is False and spawned == []
    monkeypatch.setattr(tray_module, "tray_available", lambda: True)
    assert tray_module.start_tray() is True
    assert spawned == [[sys.executable, "-m", "swissarmybench.server", "tray"]]


def test_one_tray_at_a_time(tmp_path: Path) -> None:
    """A second `swissarmybench tray` ends at once (0) while the first holds the tray's lock."""
    from swissarmybench.server.lifecycle import InstanceLock

    info = tmp_path / "server.json"
    held = InstanceLock(info.with_name("tray.json"))
    try:
        env = os.environ | {"SWISSARMYBENCH_INFO": str(info), "PYSTRAY_BACKEND": "dummy"}
        done = subprocess.run(
            [sys.executable, "-m", "swissarmybench.server", "tray"],
            capture_output=True,
            text=True,
            timeout=60,
            env=env,
            check=False,
        )
        assert done.returncode == 0 and not (tmp_path / "tray.json").exists()
    finally:
        held.release()


def test_the_tray_file_names_the_trays_process(
    tmp_path: Path, pystray: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    """run_tray writes tray.json (its process id, which an update waits for) and removes it as it ends."""
    seen: dict[str, Any] = {}

    def run(self: Any, setup: Any = None) -> None:
        seen["file"] = json.loads((tmp_path / "tray.json").read_text())
        seen["title"] = self.title

    spawned: list[list[str]] = []
    monkeypatch.setattr(pystray.Icon, "run", run)
    monkeypatch.setattr(tray_module, "detached", spawned.append)
    monkeypatch.setattr(tray_module, "Autostart", FakeAutostart)
    assert tray_module.run_tray(tmp_path / "server.json") == 0
    assert seen["file"] == {"pid": os.getpid()} and seen["title"] == "Swiss Army Bench: stopped"
    assert not (tmp_path / "tray.json").exists()
    # No server was running: the tray started one (at sign-in this is how the app starts).
    assert [command[-4:] for command in spawned] == [
        ["swissarmybench.server", "start", "--no-browser", "--no-tray"]
    ]
