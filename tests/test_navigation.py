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
    assert rules.place("home", " sandbox ") == {"window": "home", "to": "sandbox"}
    assert rules.place("home", "grid:g1") == {"window": "home", "to": "grid", "grid": "g1"}
    assert rules.place("home", "add_api") == {"window": "home", "to": "add_api"}
    assert rules.place("catalog", "catalog") == {"window": "catalog", "to": "catalog"}
    assert rules.place("catalog", "catalog:Warehouse/sales/orders") == {
        "window": "catalog",
        "to": "catalog",
        "catalog": "Warehouse",
        "schema": "sales",
        "table": "orders",
    }
    assert rules.place("catalog", "catalog:Warehouse") == {
        "window": "catalog",
        "to": "catalog",
        "catalog": "Warehouse",
    }
    assert rules.place("catalog", "blade:refresh_sales") == {
        "window": "catalog",
        "to": "blade",
        "name": "refresh_sales",
    }
    assert rules.place("workbench", "forward") == {"window": "workbench", "to": "forward"}
    assert "grid:<id>" in rules.places("home") and "sandbox" not in rules.places("workbench")


@pytest.mark.parametrize(
    ("window", "to", "words"),
    [
        ("tray", "home", "window is one of home, catalog, workbench"),
        ("home", "", "to is where to go: home, back"),
        ("home", None, "to is where to go"),
        ("home", "kitchen", "The home window cannot go to 'kitchen'. It can go to: home, back"),
        ("workbench", "sandbox", "The workbench window cannot go to 'sandbox'"),
        ("catalog", "grid:g1", "The catalog window cannot go to 'grid:g1'"),
        ("home", "grid:", "cannot go to 'grid:'"),
        ("catalog", "blade:", "cannot go to 'blade:'"),
        ("catalog", "catalog:Warehouse//orders", "catalog:<name>/<schema>/<table>"),
        ("home", "grid:" + "g" * 600, "longer than 512"),
    ],
)
def test_a_place_that_is_not_one_says_what_is(window: str, to: object, words: str) -> None:
    with pytest.raises(rules.NavigationError, match=words.replace("(", r"\(").replace(")", r"\)")):
        rules.place(window, to)


def test_the_window_is_told_and_the_audit_log_says_where(tmp_path: Path) -> None:
    with make_client(tmp_path) as client:
        # No home page open: said, not sent into nothing.
        refused = client.post("/navigate", json={"to": "sandbox"}, headers=AGENT)
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
        # The blades page is a window of its own: only an open one is told.
        assert (
            client.post("/navigate", json={"window": "catalog", "to": "back"}, headers=AGENT).status_code
            == 409
        )
        with client.websocket_connect("/ws?catalog=1", headers=AUTH | HOST) as catalog:
            assert (
                client.post(
                    "/navigate", json={"window": "catalog", "to": "blade:x"}, headers=AGENT
                ).status_code
                == 200
            )
            assert catalog.receive_json()["name"] == "x"
        refused = client.post("/navigate", json={"window": "workbench", "to": "back"}, headers=AGENT)
        assert refused.status_code == 409 and "No Workbench window is open" in refused.text
        assert "home window to grid g7" in client.get("/audit", headers=AUTH).text


def test_the_agent_moves_the_window(live: Live) -> None:  # noqa: F811
    with pytest.raises(Exception, match="No home window is open"):
        command("app_navigate", to="home")
    with pytest.raises(Exception, match="cannot go to 'kitchen'"):
        command("app_navigate", to="kitchen")
