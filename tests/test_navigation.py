"""Getting around (the owner, 2026-11-16): the places an agent sends a window to with app_navigate, the
notice the window acts on, and the refusal when no such window is open. The browser half (the mark, Back,
the address, breadcrumbs, titles) is tests/e2e/test_navigation_page.py. Made-up names only."""

from __future__ import annotations

from pathlib import Path

import pytest

from swissarmybench.domain import navigation as rules
from tests.conftest import AGENT, AUTH, PORT, make_client
from tests.test_cli import Live, live  # noqa: F401 (the running server)
from tests.test_cli import run as command

HOST = {"Host": f"127.0.0.1:{PORT}"}


def test_each_window_names_the_places_it_has() -> None:
    assert rules.place(None, "home") == {"window": "home", "to": "home"}
    assert rules.place("home", "back") == {"window": "home", "to": "back"}
    assert rules.place("home", " analyze ") == {"window": "home", "to": "analyze"}
    assert rules.place("scripts", "erd") == {"window": "scripts", "to": "erd"}
    # The old blades page went (2026-11-21): its window is the Scripts page's, one release.
    assert rules.place("catalog", "erd") == {"window": "scripts", "to": "erd"}
    # The Start view is the Projects page (the owner, 2026-11-18): its old name, one release.
    assert rules.place("home", "start") == {"window": "home", "to": "projects"}
    assert rules.place("workbench", " start ") == {"window": "workbench", "to": "projects"}
    assert rules.place("home", "grid:g1") == {"window": "home", "to": "grid", "grid": "g1"}
    assert rules.place("home", "add_api") == {"window": "home", "to": "add_api"}
    # The blades page's catalog panel went (the owner, 2026-11-17): its views are no places.
    with pytest.raises(rules.NavigationError):
        rules.place("catalog", "catalog:Warehouse/sales/orders")
    assert rules.place("catalog", "blade:refresh_sales") == {
        "window": "scripts",
        "to": "blade",
        "name": "refresh_sales",
    }
    assert rules.place("workbench", "forward") == {"window": "workbench", "to": "forward"}
    # A connection's detail on the Connections page (2026-11-16), from every window.
    for window in rules.WINDOWS:
        assert rules.place(window, "connection:Warehouse") == {
            "window": rules.OLD_WINDOWS.get(window, window),
            "to": "connection",
            "name": "Warehouse",
        }
    assert "grid:<id>" in rules.places("home") and "query" not in rules.places("workbench")


def test_the_new_query_page_and_a_draft_on_a_connection() -> None:
    """The owner, 2026-11-20: "this should just be a new query page, with the active connections and you
    can click one to start a new grid sql": the page (new_query), and a draft with Query from set
    (query:<name>)."""
    assert rules.place("home", "new_query") == {"window": "home", "to": "new_query"}
    assert rules.place("home", "query") == {"window": "home", "to": "query"}
    assert rules.place("home", "query:Warehouse") == {"window": "home", "to": "query", "name": "Warehouse"}
    assert rules.said(rules.place("home", "query:Warehouse")) == "home window to query Warehouse"
    with pytest.raises(rules.NavigationError, match="cannot go to 'new_query'"):
        rules.place("workbench", "new_query")


def test_every_rail_area_is_a_place_from_every_window() -> None:
    """The rail (2026-11-16): each area, in the rail's order, from each window, as a rail click goes."""
    assert rules.AREAS == (  # in the order of the work (the owner, 2026-11-17)
        "projects",  # the mark, the rail's first item: the Projects page (2026-11-18)
        "connections",
        "apis",
        "environment",  # everything the project holds, in the Structures and Variables places (2026-11-22)
        "data",  # the one place to browse tables (2026-11-17)
        "tables",
        "erd",
        "scripts",  # its Blades pane on the right: no Blades icon (2026-11-22)
        "notebooks",
        "canvas",  # the Apps area renamed (2026-11-21)
        "widgets",  # the Widgets window (2026-11-21)
        "analyze",
        "session",
        "extensions",
        "settings",
    )
    for old in rules.WINDOWS:
        window = rules.OLD_WINDOWS.get(old, old)
        for area in rules.AREAS:
            assert area in rules.places(window)
            # Grids is the home page's tabbed grids, only the grids; projects (the mark) and home are
            # the Projects page (2026-11-18).
            assert rules.place(window, area) == {"window": window, "to": area}
        assert rules.place(window, " grids ") == {"window": window, "to": "tables"}
        assert rules.place(window, "home") == {"window": window, "to": "home"}
        # Notebooks and Scripts open in a Workbench window of their own too (the "external tab").
        for code in ("notebooks", "scripts"):
            assert rules.place(window, code, True) == {"window": window, "to": code, "new_window": True}
            assert rules.place(window, code, False) == {"window": window, "to": code}
    assert rules.said(rules.place("home", "scripts", True)) == "home window to scripts, in a new window"
    assert rules.place("home", "apps") == {"window": "home", "to": "canvas"}  # the old word, one release
    with pytest.raises(rules.NavigationError, match="Only notebooks, scripts open in a new window"):
        rules.place("home", "analyze", True)
    with pytest.raises(rules.NavigationError, match="new_window is true or false"):
        rules.place("home", "apps", "yes")


@pytest.mark.parametrize(
    ("window", "to", "words"),
    [
        ("tray", "home", "window is one of home, workbench, notebooks, scripts"),
        ("home", "", "to is where to go: home, projects, connections, apis, environment, data"),
        ("home", None, "to is where to go"),
        (
            "home",
            "kitchen",
            "The home window cannot go to 'kitchen'. It can go to: home, projects, connections, apis",
        ),
        ("workbench", "query", "The workbench window cannot go to 'query'"),
        ("scripts", "grid:g1", "The scripts window cannot go to 'grid:g1'"),
        ("home", "grid:", "cannot go to 'grid:'"),
        ("catalog", "blade:", "cannot go to 'blade:'"),
        ("workbench", "connection:", "cannot go to 'connection:'"),
        ("scripts", "catalog:Warehouse", "The scripts window cannot go to 'catalog:Warehouse'"),
        ("home", "grid:" + "g" * 600, "longer than 512"),
    ],
)
def test_a_place_that_is_not_one_says_what_is(window: str, to: object, words: str) -> None:
    with pytest.raises(rules.NavigationError, match=words.replace("(", r"\(").replace(")", r"\)")):
        rules.place(window, to)


def test_the_window_is_told_and_the_audit_log_says_where(tmp_path: Path) -> None:
    with make_client(tmp_path) as client:
        # No home page open: said, not sent into nothing.
        refused = client.post("/navigate", json={"to": "analyze"}, headers=AGENT)
        assert refused.status_code == 409 and "No home window is open" in refused.text
        assert client.post("/navigate", json={"to": "kitchen"}, headers=AGENT).status_code == 400
        with client.websocket_connect("/ws?workspace=1", headers=AUTH | HOST) as page:
            sent = client.post("/navigate", json={"to": "grid:g7"}, headers=AGENT)
            assert sent.status_code == 200, sent.text
            assert sent.json() == {"sent": {"window": "home", "to": "grid", "grid": "g7"}}
            assert page.receive_json() == {
                "type": "navigate",
                "window": "home",
                "to": "grid",
                "grid": "g7",
                "by": "agent",
            }
        # A blade's tab is the Scripts page's (the old blades page's window read as it): only an open one
        # is told.
        assert (
            client.post("/navigate", json={"window": "catalog", "to": "back"}, headers=AGENT).status_code
            == 409
        )
        refused = client.post("/navigate", json={"window": "workbench", "to": "back"}, headers=AGENT)
        assert refused.status_code == 409 and "No Notebooks or Scripts page is open" in refused.text
        assert "home window to grid g7" in client.get("/audit", headers=AUTH).text


def test_the_agent_moves_the_window(live: Live) -> None:  # noqa: F811
    with pytest.raises(Exception, match="No home window is open"):
        command("app_navigate", to="home")
    with pytest.raises(Exception, match="cannot go to 'kitchen'"):
        command("app_navigate", to="kitchen")


def test_grids_is_the_tables_pages_old_word() -> None:
    """The owner, 2026-11-23: Grids is Tables. app_navigate's place is `tables`; `grids` is read as it."""
    assert rules.place("home", "tables") == {"window": "home", "to": "tables"}
    assert rules.place("home", "grids") == {"window": "home", "to": "tables"}
    assert rules.blazor_page("/g/g7", {}) == ("tables", {"grid": "g7"})
