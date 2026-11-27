"""The screen state (the owner, 2026-11-27): what each window shows, as text the agent reads on demand.

The shape and its rule (names only, never a value; the cap's trims), the service that keeps the latest per
window in memory, the socket a window reports over, the routes and the command the agent reads by, and that
none of it reaches the prompt hook or context.md.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pyarrow as pa
import pytest
from starlette.testclient import TestClient

from swissarmybench.client import context_hook
from swissarmybench.domain import screen
from swissarmybench.services.screen import Screens
from swissarmybench.services.workspace import NotFound
from tests.conftest import AGENT, AUTH, PORT, push

HOST = {"Host": f"127.0.0.1:{PORT}"}
# A made-up cell value and a made-up secret: neither may ever be kept.
VALUE = "Larkfield-Value-7731"
SECRET = "hunter2-made-up"

TABLES: dict[str, Any] = {
    "window": "sab-home",
    "page": "tables",
    "address": "tables?grid=g1",
    "title": "Tables · Swiss Army Bench",
    "width": 1280,
    "height": 800,
    "focused": True,
    "dialogs": ["Keep rows"],
    "errors": ["The column amount has no number in 3 rows."],
    "table": {
        "grid": "g1",
        "name": "orders",
        "rows": 120,
        "columns": [{"name": "id", "type": "BIGINT"}, {"name": "region", "type": "VARCHAR"}],
        "steps": [
            {"kind": "filter", "enabled": True, "op": "eq", "columns": ["region"]},
            {"kind": "sort", "enabled": True, "columns": ["id"], "directions": ["desc"]},
            {"kind": "limit", "enabled": False},
        ],
        "selection": {
            "kind": "cells",
            "rows": [{"first": 2, "last": 4}],
            "columns": ["region"],
            "column_numbers": [2],
        },
        "showing": {"first": 1, "last": 22},
    },
}

SCRIPTS: dict[str, Any] = {
    "window": "sab-scripts",
    "page": "scripts",
    "focused": False,
    "tab": {"title": "load.py", "path": "scripts/load.py", "kind": "script", "dirty": True},
    "cursor": {"line": 14, "column": 5},
    "selection": {"from_line": 14, "to_line": 18},
    "panes": ["Files", "Blades"],
    "problems": 2,
}


# ===== the shape (domain) =====


def test_a_report_is_read_into_the_one_shape() -> None:
    state = screen.clean(TABLES)
    assert state["kind"] == "tables" and state["page"] == "tables" and state["focused"] is True
    assert (state["width"], state["height"]) == (1280, 800)
    table = state["table"]
    assert table["name"] == "orders" and table["rows"] == 120
    assert [c["name"] for c in table["columns"]] == ["id", "region"]
    assert table["steps"] == [
        "1. Keep rows where region is a value (not shown)",
        "2. Sort by id descending",
        "3. Keep the first rows (off)",
    ]
    assert table["sort"] == [{"column": "id", "direction": "descending"}]
    assert table["filter"] == ["region"]
    assert table["selection"]["rows"] == [{"first": 2, "last": 4}]
    assert table["selection"]["column_numbers"] == [2]
    assert table["showing"] == {"first": 1, "last": 22}
    assert state["dialogs"] == ["Keep rows"]

    script = screen.clean(SCRIPTS)
    assert script["kind"] == "scripts"
    assert script["tab"] == {"title": "load.py", "path": "scripts/load.py", "kind": "script", "dirty": True}
    assert script["cursor"] == {"line": 14, "column": 5}
    assert script["selection"] == {"from_line": 14, "to_line": 18} and script["problems"] == 2


KINDS = [("", "home"), ("tables", "tables"), ("grids", "tables"), ("notebooks", "notebooks")]
KINDS += [("canvas", "canvas"), ("settings", "settings"), ("x-scm", "x-scm"), ("Connections/", "connections")]


@pytest.mark.parametrize(("page", "kind"), KINDS)
def test_the_kind_is_the_pages_first_part(page: str, kind: str) -> None:
    assert screen.kind_of(page) == kind


def test_a_value_on_screen_never_reaches_it() -> None:
    """Names only: the shape has no place for a cell's value, an output, code or a secret, so whatever a
    page sends beside the names is dropped."""
    hostile = json.loads(json.dumps(TABLES))
    hostile |= {"values": [VALUE], "output": VALUE, "code": f"x = '{VALUE}'", "password": SECRET}
    hostile["table"] |= {"cells": [[VALUE]], "rows_shown": [{"region": VALUE}], "value": VALUE}
    hostile["table"]["columns"][0] |= {"sample": VALUE, "top": [VALUE]}
    hostile["table"]["steps"][0] |= {"value": VALUE, "values": [VALUE], "params": {"value": VALUE}}
    hostile["table"]["selection"] |= {"values": [VALUE], "sum": 99.5}
    hostile["tab"] = {"title": "load.py", "text": f"password = '{SECRET}'", "source": VALUE}
    hostile["cursor"] = {"line": 3, "column": 1, "text": VALUE, "word": SECRET}
    hostile["notebook"] = {
        "focused": 4,
        "visible": [{"number": 4, "state": "ran", "output": VALUE, "source": VALUE}],
    }
    hostile["settings"] = {"section": "Team", "token": SECRET}
    kept = json.dumps(screen.clean(hostile))
    assert VALUE not in kept and SECRET not in kept
    assert '"sum"' not in kept and "99.5" not in kept
    # What is kept is the same as with nothing hostile sent beside it.
    assert screen.clean(hostile)["table"] == screen.clean(TABLES)["table"]


def test_a_filters_value_is_never_in_a_steps_words() -> None:
    step = {"kind": "filter", "op": "in", "columns": ["region"], "values": [VALUE]}
    assert screen.step_words(step, 1) == "1. Keep rows where region is one of a value (not shown)"
    assert screen.step_words({"kind": "filter", "op": "blank", "columns": ["region"]}, 2) == (
        "2. Keep rows where region is blank"
    )
    assert screen.step_words({"kind": "group_by", "columns": ["region", "month"]}, 3) == (
        "3. Group by region, month"
    )


def test_wrong_types_are_dropped_not_guessed() -> None:
    state = screen.clean(
        {
            "page": "scripts",
            "width": "1280",
            "focused": "yes",
            "problems": 2.5,
            "dialogs": "Save as",
            "cursor": {"line": True, "column": 4},
            "panes": ["Files", 7, None, {"a": 1}],
            "title": "A   title\nover  two lines",
        }
    )
    assert state == {
        "kind": "scripts",
        "page": "scripts",
        "cursor": {"column": 4},
        "panes": ["Files"],
        "title": "A title over two lines",
    }
    assert screen.clean("not a report") == {"kind": "home"} and screen.clean(None) == {"kind": "home"}
    long = screen.clean({"title": "t" * 500, "errors": ["e" * 900]})
    assert len(long["title"]) == screen.NAME_LENGTH and len(long["errors"][0]) == screen.TEXT_LENGTH


def test_the_cap_trims_in_its_stated_order() -> None:
    wide = json.loads(json.dumps(TABLES))
    wide["table"]["columns"] = [{"name": f"a_long_column_name_{n:03}", "type": "VARCHAR"} for n in range(200)]
    wide["errors"] = ["A long sentence of an error. " * 9] * 4
    state = screen.clean(wide)
    assert screen.size(state) <= screen.MAX_BYTES
    assert state["trimmed"] == ["lists_30"] and len(state["table"]["columns"]) == 30
    assert state["table"]["name"] == "orders" and state["table"]["rows"] == 120  # the names stay

    # Each trim only while it is still over; the order is TRIMS'.
    names = [name for name, _words in screen.TRIMS]
    assert names == ["lists_30", "texts_120", "lists_10", "lists_3", "parts"]
    small = screen.capped(state, 1800)
    assert small["trimmed"] == ["lists_30", "texts_120", "lists_10"]
    assert all(len(text) <= 120 for text in small["errors"]) and len(small["table"]["columns"]) == 10
    tiny = screen.capped(state, 300)
    assert tiny["trimmed"] == names and "table" not in tiny and tiny["kind"] == "tables"
    # Nothing over, nothing trimmed.
    assert "trimmed" not in screen.clean(TABLES)


def test_one_line_of_what_a_window_shows() -> None:
    assert screen.shows(screen.clean(TABLES)) == (
        "table orders, 120 rows, 2 columns, 3 steps, sorted by id descending, cells selected; "
        "dialog Keep rows; 1 error showing"
    )
    assert screen.shows(screen.clean(SCRIPTS)) == "script scripts/load.py (unsaved); cursor at line 14"
    brief = screen.brief(screen.clean(TABLES))
    assert brief["kind"] == "tables" and brief["size"] == [1280, 800] and "table" not in brief


# ===== the server keeps it (service) =====


class Clock:
    def __init__(self) -> None:
        self.at = datetime(2026, 11, 27, 9, 0, 0, tzinfo=UTC)

    def __call__(self) -> datetime:
        return self.at

    def tick(self, seconds: float) -> None:
        self.at += timedelta(seconds=seconds)


def test_the_latest_per_window_stamped_when_it_last_changed() -> None:
    clock = Clock()
    screens = Screens(clock)
    assert screens.read() == {"windows": [], "note": screen.NO_WINDOWS}

    home, code = object(), object()
    assert (screens.opened(home), screens.opened(code), screens.opened(home)) == ("w1", "w2", "w1")
    # A page that has not reported yet is said as such.
    waiting = screens.read()["windows"]
    assert [w["reported"] for w in waiting] == [False, False] and waiting[0]["note"] == screen.NOT_REPORTED

    clock.tick(5)
    assert screens.report(home, SCRIPTS) is True
    clock.tick(5)
    assert screens.report(code, TABLES) is True
    clock.tick(20)
    assert screens.report(code, TABLES) is False  # the same again: its stamp stays
    listing = screens.read()
    assert [w["id"] for w in listing["windows"]] == ["w2", "w1"] and listing[
        "focused"
    ] == "w2"  # focused first
    first = listing["windows"][0]
    assert first["changed"] == "2026-11-27T09:00:10+00:00" and first["seconds_ago"] == 20
    assert first["shows"].startswith("table orders, 120 rows") and "table" not in first

    full = screens.read("w2")
    assert full["table"]["name"] == "orders" and full["reported"] is True and full["id"] == "w2"
    assert screens.read("focused")["id"] == "w2" and screens.read("scripts")["id"] == "w1"
    with pytest.raises(NotFound, match=r"No window w9 is open. Open now: w2 \(tables\), w1 \(scripts\)"):
        screens.read("w9")

    # A change moves the stamp; a closed window is dropped.
    assert screens.report(code, TABLES | {"focused": False}) is True
    assert screens.read("w2")["seconds_ago"] == 0 and "focused" not in screens.read()
    screens.closed(code)
    assert [w["id"] for w in screens.read()["windows"]] == ["w1"]
    assert screens.report(code, TABLES) is False  # a window that is gone reports nothing


def test_only_a_report_is_heard() -> None:
    screens = Screens(Clock())
    page = object()
    screens.opened(page)
    assert screens.heard(page, '{"type":"focus"}') is False
    assert screens.heard(page, "not json") is False and screens.heard(page, "[1, 2]") is False
    assert screens.heard(page, json.dumps({"type": "screen", "state": {"page": "x" * 70_000}})) is False
    assert screens.read("w1")["reported"] is False
    assert screens.heard(page, json.dumps({"type": "screen", "state": SCRIPTS})) is True
    assert screens.read("w1")["cursor"]["line"] == 14
    assert screens.heard(object(), json.dumps({"type": "screen", "state": SCRIPTS})) is False  # never opened


# ===== the socket, the routes, the command =====


def _report(state: dict[str, Any]) -> str:
    return json.dumps({"type": "screen", "state": state})


def test_windows_report_over_their_socket_and_the_agent_reads(client: TestClient) -> None:
    assert client.get("/screen", headers=AGENT).json() == {"windows": [], "note": screen.NO_WINDOWS}
    with client.websocket_connect("/ws?workspace=1", headers=AUTH | HOST) as home:
        listing = client.get("/screen", headers=AGENT).json()
        assert [w["reported"] for w in listing["windows"]] == [False]
        home.send_text(_report(TABLES))
        with client.websocket_connect("/ws?workspace=1", headers=AUTH | HOST) as code:
            code.send_text(_report(SCRIPTS))
            code.send_text('{"type":"focus"}')  # the other message a window sends still works
            listing = client.get("/screen", headers=AGENT).json()
            assert [(w["id"], w["kind"]) for w in listing["windows"]] == [("w1", "tables"), ("w2", "scripts")]
            assert listing["focused"] == "w1"
            full = client.get("/screen/scripts", headers=AGENT).json()
            assert full["tab"]["path"] == "scripts/load.py" and full["cursor"] == {"line": 14, "column": 5}
            assert client.get("/screen/w1", headers=AGENT).json()["table"]["sort"] == [
                {"column": "id", "direction": "descending"}
            ]
            missing = client.get("/screen/w7", headers=AGENT)
            assert missing.status_code == 404 and "No window w7 is open" in missing.json()["error"]
        # The second window closed: gone.
        assert [w["id"] for w in client.get("/screen", headers=AGENT).json()["windows"]] == ["w1"]
    assert client.get("/screen", headers=AGENT).json()["windows"] == []


def test_the_agents_own_socket_is_no_window_and_reports_nothing(client: TestClient) -> None:
    with client.websocket_connect("/ws?agent=1", headers=AGENT | HOST) as agent:
        agent.send_text(_report(TABLES))
        with client.websocket_connect("/ws?opener=1", headers=AUTH | HOST) as opener:
            opener.send_text(_report(TABLES))
            assert client.get("/screen", headers=AGENT).json()["windows"] == []
    # There is no route to report by: only a window's socket says what a window shows.
    assert client.post("/screen", json={"state": TABLES}, headers=AUTH).status_code == 405


def test_app_screen_reads_all_or_one(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    from swissarmybench.cli import api
    from swissarmybench.cli.api import CommandError
    from swissarmybench.cli.commands import execute

    def fake_call(method: str, path: str, body: Any = None, params: Any = None, timeout: float = 0) -> Any:
        response = client.request(method, path, json=body, params=params, headers=AGENT)
        if response.status_code >= 400:
            raise CommandError(f"{response.status_code}: {response.text}")
        return response.json()

    monkeypatch.setattr(api, "call", fake_call)
    with client.websocket_connect("/ws?workspace=1", headers=AUTH | HOST) as home:
        home.send_text(_report(TABLES))
        assert client.get("/screen", headers=AGENT).json()["windows"]  # the report has landed
        listing = json.loads(execute("app_screen"))
        assert listing["windows"][0]["shows"].startswith("table orders")
        assert json.loads(execute("app_screen", {"window": "focused"}))["table"]["name"] == "orders"
        with pytest.raises(CommandError, match="No window w5 is open"):
            execute("app_screen", {"window": "w5"})


def test_the_mcp_has_the_tool_and_the_resource() -> None:
    from swissarmybench.cli.commands import REGISTRY
    from swissarmybench.mcp import server as mcp_server

    assert "app_screen" in REGISTRY and "Names only" in REGISTRY["app_screen"].summary
    assert mcp_server.SCREEN_URI == "swissarmybench://screen"
    index = Path(mcp_server.__file__).with_name("index.md").read_text(encoding="utf-8")
    assert "`app_screen`" in index
    grids = Path(mcp_server.__file__).parent.joinpath("guide", "grids.md").read_text(encoding="utf-8")
    assert "instead of asking for a snapshot" in " ".join(grids.split())


# ===== never pushed: not in the prompt hook, not in context.md =====

MARK = "zebra_marker_table"


def test_it_is_not_in_the_prompt_hook_nor_in_context_md(client: TestClient) -> None:
    """ "It shouldn't send the screen every turn that will kill context. it should just be accessible when
    needed": what a window shows is in none of the routes the prompt hook reads, nor in context.md's text."""
    push(client, "orders", pa.table({"id": [1, 2]}))
    shown = json.loads(json.dumps(TABLES))
    shown["table"]["name"] = MARK
    shown["dialogs"] = [f"{MARK} dialog"]
    with client.websocket_connect("/ws?workspace=1", headers=AUTH | HOST) as home:
        home.send_text(_report(shown))
        assert MARK in client.get("/screen/focused", headers=AGENT).text  # it is there when asked for
        context = client.get("/claude/context", headers=AGENT)
        assert context.status_code == 200 and "orders" in context.text and MARK not in context.text
        for route in ("/agent/inbox", "/claude/context/prompt", "/agent/context"):  # what the hook reads
            answer = client.get(route, headers=AGENT)
            assert answer.status_code == 200 and MARK not in answer.text


def test_the_hook_and_context_md_never_read_the_screen() -> None:
    import swissarmybench.domain.context_md as context_domain
    import swissarmybench.services.context_md as context_service

    assert "/screen" not in Path(context_hook.__file__).read_text(encoding="utf-8")
    for module in (context_domain, context_service):
        source = Path(str(module.__file__)).read_text(encoding="utf-8")
        assert "services.screen" not in source and "domain.screen" not in source
        assert "app_screen" not in source and "import screen" not in source


def test_the_parts_a_page_keeps_in_its_address() -> None:
    detail = screen.clean({"page": "connections", "address": "connections?name=Finance%20Captive"})
    assert detail["connections"] == {"view": "detail", "selected": "Finance Captive"}
    assert screen.shows(detail) == "connection Finance Captive"
    assert screen.clean({"page": "connections", "address": "connections"})["connections"] == {"view": "cards"}
    assert (
        screen.clean({"page": "connections", "address": "connections?add=1"})["connections"]["view"] == "add"
    )
    assert screen.clean({"page": "", "address": "?view=projects"})["home"] == {"view": "projects"}
    assert "home" not in screen.clean({"page": "tables", "address": "tables?view=projects"})
