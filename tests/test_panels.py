"""The panels Settings can turn off (the owner, 2026-11-15): every one on by default, switched off
and on again, shared by every window, and every one on again when Swiss Army Bench starts (memory
only). The agent reads and sets them too."""

from __future__ import annotations

from pathlib import Path

import pytest

from swissarmybench.domain import panels as rules
from tests.conftest import AGENT, AUTH, make_client
from tests.test_cli import Live, live  # noqa: F401 (the running server)
from tests.test_cli import run as command


def test_every_panel_is_on_until_switched_off() -> None:
    state = rules.defaults()
    assert set(state) == set(rules.IDS) and all(state.values())
    assert {page for _, page, _ in rules.PANELS} == {"Workbench", "Grid page", "Every page"}
    assert rules.PANELS[-1] == ("app.rail", "Every page", "Navigation rail")
    assert rules.changes({"workbench.console": False}) == {"workbench.console": False}
    for bad, words in (
        ({}, "Send the switches"),
        ({"workbench.nope": False}, "No panel is called 'workbench.nope'"),
        ({"workbench.console": "off"}, "true \\(on\\) or false"),
        ([], "Send the switches"),
    ):
        with pytest.raises(rules.PanelError, match=words):
            rules.changes(bad)


def test_switches_are_the_servers_shared_and_on_again_at_each_start(tmp_path: Path) -> None:
    with make_client(tmp_path) as client:
        listed = client.get("/panels", headers=AUTH).json()["panels"]
        assert [p["id"] for p in listed] == list(rules.IDS) and all(p["on"] for p in listed)
        assert listed[4] == {"id": "workbench.console", "page": "Workbench", "name": "Console", "on": True}
        off = client.put("/panels", json={"workbench.console": False, "grid.ribbon": False}, headers=AUTH)
        assert off.status_code == 200, off.text
        state = {p["id"]: p["on"] for p in client.get("/panels", headers=AGENT).json()["panels"]}
        assert state["workbench.console"] is False and state["grid.ribbon"] is False
        assert sum(not on for on in state.values()) == 2
        assert client.put("/panels", json={"grid.ribbon": "no"}, headers=AUTH).status_code == 400
        back = client.put("/panels", json={"grid.ribbon": True}, headers=AUTH).json()["panels"]
        assert {p["id"]: p["on"] for p in back}["grid.ribbon"] is True
    # A new start of Swiss Army Bench: every panel on again (nothing was written to disk).
    with make_client(tmp_path) as client:
        assert all(p["on"] for p in client.get("/panels", headers=AUTH).json()["panels"])


def test_the_agent_reads_and_sets_the_switches(live: Live) -> None:  # noqa: F811
    assert all(p["on"] for p in command("app_panels")["panels"])
    done = command("app_panels", set={"workbench.streamlit": False})
    assert {p["id"]: p["on"] for p in done["panels"]}["workbench.streamlit"] is False
    assert {p["id"]: p["on"] for p in live.user("GET", "/panels")["panels"]}["workbench.streamlit"] is False
