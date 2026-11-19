"""The Session page (the owner, 2026-11-16: "when the agent is driving the app and adding things, I want to
see objects that were created in a log make that a new page called Session on the rail"): each action's
entry names its object, never a value; the filter; and Follow the agent, the user's switch (403 for the
agent, who reads it)."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

import pytest

from swissarmybench.domain import session_log as rules
from tests.conftest import AGENT, AUTH, make_client
from tests.test_cli import Live, live  # noqa: F401 (the running server)
from tests.test_cli import run as command

# Made-up values that must never reach an entry: a filter's value, a query's literal, a secret.
SECRET_VALUE = "Globex-7731"
PASSWORD = "hunter2-not-real"


# ===== the rules: each action's words and its object =====


def test_each_kind_of_action_names_its_object() -> None:
    def said(action: str, dataset: str | None = None, **details: Any) -> dict[str, Any]:
        found = rules.entry("agent", action, dataset, details)
        assert found is not None, action
        return found

    step = said("steps", "orders", grid="g3", op="add", kind="filter", steps=2)
    assert step["what"] == "Added a filter step to orders" and step["area"] == "grids"
    assert step["target"] == {"place": "grid", "grid": "g3", "dataset": "orders"}
    assert (
        said("steps", "orders", grid="g3", op="delete", kind="sort")["what"]
        == "Removed a sort step from orders"
    )
    assert said("steps", "orders", grid="g3", steps=3)["what"] == "Set the steps of orders (3 steps)"
    assert said("open_grid", "orders", grid="g4")["target"]["grid"] == "g4"
    card = said("add_card", "orders", kind="chart", card="c7", replaced=False)
    assert card["what"] == "Added a chart card on Analyze" and card["area"] == "analyze"
    ran = said("analyze_run", "orders", analysis="benford", cards=2, grid="g3", run="r1")
    assert ran["what"] == "Ran Do the first digits look natural? on orders (2 cards on Analyze)"
    assert ran["area"] == "analyze" and ran["target"] == {"place": "area", "area": "analyze"}
    fixed = said("analyze_fix", "orders", analysis="benford", fixes=1, grid="g3")
    assert fixed["what"] == "Made orders fit Do the first digits look natural? (1 fix, as steps)"
    assert fixed["target"] == {"place": "grid", "grid": "g3", "dataset": "orders"}
    assert card["target"] == {"place": "card", "card": "c7"}
    edge = said("relationships", None, added=["orders.customer_id -> customers.id"], removed=[])
    assert (
        edge["what"] == "Added the relationship orders.customer_id -> customers.id" and edge["area"] == "erd"
    )
    assert edge["target"] == {
        "place": "relationship",
        "relationships": ["orders.customer_id -> customers.id"],
    }
    two = said("relationships", None, added=["a.x -> b.y", "c.x -> b.y"], removed=["d.x -> b.y"])
    assert two["what"] == "Added 2 relationships, removed the relationship d.x -> b.y"
    conn = said("save_blade", "Warehouse", kind="connection")
    assert conn["area"] == "connections" and conn["target"] == {"place": "connection", "name": "Warehouse"}
    assert said("save_blade", "Tidy names", kind="blade")["target"] == {
        "place": "blade",
        "name": "Tidy names",
    }
    cell = said(
        "workbench_window",
        None,
        command="cell.insertBelow",
        path="/p/sales.ipynb",
        title="sales.ipynb",
        cell=4,
    )
    assert cell["what"] == "Added a cell to sales.ipynb" and cell["area"] == "notebooks"
    assert cell["target"] == {"place": "cell", "path": "/p/sales.ipynb", "cell": 4}
    page = said(
        "streamlit_add_page", "Sales: Overview", title="Sales", detail="Overview", path="/p/sales.stapp.json"
    )
    assert page["what"] == "Added the page Overview in Sales" and page["area"] == "apps"
    exported = said("export", "orders", file="orders.csv", format="csv", rows=12)
    assert exported["what"] == "Exported orders to orders.csv"
    assert said("save_sab_project", None, rows=1)["what"] == "Saved the project with its rows"


def test_reads_and_unknown_actions_make_no_entry() -> None:
    for action in ("describe", "profile", "read", "navigate", "snapshot", "panels", "no_such_action"):
        assert rules.entry("agent", action, "orders", {}) is None
    # A window's read (what is open) makes nothing either.
    assert rules.entry("agent", "workbench_window", None, {"command": "documents"}) is None
    assert rules.entry("someone", "steps", "orders", {}) is None


def test_no_value_ever_reaches_an_entry() -> None:
    """Only the fields each action's words name: a query, a step's value or a password never pass."""
    noisy = {
        "query": f"SELECT * FROM orders WHERE client = '{SECRET_VALUE}'",  # noqa: S608 (a made-up query)
        "value": SECRET_VALUE,
        "params": {"value": SECRET_VALUE},
        "password": PASSWORD,
        "secrets": {"PASSWORD": PASSWORD},
    }
    for action in rules.RULES:
        found = rules.entry("agent", action, "orders", dict(noisy, grid="g1", op="add", kind="filter"))
        text = json.dumps(found)
        assert SECRET_VALUE not in text and PASSWORD not in text, action


def test_the_filter_and_the_switchs_words() -> None:
    entries = [{"id": i, "actor": a} for i, a in enumerate(["agent", "user", "agent"], 1)]
    assert [e["id"] for e in rules.shown(entries, "agent", 10)] == [3, 1]  # newest first
    assert [e["id"] for e in rules.shown(entries, "user", 10)] == [2]
    assert [e["id"] for e in rules.shown(entries, "both", 2)] == [3, 2]
    assert rules.check_filter(None) == "agent"
    with pytest.raises(rules.SessionLogError, match="agent, user, both"):
        rules.check_filter("everyone")
    assert rules.check_follow({"on": False}) is False
    with pytest.raises(rules.SessionLogError):
        rules.check_follow({"on": "no"})
    assert rules.read_saved(None) is True and rules.read_saved({"follow": False}) is False


# ===== over HTTP: the agent's actions, the user's, the switch =====


def _ok(response: Any) -> Any:
    assert response.status_code == 200, response.text
    return response.json()


def test_the_agents_actions_arrive_naming_their_objects(tmp_path: Path) -> None:
    db = tmp_path / "bakery.sqlite"
    with sqlite3.connect(db) as setup:
        setup.execute("CREATE TABLE loaves (id INTEGER, name TEXT)")
    with make_client(tmp_path) as client:
        _ok(
            client.post(
                "/datasets/orders/paste", content=b"id\tclient\n1\tGlobex-7731\n2\tInitech\n", headers=AUTH
            )
        )
        _ok(client.post("/datasets/customers/paste", content=b"id\tname\n1\tAda\n", headers=AUTH))
        grid = _ok(client.post("/grids", json={"dataset": "orders"}, headers=AGENT))["grid"]
        step = {"kind": "filter", "params": {"column": "client", "op": "ne", "value": SECRET_VALUE}}
        _ok(client.post(f"/grids/{grid}/step-ops", json={"op": "add", "step": step}, headers=AGENT))
        card = _ok(
            client.post("/cards", json={"kind": "note", "title": "Made-up", "body": "x"}, headers=AGENT)
        )
        model = {
            "relationships": [
                {"from": "orders", "from_columns": ["id"], "to": "customers", "to_columns": ["id"]}
            ]
        }
        _ok(client.post("/relationships", json={"model": model}, headers=AGENT))
        blade = {
            "name": "Bakery DB",
            "kind": "sql",
            "dialect": "sqlite",
            "code": f"import sqlite3\nconn = sqlite3.connect({str(db)!r})\n",
        }
        _ok(client.post("/blades", json=blade, headers=AGENT))
        # The user's own action: on the Session page under Me (and Both), not under The agent.
        _ok(client.post(f"/grids/{grid}/step-ops", json={"op": "delete", "index": 0}, headers=AUTH))

        log = _ok(client.get("/session-log", headers=AUTH))
        assert log["who"] == "agent" and log["follow"] is True
        by_action = {e["action"]: e for e in log["entries"]}
        assert all(e["actor"] == "agent" for e in log["entries"])
        assert by_action["open_grid"]["target"]["grid"] == grid
        assert by_action["steps"]["target"] == {"place": "grid", "grid": grid, "dataset": "orders"}
        assert by_action["steps"]["what"] == "Added a filter step to orders"
        assert by_action["add_card"]["target"] == {"place": "card", "card": card["card"]}
        assert by_action["relationships"]["target"]["relationships"] == ["orders.id -> customers.id"]
        assert by_action["save_blade"]["target"] == {"place": "connection", "name": "Bakery DB"}
        # Newest first, each with a number and a time.
        ids = [e["id"] for e in log["entries"]]
        assert ids == sorted(ids, reverse=True) and all(e["time"] for e in log["entries"])
        mine = _ok(client.get("/session-log?who=user", headers=AUTH))["entries"]
        assert [e["what"] for e in mine if e["action"] == "steps"] == ["Removed a filter step from orders"]
        both = _ok(client.get("/session-log?who=both&limit=3", headers=AUTH))["entries"]
        assert len(both) == 3 and both[0]["actor"] == "user"
        assert client.get("/session-log?who=nobody", headers=AUTH).status_code == 400
        # No value anywhere in it: the filter's value, the pasted cells.
        text = json.dumps(_ok(client.get("/session-log?who=both", headers=AUTH)))
        assert SECRET_VALUE not in text and "Initech" not in text


def test_follow_is_the_users_switch_kept_across_restarts(tmp_path: Path) -> None:
    with make_client(tmp_path) as client:
        assert _ok(client.get("/session-log", headers=AGENT))["follow"] is True  # the agent reads it
        refused = client.put("/session-log/follow", json={"on": False}, headers=AGENT)
        assert refused.status_code == 403 and "user's switch" in refused.text
        assert client.put("/session-log/follow", json={"on": "off"}, headers=AUTH).status_code == 400
        assert _ok(client.put("/session-log/follow", json={"on": False}, headers=AUTH)) == {"follow": False}
        assert _ok(client.get("/session-log", headers=AGENT))["follow"] is False
    with make_client(tmp_path) as client:
        assert _ok(client.get("/session-log", headers=AUTH))["follow"] is False
        # The entries are this session's: a new start begins with none.
        assert _ok(client.get("/session-log?who=both", headers=AUTH))["entries"] == []


def test_the_agent_reads_the_session(live: Live) -> None:  # noqa: F811
    read = command("app_session", who="both", limit=5)
    assert set(read) >= {"entries", "follow", "who"} and read["who"] == "both"
