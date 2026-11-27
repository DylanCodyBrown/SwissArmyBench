"""Pop out any page or any table into a window of its own (the owner, 2026-11-27).

The rules (keys, addresses, the words), the service's owner map (one owner at a time, popping out twice,
closing either side, a window that never connects, a reload), the routes over the live socket, the agent's
command and what app_screen says of each window. Made-up tables only.
"""

from __future__ import annotations

import asyncio
import json
from typing import Any

import pyarrow as pa
import pytest
from starlette.testclient import TestClient

from swissarmybench.domain import pop_outs as rules
from swissarmybench.domain import screen
from swissarmybench.services.pop_outs import NO_MAIN, PopOuts
from swissarmybench.services.workspace import Conflict, NotFound
from tests.conftest import AGENT, AUTH, PORT, push
from tests.test_service_layer import audit_of, told, workspace

HOST = {"Host": f"127.0.0.1:{PORT}"}
CONNECTIONS = {"key": "page:connections", "name": "Connections", "address": "connections", "open": False}


def said(key: str, address: str, name: str = "Connections") -> str:
    return json.dumps({"type": "pop_out", "key": key, "name": name, "address": address})


class Window:
    """A window's socket as the service sees it: what it was sent."""

    def __init__(self) -> None:
        self.got: list[dict[str, Any]] = []

    async def send(self, message: dict[str, Any]) -> None:
        self.got.append(message)


# ===== the rules =====


def test_keys_addresses_and_the_words() -> None:
    assert rules.read_key("page:connections") == "page:connections"
    assert rules.read_key("table:g 7") == "table:g 7"
    assert rules.read_key("doc:scripts/load.py") == "doc:scripts/load.py"
    for bad in ("", "connections", "window:x", "page:", "page:Has Space", 7, None, "table: g1"):
        with pytest.raises(rules.PopOutError):
            rules.read_key(bad)
    assert rules.read_address("connections?name=Finance%20Captive") == "connections?name=Finance%20Captive"
    assert rules.read_address("") == ""  # Home
    for outside in (
        "https://example.com/x",
        "//example.com",
        "/etc/passwd",
        "../x",
        "a\\b",
        "javascript:1",
        4,
    ):
        with pytest.raises(rules.PopOutError):
            rules.read_address(outside)
    assert rules.placeholder("orders") == "orders is open in its own window"
    assert rules.window_name("table:g1") == "sab-pop:table:g1"


def test_a_page_by_the_agents_word_and_a_table() -> None:
    assert rules.page_entry("connections").said() == {
        "key": "page:connections",
        "kind": "page",
        "name": "Connections",
        "address": "connections",
        "connected": False,
        "placeholder": "Connections is open in its own window",
    }
    home = rules.page_entry("home")
    assert (home.key, home.name, home.address) == ("page:home", "Home", "")
    assert rules.page_entry("projects").key == "page:home"
    assert rules.page_entry("grids").key == "page:tables"
    assert rules.page_entry("data").name == "Catalog"
    assert rules.page_entry("x-scm").name == "Scm"
    with pytest.raises(rules.PopOutError):
        rules.page_entry("https://example.com")
    table = rules.table_entry("g1", "orders")
    assert (table.key, table.name, table.address) == ("table:g1", "orders", "tables?grid=g1")


def test_what_a_popped_out_window_says_is_read_or_dropped() -> None:
    heard = rules.read_said(said("page:connections", "connections?name=warehouse"))
    assert heard is not None and heard.address == "connections?name=warehouse"
    assert rules.read_said('{"type":"screen","state":{}}') is None
    assert rules.read_said("not json") is None
    assert rules.read_said(said("page:connections", "https://example.com")) is None
    assert rules.read_said(said("page:connections", "x" * 5000)) is None


# ===== the owner map =====


def test_one_owner_at_a_time(tmp_path: Any) -> None:
    async def run() -> None:
        ws = workspace(tmp_path)
        pop_outs = PopOuts(ws)
        main, popped = Window(), Window()
        await pop_outs.opened(main, main.send)
        first = await pop_outs.pop(CONNECTIONS)
        assert first["existing"] is False and first["placeholder"] == "Connections is open in its own window"
        assert pop_outs.listing()["mains"] == 1
        # Its window connects and says what it holds: it is no main window any more.
        await pop_outs.opened(popped, popped.send)
        assert await pop_outs.heard(popped, said("page:connections", "connections"))
        listing = pop_outs.listing()
        assert [(e["key"], e["connected"]) for e in listing["popped"]] == [("page:connections", True)]
        assert listing["mains"] == 1
        # Popping out twice brings the window there is to the front: still one entry.
        again = await pop_outs.pop(CONNECTIONS | {"open": True}, "agent")
        assert again["existing"] is True and len(pop_outs.listing()["popped"]) == 1
        assert told(ws)[-1] == {"type": "pop_out_show", "key": "page:connections"}
        assert main.got == []  # no second window was asked for
        # The window moves: Reattach brings it back where it is now.
        await pop_outs.heard(popped, said("page:connections", "connections?name=warehouse"))
        back = await pop_outs.reattach({"key": "page:connections"})
        assert back["address"] == "connections?name=warehouse" and back["reattached"] is True
        notice = told(ws)[-1]
        assert notice["type"] == "pop_outs" and notice["popped"] == []
        assert notice["reattached"]["address"] == "connections?name=warehouse"
        with pytest.raises(NotFound, match="not in a window of its own"):
            await pop_outs.reattach({"key": "page:connections"})
        assert [(who, action, words) for who, action, words, _ in audit_of(ws)] == [
            ("user", "pop_out", "page Connections"),
            ("user", "reattach", "page Connections"),
        ]

    asyncio.run(run())


def test_closing_the_popped_out_window_brings_it_back(tmp_path: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(rules, "RELOAD_SECONDS", 0.05)

    async def run() -> None:
        ws = workspace(tmp_path)
        pop_outs = PopOuts(ws)
        main, popped = Window(), Window()
        await pop_outs.opened(main, main.send)
        await pop_outs.pop(CONNECTIONS)
        await pop_outs.opened(popped, popped.send)
        await pop_outs.heard(popped, said("page:connections", "connections?add=1"))
        await pop_outs.closed(popped)
        # A reload looks the same at first: the entry waits, said as not connected.
        assert [e["connected"] for e in pop_outs.listing()["popped"]] == [False]
        await asyncio.sleep(0.15)
        assert pop_outs.listing() == {"popped": [], "mains": 1}
        assert told(ws)[-1]["reattached"]["address"] == "connections?add=1"

    asyncio.run(run())


def test_an_old_windows_closing_never_takes_the_new_one_back(tmp_path: Any) -> None:
    async def run() -> None:
        ws = workspace(tmp_path)
        pop_outs = PopOuts(ws)
        main, popped = Window(), Window()
        await pop_outs.opened(main, main.send)
        await pop_outs.pop(CONNECTIONS)
        # Popped out again before its window connected: the opener's "it closed" is the old window's news.
        stale = await pop_outs.reattach({"key": "page:connections", "closed": True})
        assert stale["reattached"] is False and len(pop_outs.listing()["popped"]) == 1
        await pop_outs.opened(popped, popped.send)
        await pop_outs.heard(popped, said("page:connections", "connections"))
        stale = await pop_outs.reattach({"key": "page:connections", "closed": True})
        assert stale["reattached"] is False and len(pop_outs.listing()["popped"]) == 1
        # Its window really gone (its socket closed): the opener's word brings it back at once.
        await pop_outs.closed(popped)
        back = await pop_outs.reattach({"key": "page:connections", "closed": True})
        assert back["reattached"] is True and pop_outs.listing()["popped"] == []

    asyncio.run(run())


def test_a_reload_of_the_popped_out_window_keeps_it(tmp_path: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(rules, "RELOAD_SECONDS", 0.1)

    async def run() -> None:
        ws = workspace(tmp_path)
        pop_outs = PopOuts(ws)
        main, popped, reloaded = Window(), Window(), Window()
        await pop_outs.opened(main, main.send)
        await pop_outs.pop(CONNECTIONS)
        await pop_outs.opened(popped, popped.send)
        await pop_outs.heard(popped, said("page:connections", "connections"))
        await pop_outs.closed(popped)
        await pop_outs.opened(reloaded, reloaded.send)
        await pop_outs.heard(reloaded, said("page:connections", "connections"))
        await asyncio.sleep(0.25)
        assert [(e["key"], e["connected"]) for e in pop_outs.listing()["popped"]] == [
            ("page:connections", True)
        ]
        # One reloaded after its wait ran out holds it again as it says so.
        await pop_outs.closed(reloaded)
        await asyncio.sleep(0.25)
        assert pop_outs.listing()["popped"] == []
        late = Window()
        await pop_outs.opened(late, late.send)
        await pop_outs.heard(late, said("page:connections", "connections"))
        assert [e["connected"] for e in pop_outs.listing()["popped"]] == [True]

    asyncio.run(run())


def test_a_window_that_never_connects_gives_the_place_back(
    tmp_path: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(rules, "CONNECT_SECONDS", 0.05)

    async def run() -> None:
        ws = workspace(tmp_path)
        pop_outs = PopOuts(ws)
        main = Window()
        await pop_outs.opened(main, main.send)
        await pop_outs.pop(CONNECTIONS)
        assert len(pop_outs.listing()["popped"]) == 1
        await asyncio.sleep(0.15)
        assert pop_outs.listing()["popped"] == []
        assert told(ws)[-1]["reattached"]["key"] == "page:connections"

    asyncio.run(run())


def test_the_main_window_closed_first_leaves_the_popped_out_one_alone(tmp_path: Any) -> None:
    async def run() -> None:
        ws = workspace(tmp_path)
        pop_outs = PopOuts(ws)
        main, popped = Window(), Window()
        await pop_outs.opened(main, main.send)
        await pop_outs.pop(CONNECTIONS)
        await pop_outs.opened(popped, popped.send)
        await pop_outs.heard(popped, said("page:connections", "connections"))
        await pop_outs.closed(main)
        # It keeps working by itself: still held, with no main window to go back to.
        assert pop_outs.listing()["mains"] == 0
        assert [e["connected"] for e in pop_outs.listing()["popped"]] == [True]
        assert told(ws)[-1]["mains"] == 0
        # A link out of it finds no main window; a new main window is counted again.
        assert await pop_outs.front({"address": "tables"}) == {"shown": False}
        fresh = Window()
        await pop_outs.opened(fresh, fresh.send)
        assert pop_outs.listing()["mains"] == 1
        assert await pop_outs.front({"address": "tables"}) == {"shown": True}
        assert fresh.got == [{"type": "pop_out_front", "address": "tables"}]

    asyncio.run(run())


def test_the_agents_pop_out_is_opened_by_the_main_window_last_in_front(tmp_path: Any) -> None:
    async def run() -> None:
        ws = workspace(tmp_path)
        pop_outs = PopOuts(ws)
        with pytest.raises(Conflict, match="No main window is open"):
            await pop_outs.pop({"page": "settings"}, "agent")
        assert NO_MAIN and pop_outs.listing()["popped"] == []
        first, second = Window(), Window()
        await pop_outs.opened(first, first.send)
        await pop_outs.opened(second, second.send)
        pop_outs.focused(first)
        made = await pop_outs.pop({"page": "settings"}, "agent")
        assert (made["key"], made["name"], made["address"]) == ("page:settings", "Settings", "settings")
        assert [m["type"] for m in first.got] == ["pop_out_open"] and second.got == []
        assert first.got[0]["address"] == "settings"
        # The popped-out window's own Reattach: the main window last in front goes to it.
        await pop_outs.reattach({"page": "settings", "front": True}, "agent")
        assert first.got[-1]["type"] == "pop_out_front" and first.got[-1]["address"] == "settings"
        with pytest.raises(NotFound):
            await pop_outs.show({"page": "settings"})
        with pytest.raises(NotFound, match="No such open table"):
            await pop_outs.pop({"table": "nope"}, "agent")

    asyncio.run(run())


# ===== the routes, the socket and the command =====


def test_pop_out_and_reattach_over_the_socket(client: TestClient) -> None:
    grid = push(client, "orders", pa.table({"id": [1, 2, 3]})).json()["grid"]
    assert client.get("/pop-outs", headers=AGENT).json() == {"popped": [], "mains": 0}
    refused = client.post("/pop-outs", json={"table": grid}, headers=AGENT)
    assert refused.status_code == 409 and "No main window" in refused.json()["error"]
    with client.websocket_connect("/ws?workspace=1", headers=AUTH | HOST) as main:
        popped = client.post("/pop-outs", json={"table": grid}, headers=AGENT).json()
        assert popped["key"] == f"table:{grid}" and popped["name"] == "orders"
        opened = main.receive_json()
        while opened["type"] != "pop_out_open":
            opened = main.receive_json()
        assert opened["address"] == f"tables?grid={grid}"
        with client.websocket_connect("/ws?workspace=1", headers=AUTH | HOST) as own:
            own.send_text(said(f"table:{grid}", f"tables?grid={grid}", "orders"))
            own.send_text('{"type":"focus"}')
            listing = client.get("/pop-outs", headers=AGENT).json()
            while not listing["popped"][0]["connected"]:
                listing = client.get("/pop-outs", headers=AGENT).json()
            assert listing["mains"] == 1
            # A page's own report still lands (the socket takes both).
            own.send_text(json.dumps({"type": "screen", "state": {"page": "tables", "pop_out": "orders"}}))
            main.send_text(
                json.dumps(
                    {
                        "type": "screen",
                        "state": {
                            "page": "tables",
                            "placeholder": rules.placeholder("orders"),
                            "popped_out": ["orders"],
                        },
                    }
                )
            )
            shows = [w.get("shows", "") for w in client.get("/screen", headers=AGENT).json()["windows"]]
            while not all(shows) or len(shows) < 2:
                shows = [w.get("shows", "") for w in client.get("/screen", headers=AGENT).json()["windows"]]
            assert "orders is open in its own window (Reattach brings it back)" in shows
            assert "orders, popped out in its own window" in shows
            assert client.post("/pop-outs/show", json={"table": grid}, headers=AGENT).status_code == 200
            back = client.post("/pop-outs/reattach", json={"table": grid}, headers=AGENT).json()
            assert back["reattached"] is True
        assert client.get("/pop-outs", headers=AGENT).json()["popped"] == []
    bad = client.post(
        "/pop-outs", json={"key": "page:x", "name": "X", "address": "https://example.com"}, headers=AUTH
    )
    assert bad.status_code == 400


def test_app_navigate_pops_out_lists_shows_and_reattaches(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    from swissarmybench.cli import api
    from swissarmybench.cli.api import CommandError
    from swissarmybench.cli.commands import execute

    def fake_call(method: str, path: str, body: Any = None, params: Any = None, timeout: float = 0) -> Any:
        response = client.request(method, path, json=body, params=params, headers=AGENT)
        if response.status_code >= 400:
            raise CommandError(f"{response.status_code}: {response.text}")
        return response.json()

    monkeypatch.setattr(api, "call", fake_call)
    grid = push(client, "orders", pa.table({"id": [1, 2, 3]})).json()["grid"]
    assert json.loads(execute("app_navigate", {"to": "home", "pop": "list"})) == {"popped": [], "mains": 0}
    with client.websocket_connect("/ws?workspace=1", headers=AUTH | HOST):
        popped = json.loads(execute("app_navigate", {"to": "connections", "pop": "out"}))
        assert popped["key"] == "page:connections"
        assert json.loads(execute("app_navigate", {"to": f"grid:{grid}", "pop": "out"}))["name"] == "orders"
        listed = json.loads(execute("app_navigate", {"to": "home", "pop": "list"}))
        assert [e["name"] for e in listed["popped"]] == ["Connections", "orders"]
        assert json.loads(execute("app_navigate", {"to": "connections", "pop": "show"}))["kind"] == "page"
        assert json.loads(execute("app_navigate", {"to": "connections", "pop": "reattach"}))["reattached"]
        assert json.loads(execute("app_navigate", {"to": f"grid:{grid}", "pop": "reattach"}))["reattached"]
        with pytest.raises(CommandError, match="not in a window of its own"):
            execute("app_navigate", {"to": "connections", "pop": "reattach"})
        with pytest.raises(CommandError, match="pop is out, reattach, show or list"):
            execute("app_navigate", {"to": "connections", "pop": "sideways"})


def test_the_screen_state_has_places_for_it() -> None:
    state = screen.clean(
        {
            "page": "connections",
            "placeholder": "Connections is open in its own window",
            "popped_out": ["Connections", 7],
        }
    )
    assert state["popped_out"] == ["Connections"]
    assert screen.shows(state).startswith("Connections is open in its own window")
    own = screen.clean({"page": "connections", "pop_out": "Connections"})
    assert "popped out in its own window" in screen.brief(own)["shows"]
