"""Test app two, the field service app (examples/field_service; 2026-11-22): what its two tests share.

Brightline Field Services (made up) runs work orders: a Streamlit project built the way a user builds one,
through the agent's commands only (the golden rule), against a real server. tests/test_field_service_app.py
builds it step by step and checks every step; tests/e2e/test_field_service_app.py opens the finished folder
(examples/field_service) and plays it in a browser. Here: the agent's hands (Agent), the user answering
Allow (Approver), the text the "agent" writes (the project's own widget, its own endpoints) and the made-up
Depot database. Made-up data only (tests/field_service_data.py).
"""

from __future__ import annotations

import json
import sqlite3
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

from swissarmybench.cli import commands
from tests import field_service_data as data

EXAMPLE = Path(__file__).resolve().parents[1] / "examples" / "field_service"
KEYRING_SECRET = "made-up-depot-pa55-7731"  # the Depot connection's password: the keyring's only
CANVAS = "field_service.canvas.json"
# What a copy of the project carries (the example folder): never the sandbox's rows, a build, an export, a
# made file the app writes again as the project opens, or what is Git-ignored.
NOT_KEPT = (
    "sandbox",
    "sandbox_data.py",
    "sandbox_connections.py",
    "adapter.py",
    "connections.py",
    "builds",
    "exports",
    "__pycache__",
    "stats.json",
    "changes.jsonl",
    "api-shapes",
    "api-discover.json",
    "scaffold.json",
    ".venv",
)


class Agent:
    """The agent's hands: one command of the registry (so one MCP tool) per call, its JSON answer read."""

    def __call__(self, _command: str, **args: Any) -> Any:
        out = commands.execute(_command, args)
        if out.startswith(commands.DATA_NOTE):  # values: inside their <untrusted-data> block
            start = out.index("\n", out.index("<untrusted-data source")) + 1
            out = out[start : out.rindex("\n</untrusted-data>")]
        try:
            return json.loads(out)
        except ValueError:
            return out

    def refused(self, _command: str, **args: Any) -> str:
        """A command that must be refused: the reason, in the server's words."""
        try:
            self(_command, **args)
        except commands.CommandError as error:
            return str(error)
        raise AssertionError(f"{_command} was not refused: {args}")

    def api(self, method: str, path: str, query: dict[str, Any] | None = None, body: Any = None) -> Any:
        """The local sandbox API called as the agent calls it (api call): the whole answer."""
        args: dict[str, Any] = {"method": method, "path": path}
        if query:
            args["query"] = query
        if body is not None:
            args["body"] = body
        return self("api", action="call", args=args)


def ask(port: int, token: str, method: str, path: str, body: Any = None) -> Any:
    """The user at the page: one request with the page's token (never the agent's door)."""
    request = urllib.request.Request(
        f"http://127.0.0.1:{port}{path}",
        data=None if body is None else json.dumps(body).encode(),
        method=method,
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(request, timeout=300) as answer:  # noqa: S310 (127.0.0.1)
            return json.loads(answer.read() or b"null")
    except urllib.error.HTTPError as failed:
        raise AssertionError(f"{failed.code}: {failed.read().decode()}") from None


class Approver:
    """The user answering every Allow the agent's commands wait for, and what each one said. `hold()` stops
    answering for a while (so a test sees a command wait)."""

    def __init__(self, port: int, token: str) -> None:
        self.port, self.token = port, token
        self.asked: list[dict[str, str]] = []
        self._stop = threading.Event()
        self._held = threading.Event()
        self._thread = threading.Thread(target=self._run, daemon=True)

    def start(self) -> Approver:
        self._thread.start()
        return self

    def stop(self) -> None:
        self._stop.set()
        self._thread.join(5)

    def hold(self, held: bool = True) -> None:
        if held:
            self._held.set()
        else:
            self._held.clear()

    def pending(self) -> list[dict[str, str]]:
        found: list[dict[str, str]] = ask(self.port, self.token, "GET", "/agent/approvals")["pending"]
        return found

    def actions(self) -> list[str]:
        return [a["action"] for a in self.asked]

    def _run(self) -> None:
        while not self._stop.is_set():
            if not self._held.is_set():
                try:
                    for one in self.pending():
                        self.asked.append(one)
                        ask(self.port, self.token, "POST", f"/agent/approvals/{one['id']}", {"approve": True})
                except (OSError, AssertionError, ValueError):
                    pass
            self._stop.wait(0.05)


def until(check: Any, seconds: float = 30) -> Any:
    """Wait for `check()` to answer something true (a background write, a process starting)."""
    deadline = time.monotonic() + seconds
    while True:
        found = check()
        if found or time.monotonic() > deadline:
            return found
        time.sleep(0.1)


# ===== the made-up Depot: a real connection (SQLite), its password in the keyring =====


def depot_connection(folder: Path, keyring: bool = True) -> dict[str, Any]:
    """The Depot database (the parts in stock) made in `folder`, and its connection as the form saves it.
    keyring=False: no password at all (the e2e server runs where no keyring is)."""
    database = folder / "depot.sqlite"
    with sqlite3.connect(database) as made_up:
        made_up.execute(
            "CREATE TABLE stock (part_sku TEXT PRIMARY KEY, part_name TEXT, on_hand INTEGER, "
            "reorder_point INTEGER, on_order INTEGER)"
        )
        made_up.executemany(
            "INSERT INTO stock VALUES (?, ?, ?, ?, ?)",
            [
                (sku, name, (at * 7) % 12, 5, 10 if at % 3 == 0 else 0)
                for at, (sku, name, _) in enumerate(data.PARTS)
            ],
        )
    code = (
        "import sqlite3\nfrom pathlib import Path\n\n"
        + ('assert secret("password")\n' if keyring else "")
        + f'path = Path(r"{database}")\n'
        "conn = sqlite3.connect(path)\n"
    )
    return {
        "name": "Depot",
        "kind": "sql",
        "template": "sqlite",
        "dialect": "sqlite",
        "code": code,
        "description": "The parts in stock (made up)",
    } | ({"secrets": {"password": KEYRING_SECRET}} if keyring else {})


LOW_STOCK = sorted(sku for at, (sku, _, _) in enumerate(data.PARTS) if (at * 7) % 12 <= 5)

# ===== what the agent writes: the project's own widget =====

VISIT_CARD = """\
from typing import Literal, TypedDict

import streamlit as st
from sab_canvas import Event, In, Out, Table, key, sample


class Visit(TypedDict):
    work_order_id: int
    technician: str
    note: str


# The work orders (not wired: made-up sample data)
orders: In[Table] = None
# The technicians, to find the picked one's work orders by name (not wired: everyone's)
technicians: In[Table] = None
# The technician whose visits show (wired from a select; All: everyone's)
technician: In[str] = "All"
# Who is looking at the page
viewer: In[str] = "unknown"
heading = "Visits to do"
accent = "#0b6e4f"
# How many visits it lists
max_rows = 8  # 1..50
# Show the ones already done too
show_done = False
# The status a visit to do has
status: Literal["open", "scheduled", "in_progress"] = "scheduled"
id_column = "work_order_id"  # column of orders
# The visit picked, for the other widgets (another page's too)
picked: Out[int] = None
# Fired by Mark done: the visit (work_order_id, technician, note); the Canvas wires what it does
completed: Event[Visit] = None

frame = orders if orders is not None else sample(kind="tickets")
who = technician or "All"
st.markdown(f"<h4 style='color:{accent};margin:0'>{heading}</h4>", unsafe_allow_html=True)
st.caption(f"For {viewer} · technician: {who}")
if "status" in frame.columns and not show_done:
    frame = frame[frame["status"].astype(str) == status]
if who != "All" and technicians is not None and "technician_id" in frame.columns:
    ids = technicians[technicians["name"].astype(str) == who]["technician_id"]
    frame = frame[frame["technician_id"].isin(list(ids))]
frame = frame.head(max_rows)
if id_column not in frame.columns:
    st.warning(f"Pick the visit's id column: {id_column} is not in the table.")
elif frame.empty:
    st.info("No visits to do.")
else:
    visits = [v.item() if hasattr(v, "item") else v for v in frame[id_column]]
    chosen = st.selectbox("Visit", visits, key=key("visit"))
    picked = chosen
    st.dataframe(frame, hide_index=True, use_container_width=True)
    note = st.text_input("Note", key=key("note"))
    if st.button("Mark done", type="primary", key=key("done")):
        completed({"work_order_id": int(chosen), "technician": who, "note": note})
        st.success(f"Visit {chosen} marked done.")
"""

# ===== what the agent writes: the app's own endpoints, after the wizard's =====

OWN_ENDPOINTS = '''

# ===== the app's own endpoints (written by hand, after the wizard's) =====


class VisitDone(TypedDict):
    work_order_id: int
    technician: str
    note: str


@endpoint("POST", "/visits/done")
def visit_done(visit: VisitDone) -> WorkOrdersRow:
    """A visit marked done: its work order's status set to done, its note added to the summary."""
    db = connection("Sandbox")
    key = visit["work_order_id"]
    found = records(db.read("work_orders", filters=[["work_order_id", "=", key]], limit=1))
    if not found:
        raise ApiError(404, f"No work order {key}.")
    change = {"work_order_id": key, "status": "done"}
    if visit["note"]:
        change["summary"] = f"{found[0]['summary']} ({visit['note']})"
    db.write("work_orders", [change], key=["work_order_id"], mode="update")
    return get_work_orders(key)


class LowStock(TypedDict):
    part_sku: str
    part_name: str
    on_hand: int
    reorder_point: int


@endpoint("GET", "/stock/low")
def low_stock() -> list[LowStock]:
    """The parts at or under their reorder point, in Depot's own SQL."""
    return records(
        connection("Depot").query(
            "SELECT part_sku, part_name, on_hand, reorder_point FROM stock "
            "WHERE on_hand <= reorder_point ORDER BY part_sku"
        )
    )
'''

# The wizard's nine patterns as this app uses them: (pattern, table, fields, other).
PATTERNS: tuple[tuple[str, str, dict[str, Any], str], ...] = (
    ("table", "work_orders", {}, ""),
    ("choices", "technicians", {}, ""),
    (
        "search",
        "work_orders",
        {"text": "summary", "filters": ["status", "priority", "region", "opened_on"]},
        "",
    ),
    (
        "summary",
        "work_orders",
        {"group": ["status"], "totals": [{"fn": "sum", "column": "amount"}, {"fn": "count", "column": ""}]},
        "",
    ),
    (
        "summary",
        "work_orders",
        {"group": [], "totals": [{"fn": "sum", "column": "hours"}], "date": "opened_on", "period": "month"},
        "",
    ),
    ("bulk", "parts_used", {}, ""),
    ("action", "work_orders", {"name": "complete", "sets": [{"column": "status", "value": "done"}]}, ""),
    ("versions", "price_lists", {"of": "part_sku"}, ""),
    ("reconcile", "invoices", {}, "work_orders"),
    ("export", "work_orders", {}, ""),
)
# Every endpoint the finished API.py has, in its order.
ENDPOINTS = [
    "GET /work_orders",
    "GET /work_orders/{key}",
    "POST /work_orders",
    "PUT /work_orders/{key}",
    "DELETE /work_orders/{key}",
    "GET /technicians/choices",
    "GET /work_orders/search",
    "GET /work_orders/summary/status",
    "GET /work_orders/summary/month",
    "POST /parts_used/bulk",
    "POST /work_orders/complete",
    "GET /price_lists/{key}/versions",
    "GET /price_lists/{key}/current",
    "POST /price_lists/{key}/versions",
    "GET /reconcile/invoices-work_orders",
    "GET /reconcile/invoices-work_orders/rows",
    "GET /work_orders/export.csv",
    "POST /visits/done",
    "GET /stock/low",
]


def fill_sandbox(agent: Agent, folder: Path) -> dict[str, Any]:
    """The project's sandbox filled as the build fills it (the e2e test fills a copy of the example the same
    way): the project's own source/ files, two of them through an open grid, the Depot's stock read once."""
    source = folder / "source"
    added: dict[str, Any] = {}
    for table, key in (("work_orders", "work_order_id"), ("parts_used", "line_id")):
        added[table] = agent(
            "sandbox",
            action="add",
            args={"from": "file", "path": str(source / f"{table}.csv"), "name": table, "key": key},
        )
    for table in ("invoices", "price_lists"):
        added[table] = agent(
            "sandbox",
            action="add",
            args={"from": "file", "path": str(source / f"{table}.csv"), "name": table},
        )
    for table, key in (("technicians", "technician_id"), ("customers", "customer_id")):
        added[table] = agent("sandbox", action="add", args={"from": "grid", "table": table, "key": key})
    added["stock"] = agent(
        "sandbox",
        action="add",
        args={"from": "connection", "connection": "Depot", "table": "stock", "key": "part_sku"},
    )
    return added
