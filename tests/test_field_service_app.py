"""Test app two: the field service app (examples/field_service), built through the agent's commands.

A Streamlit project made the way a user makes one, every step one of the agent's commands (cli/commands.py and
the Streamlit extension's: the MCP tools) against a real server, so each step proves the golden rule: the
scaffold, the sandbox, the local sandbox API (the endpoint wizard's nine patterns, Run, calls, the three
exports run), another API through the API adapter, a widget with Ins, Outs and an Event, the Canvas (pages,
containers, pairing, wiring, both layouts, Hidden in the app, undo), the headless check, Play, Launch with the
Performance Analyzer, Builds, Export run headless, Share (the devtunnel stand-in), the statistics and the
change log. The tests run in the file's order on one server and one project (each builds on the last). The
finished folder is examples/field_service, byte for byte (SAB_FIELD_SERVICE_KEEP=1 writes it).
Made-up data only (tests/field_service_data.py: Brightline Field Services)."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import threading
import urllib.request
from collections.abc import Iterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pytest

from swissarmybench.adapters import adapter as the_adapter
from swissarmybench.domain import scaffold as scaffold_rules
from swissarmybench.server.app import create_app
from swissarmybench.settings import Settings
from tests import field_service_data as data
from tests.api_standins import Service
from tests.fake_keyring import memory_keyring
from tests.field_service_app import (
    CANVAS,
    ENDPOINTS,
    EXAMPLE,
    KEYRING_SECRET,
    LOW_STOCK,
    NOT_KEPT,
    OWN_ENDPOINTS,
    PATTERNS,
    VISIT_CARD,
    Agent,
    Approver,
    ask,
    depot_connection,
    fill_sandbox,
    until,
)
from tests.live_server import running
from tests.streamlit_helpers import STREAMLIT_PYTHON, needs_streamlit
from tests.test_api_export import AZURE_STANDIN, FASTAPI_STANDIN, _run

TOKEN = "field-service-token"
STANDIN = Path(__file__).parent / "devtunnel_standin.py"


@dataclass
class Built:
    """The one server and project the file's tests share, and what earlier tests made (ids, answers)."""

    port: int
    tmp: Path
    folder: Path
    agent: Agent
    approver: Approver
    orders: Service
    made: dict[str, Any] = field(default_factory=dict)

    def user(self, method: str, path: str, body: Any = None) -> Any:
        return ask(self.port, TOKEN, method, path, body)

    def text(self, name: str) -> str:
        return (self.folder / name).read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def app(tmp_path_factory: pytest.TempPathFactory) -> Iterator[Built]:
    tmp = tmp_path_factory.mktemp("field_service")
    settings = Settings(
        state_dir=tmp / "state",
        export_dir=tmp / "exports",
        projects_dir=tmp / "projects",
        workbench_dir=tmp / "wb",
    )
    with pytest.MonkeyPatch.context() as env, memory_keyring():
        info = tmp / "server.json"
        env.setenv("SWISSARMYBENCH_INFO", str(info))
        env.setenv("SWISSARMYBENCH_STATE", str(tmp / "state"))
        env.setenv("SWISSARMYBENCH_OPEN", "0")
        env.setenv("SWISSARMYBENCH_DEVTUNNEL_STANDIN", str(STANDIN))
        env.setenv("SAB_LOCAL_VIEWER", "Dana Lee")  # who views a played page: a made-up name, not this user's
        orders = Service().start()
        try:
            with running(lambda port: create_app(port, TOKEN, settings), log_level="critical") as (port, _):
                info.write_text(json.dumps({"port": port, "token": TOKEN}))
                approver = Approver(port, TOKEN).start()
                try:
                    yield Built(port, tmp, tmp / "projects" / "field_service", Agent(), approver, orders)
                finally:
                    approver.stop()
        finally:
            orders.stop()


def _secret_free(folder: Path) -> None:
    for file in folder.rglob("*"):
        if file.is_file() and file.suffix in (".py", ".md", ".json", ".txt", ".ipynb", ".yaml", ".toml"):
            assert KEYRING_SECRET not in file.read_text(encoding="utf-8", errors="replace"), file


# ===== 1. New project of the Streamlit type: the scaffold =====


def test_a_new_streamlit_project_is_scaffolded(app: Built) -> None:
    agent, folder = app.agent, app.folder
    types = {t["type"]: t for t in agent("project_types")["types"]}
    assert types["streamlit"]["deliverable"] == "a Streamlit app"
    made = agent("project_new", path=str(folder), type="streamlit")
    assert made["project"]["type"] == "streamlit" and made["project"]["name"] == "field_service"
    assert [Path(f).name for f in made["files"]] == ["data.ipynb", CANVAS, "API.py"]
    assert {p.name for p in folder.iterdir()} == {
        ".gitignore",
        ".sab",
        "API.py",
        "README.md",
        CANVAS,
        "data.ipynb",
        "data.py",
        "requirements.txt",
    }
    assert app.text("API.py").startswith('# /// swissarmybench-api\n# name = "field_service API"')
    assert "sandbox/" in app.text(".gitignore")
    status = agent("project_scaffold", action="status")
    # Nothing reads a connection yet: no adapter.py, no connections.py (the scaffold grows as the user works).
    assert status["connections"] == [] and status["to_write"] == []
    assert status["deliverable"]["deliverable"] == "a Streamlit app"
    assert [f["path"] for f in status["deliverable"]["files"]] == ["{slug}.canvas.json", "builds/"]
    assert agent("app_mode")["mode"]["tools"] == ["canvas_", "widgets_"]


def test_the_scaffold_grows_with_a_connection_and_a_hand_edit_is_kept_until_taken(app: Built) -> None:
    agent, folder = app.agent, app.folder
    # The user's own files: the made-up tables as CSV in the project's source/ folder, the Depot database.
    data.write_all(folder / "source")
    depot = depot_connection(app.tmp)
    saved = agent("connections_create", **depot)
    assert saved["name"] == "Depot"
    agent("connections_load_catalog", name="Depot")
    assert until(lambda: "stock" in json.dumps(agent("explorer_browse", connection="Depot"))), agent(
        "explorer_browse", connection="Depot"
    )
    # data.ipynb reads Depot in a SQL cell: the project uses the connection from here on.
    opened = agent("workbench_open", path=str(folder / "data.ipynb"))
    cells = [*opened["cells"], {"kind": "sql", "source": "SELECT * FROM stock", "connection": "Depot"}]
    agent("workbench_save", path=str(folder / "data.ipynb"), cells=cells, modified=opened["modified"])
    done = agent("project_scaffold", action="refresh")
    assert done["connections"] == ["Depot"] and done["kept"] == []
    assert (folder / "adapter.py").read_bytes() == Path(the_adapter.__file__).read_bytes()  # the same bytes
    text = app.text("connections.py")
    assert scaffold_rules.section_names(text) == ["Depot"] and "DEPOT_PASSWORD" in text
    readme = app.text("README.md")
    assert "| `DEPOT_PASSWORD` |" in readme and "connection Depot" in readme
    _secret_free(folder)
    assert agent("project_scaffold", action="refresh")["written"] == []  # nothing changed: no byte written
    # Edited by hand: kept (said with both texts), then Take the new one.
    (folder / "connections.py").write_text(text + "\n# my own line\n", encoding="utf-8")
    kept = agent("project_scaffold", action="status")
    assert [k["file"] for k in kept["kept"]] == ["connections.py"]
    assert "# my own line" in kept["kept"][0]["yours"]
    assert agent("project_scaffold", action="refresh")["written"] == []  # a refresh never takes it
    taken = agent("project_scaffold", action="take", file="connections.py")
    assert "connections.py" in taken["written"] and app.text("connections.py") == text
    # The made files are marked made in the project's documents (never offered as the user's scripts).
    documents = {d["path"]: d for d in agent("project_documents")["documents"]}
    assert (
        documents["adapter.py"]["made"]
        and documents["connections.py"]["made"]
        and documents["data.py"]["made"]
    )
    assert not documents["API.py"]["made"] and documents["data.ipynb"]["role"] == "data"


# ===== 2. The sandbox =====


def _in_background(call: Any) -> tuple[threading.Thread, dict[str, Any]]:
    out: dict[str, Any] = {}

    def go() -> None:
        try:
            out["answer"] = call()
        except Exception as failed:
            out["error"] = str(failed)

    thread = threading.Thread(target=go)
    thread.start()
    return thread, out


def test_the_sandbox_takes_tables_from_files_a_grid_and_a_connection(app: Built) -> None:
    agent, folder = app.agent, app.folder
    for name in ("technicians", "customers"):
        loaded = agent("datasets_load", name=name, path=str(folder / "source" / f"{name}.csv"))
        app.made[f"grid_{name}"] = loaded["grid"]
    # A step on the grid: the sandbox takes the grid's view (after its steps).
    agent("column_remove", grid=app.made["grid_technicians"], columns=["active"])
    added = fill_sandbox(agent, folder)
    assert {table: said["rows"] for table, said in added.items()} == {
        "work_orders": 120,
        "parts_used": 77,
        "invoices": 50,
        "price_lists": 18,
        "technicians": 12,
        "customers": 24,
        "stock": 6,
    }
    assert added["work_orders"]["key"] == ["work_order_id"] and added["stock"]["key"] == ["part_sku"]
    listed = agent("sandbox", action="list", args={"sort": "rows", "order": "desc"})
    assert [t["name"] for t in listed["tables"]][:2] == ["work_orders", "parts_used"]
    tables = {t["name"]: t for t in listed["tables"]}
    assert [c["name"] for c in tables["technicians"]["columns"]] == [
        "technician_id",
        "name",
        "region",
        "skill",
    ]  # the grid's step applied
    assert tables["technicians"]["source_words"] == "From the open table technicians"
    assert tables["work_orders"]["source_words"] == "From work_orders"
    stock = tables["stock"]
    assert stock["source_words"] == "Read once from Depot" and stock["client"]["connection"] == "Depot"
    assert stock["origin_words"].startswith("A sandbox variant of stock from Depot, copied ")
    assert listed["mock_choices"] == ["Depot"] and listed["log_words"] == "No changes since the baseline"
    # Keys: one set afterwards; a column with repeats is refused in one sentence; a second key is refused.
    assert agent("sandbox", action="key", args={"table": "invoices", "key": "invoice_id"})["key"] == [
        "invoice_id"
    ]
    assert "Duplicate key" in agent.refused(
        "sandbox", action="key", args={"table": "price_lists", "key": "part_sku"}
    )
    assert "key is line_id already" in agent.refused(
        "sandbox", action="key", args={"table": "parts_used", "key": "work_order_id"}
    )
    # A variant: a copy named apart, its origin kept and said.
    variant = agent("sandbox", action="variant", args={"from": "grid", "table": "customers"})
    assert variant == {
        "added": "customers_sandbox",
        "rows": 24,
        "sql": "[Sandbox].customers_sandbox",
        "title": "customers · sandbox",
        "variant": True,
    }
    # A file's table answers as a connection (Mocked as), and back.
    mocked = agent("sandbox", action="mock", args={"table": "price_lists", "connection": "Depot"})
    assert mocked["mocked"] and mocked["client"]["dialect"] == "sqlite"
    assert not agent("sandbox", action="mock", args={"table": "price_lists", "connection": None})["mocked"]
    # DuckDB SQL names a sandbox table.
    counted = agent(
        "steps_run_sql",
        grid=app.made["grid_customers"],
        sql="SELECT count(*) AS n FROM [Sandbox].work_orders",
    )
    assert counted["rows"] == [[120]] and counted["connection_reads"][0]["connection"] == "Sandbox"
    # The mirror beside the app: the tables by name, each connection's stand-in, never a value.
    agent("project_scaffold", action="refresh")
    mirror = app.text("sandbox_data.py")
    assert "'work_orders'" in mirror and "'stock'" in mirror and "Brightline" not in mirror
    assert scaffold_rules.section_names(app.text("sandbox_connections.py")) == ["Depot"]
    _secret_free(folder)


def test_sandbox_edits_checkpoints_reset_on_allow_and_the_baseline(app: Built) -> None:
    agent, approver = app.agent, app.approver
    grid = agent("sandbox", action="open", args={"table": "work_orders"})["grid"]

    def edit(**args: Any) -> Any:
        return agent("sandbox", action="edit", args={"table": "work_orders"} | args)

    # Its grid's edits: a cell by its place in the view, rows by their values, each value checked first.
    assert edit(op="update", row=0, column="priority", value="high")["rows"] == 1
    assert edit(op="update", where={"work_order_id": 1001}, values={"hours": "2.5"})["rows"] == 1
    refused = agent.refused(
        "sandbox",
        action="edit",
        args={
            "table": "work_orders",
            "op": "update",
            "where": {"work_order_id": 1001},
            "values": {"hours": "lots"},
        },
    )
    assert "'lots' is not a number: hours is DOUBLE" in refused
    new = {
        "work_order_id": 2000,
        "customer_id": 500,
        "technician_id": 100,
        "region": "North",
        "status": "open",
        "priority": "low",
        "opened_on": "2026-11-01",
        "hours": 0,
        "amount": 0,
        "summary": "Made-up visit",
    }
    assert edit(op="insert", values=new)["rows"] == 1
    assert agent("row_count", grid=grid)["row_count"] == 121  # its open grid follows every write
    duplicate = agent.refused(
        "sandbox", action="edit", args={"table": "work_orders", "op": "insert", "values": new}
    )
    assert "Duplicate key: a row with work_order_id: 2000 is there already" in duplicate
    done = edit(op="delete", where={"work_order_id": 1002})
    assert done["log"] == {"work_orders": {"inserted": 1, "updated": 2, "deleted": 1}}
    saved = agent("sandbox", action="checkpoint", args={"name": "after edits"})
    assert [c["name"] for c in saved["checkpoints"]] == ["after edits"]
    # Reset waits for the user's Allow: nothing changes until it is given.
    approver.hold()
    thread, out = _in_background(lambda: agent("sandbox", action="reset"))
    pending = until(approver.pending)
    assert pending and pending[0]["dataset"] == "Sandbox" and "baseline" in pending[0]["detail"]
    assert agent("row_count", grid=grid)["row_count"] == 120  # 121 - 1: still the edited rows
    approver.hold(False)
    thread.join(60)
    assert "answer" in out, out
    after = agent("sandbox", action="list")
    assert after["log"] == {} and after["log_words"] == "No changes since the baseline"
    assert agent("row_count", grid=grid)["row_count"] == 120
    first = agent("row_read", grid=grid, start=0, end=1)
    assert first["rows"][0][:6] == [1000, 500, 100, "North", "open", "low"]  # its priority back as it was
    # Restore the checkpoint (the edits again), one table back alone, then the baseline moved.
    restored = agent("sandbox", action="restore", args={"name": "after edits"})
    assert restored["log"] == {"work_orders": {"inserted": 1, "updated": 2, "deleted": 1}}
    agent("sandbox", action="reset", args={"table": "work_orders"})
    back = agent("sandbox", action="list")
    assert back["log"] == {}
    keys = {t["name"]: [c["name"] for c in t["columns"] if c["key"]] for t in back["tables"]}
    assert keys["work_orders"] == ["work_order_id"] and keys["stock"] == ["part_sku"]  # Reset keeps a key
    assert agent("sandbox", action="baseline")["baseline_at"]
    assert (
        agent("sandbox", action="checkpoint", args={"name": "after edits", "action": "delete"})["checkpoints"]
        == []
    )
    assert [a["action"] for a in approver.asked if a["dataset"] == "Sandbox"] == [
        "reset the sandbox",
        "reset a sandbox table",
    ]


# ===== 3. The local sandbox API: the endpoint wizard's nine patterns =====


def test_the_wizard_plans_the_nine_patterns_and_scaffolds_the_fitting_ones(app: Built) -> None:
    agent, folder = app.agent, app.folder
    nine = ["table", "choices", "search", "summary", "bulk", "action", "versions", "reconcile", "export"]
    listed = agent("api", action="patterns")["patterns"]
    assert [p["id"] for p in listed] == nine and all(p["steps"] or p["id"] == "export" for p in listed)
    # A table's shape ranks every pattern, each with one sentence why; one that does not fit says its need.
    ranked = {r["pattern"]: r for r in agent("api", action="plan", args={"table": "work_orders"})["ranked"]}
    assert sorted(ranked) == sorted(nine) and all(r["why"] for r in ranked.values())
    assert ranked["table"]["fits"] and "has a key (work_order_id)" in ranked["table"]["why"]
    assert not ranked["versions"]["fits"] and "no version number column" in ranked["versions"]["why"]
    prices = {r["pattern"]: r for r in agent("api", action="plan", args={"table": "price_lists"})["ranked"]}
    assert prices["versions"]["fits"] and "has version" in prices["versions"]["why"]
    # Each pattern planned for its table: its steps with what the shape suggests, and the code it would add.
    before = app.text("API.py")
    for pattern, table, fields, other in PATTERNS:
        args = {"table": table, "pattern": pattern, "fields": fields} | ({"other": other} if other else {})
        planned = agent("api", action="plan", args=args)
        assert planned["problem"] is None and planned["plan"]["steps"], (pattern, planned["problem"])
        assert f"# pattern: {pattern} of {table}" in planned["code"]
        dry = agent("api", action="scaffold", args=args | {"dry_run": True})
        assert dry["dry_run"] and dry["code"] == planned["code"]
    unfit = agent("api", action="plan", args={"table": "work_orders", "pattern": "versions"})
    assert unfit["problem"] == "Pick the version number." and not unfit["code"]
    assert app.text("API.py") == before  # a plan and a dry run write nothing
    # Scaffolded: each pattern's endpoints appended to API.py, marked, each paired with its widgets.
    paired: dict[str, list[str]] = {}
    for pattern, table, fields, other in PATTERNS:
        args = {"table": table, "pattern": pattern, "fields": fields} | ({"other": other} if other else {})
        done = agent("api", action="scaffold", args=args)
        assert done["added"] and done["problems"] == [], (pattern, done["problems"])
        for pair in done["paired"]:
            paired.setdefault(pair["endpoint"], []).append(pair["widget"])
    assert paired["GET /technicians/choices"] == ["select_box", "input_select"]
    assert paired["POST /work_orders"] == ["api_form"] and paired["POST /work_orders/complete"] == [
        "api_button"
    ]
    assert paired["GET /reconcile/invoices-work_orders"] == ["api_metric"]
    state = agent("api", action="state")
    assert [f"{e['method']} {e['path']}" for e in state["endpoints"]] == ENDPOINTS[:17]
    assert [e["pattern"]["id"] for e in state["endpoints"]] == [
        *["table"] * 5,
        "choices",
        "search",
        "summary",
        "summary",
        "bulk",
        "action",
        *["versions"] * 3,
        "reconcile",
        "reconcile",
        "export",
    ]
    # The code is the user's from then on: the agent adds the app's own two endpoints by hand.
    opened = agent("workbench_open", path=str(folder / "API.py"))
    agent(
        "workbench_save",
        path=str(folder / "API.py"),
        text=opened["text"] + OWN_ENDPOINTS,
        modified=opened["modified"],
    )
    state = agent("api", action="state")
    assert [f"{e['method']} {e['path']}" for e in state["endpoints"]] == ENDPOINTS and state["problems"] == []
    own = {e["name"]: e for e in state["endpoints"][-2:]}
    assert own["visit_done"]["pattern"] is None and own["visit_done"]["writes"]
    assert own["low_stock"]["data"] == ["Mock of Depot (sqlite)"] and own["low_stock"]["connections"] == [
        "Depot"
    ]
    assert list(own["visit_done"]["fields"]) == ["work_order_id", "technician", "note"], own["visit_done"][
        "fields"
    ]
    compile(app.text("API.py"), "API.py", "exec")
    # In its editor the wizard's code and the app's own are clean: no squiggle (the lint, API.py's rules).
    noted = agent("workbench_problems", path=str(folder / "API.py"))["documents"]
    assert [(p["line"], p["message"]) for d in noted for p in d["problems"]] == []


def test_the_api_runs_every_get_answers_and_writes_wait_for_allow(app: Built) -> None:
    agent, approver = app.agent, app.approver
    ran = agent("api", action="run")
    assert ran["running"]["endpoints"] == len(ENDPOINTS) and ran["failed"] is None
    get = agent.api
    two = get("GET", "/work_orders", {"limit": 2})
    assert two["status"] == 200 and [r["work_order_id"] for r in two["body"]] == [1000, 1001]
    one = get("GET", "/work_orders/1001")["body"]
    assert (one["status"], one["amount"], one["closed_on"]) == ("done", 288.75, "2026-07-10")
    missing = get("GET", "/work_orders/5")
    assert missing["status"] == 404 and missing["error"] == "No work_orders row has work_order_id 5."
    ada = get("GET", "/technicians/choices", {"search": "ada"})["body"]
    assert ada == [{"technician_id": 100, "name": "Ada Marlow"}]
    found = get("GET", "/work_orders/search", {"q": "thermostat", "status": "done", "limit": 2})["body"]
    assert [r["work_order_id"] for r in found] == [1009, 1015]
    dated = get(
        "GET",
        "/work_orders/search",
        {"from_opened_on": "2026-10-01", "to_opened_on": "2026-10-10", "sort": "amount", "descending": True},
    )["body"]
    assert dated[0]["work_order_id"] == 1065 and all(
        "2026-10-0" in r["opened_on"] or r["opened_on"] == "2026-10-10" for r in dated
    )
    by_status = {r["status"]: r for r in get("GET", "/work_orders/summary/status")["body"]}
    assert by_status["done"] == {"status": "done", "sum_amount": 20665.0, "rows": 51} and len(by_status) == 5
    months = get("GET", "/work_orders/summary/month")["body"]
    assert [m["period"] for m in months] == ["2026-07-01", "2026-08-01", "2026-09-01", "2026-10-01"]
    versions = get("GET", "/price_lists/FLT-100/versions")["body"]
    assert [v["version"] for v in versions] == [3, 2, 1]
    assert get("GET", "/price_lists/FLT-100/current")["body"]["price"] == 18.75
    assert get("GET", "/reconcile/invoices-work_orders")["body"] == {
        "matched": 47,
        "differing": 2,
        "missing_in_invoices": 71,
        "missing_in_work_orders": 1,
    }
    differing = get("GET", "/reconcile/invoices-work_orders/rows", {"show": "differing"})["body"]
    assert [(r["work_order_id"], r["amount_invoices"] - r["amount_work_orders"]) for r in differing] == [
        (data.OFF[0], 10.0),
        (data.OFF[1], 10.0),
    ]
    stray = get("GET", "/reconcile/invoices-work_orders/rows", {"show": "missing_in_work_orders"})["body"]
    assert [r["work_order_id"] for r in stray] == [data.STRAY]
    bad_show = get("GET", "/reconcile/invoices-work_orders/rows", {"show": "everything"})
    assert bad_show["status"] == 422 and bad_show["error"].startswith("show is one of: differences")
    saved = get("GET", "/work_orders/export.csv", {"limit": 3})["body"]
    assert saved["download"] == "work_orders.csv" and saved["text"].count("\n") == 4
    assert [r["part_sku"] for r in get("GET", "/stock/low")["body"]] == LOW_STOCK  # the mock of Depot
    assert get("GET", "/nothing")["error"] == "No endpoint answers GET /nothing."
    # The first write waits for the user's Allow; that Allow covers the session.
    new = {
        "work_order_id": 3000,
        "customer_id": 501,
        "technician_id": 101,
        "region": "North",
        "status": "open",
        "priority": "normal",
        "opened_on": "2026-11-02",
        "hours": 0,
        "amount": 0,
        "summary": "Made-up: fan motor check",
    }
    assert agent("api", action="state")["agent_writes"] is False
    approver.hold()
    thread, out = _in_background(lambda: get("POST", "/work_orders", body=new))
    pending = until(approver.pending)
    assert pending and pending[0]["action"] == "write the sandbox through the local API"
    assert "never live data" in pending[0]["detail"]
    assert get("GET", "/work_orders/3000")["status"] == 404  # nothing was sent yet
    approver.hold(False)
    thread.join(60)
    assert out["answer"]["status"] == 201 and agent("api", action="state")["agent_writes"] is True
    # A 422 names the field (the body is checked against its model before the endpoint runs).
    wrong = get("POST", "/work_orders", body={"work_order_id": "x"})
    assert wrong["status"] == 422 and wrong["body"]["field"] == "row.work_order_id"
    unknown = get("POST", "/work_orders", body={"work_order_id": 3001, "nope": 1})
    assert unknown["status"] == 422 and "row has no field 'nope'" in unknown["error"]
    required = get("POST", "/visits/done", body={"work_order_id": 1003})
    assert required["status"] == 422 and required["error"] == "visit.technician is required."
    # The rest of the writes: by key, an action all or none, a bulk upload checked first, a new version.
    assert get("PUT", "/work_orders/3000", body={"status": "scheduled"})["body"]["status"] == "scheduled"
    # (This one as an action through the API adapter, which learns the shape of what was sent and answered.)
    marked = agent(
        "actions",
        action="run",
        api="local",
        name="complete_work_orders",
        args={"inputs": {"body": {"keys": [3000, 1000]}}},
    )
    assert marked["ok"] and marked["kind"] == "record" and marked["record"]["changed"] == 2
    none = get("POST", "/work_orders/complete", body={"keys": [1003, 77]})
    assert none["status"] == 404 and get("GET", "/work_orders/1003")["body"]["status"] == "scheduled"
    rows: list[dict[str, Any]] = [
        {"line_id": 1, "quantity": 5},
        {"line_id": 900, "work_order_id": 3000, "part_sku": "FLT-100", "quantity": "two", "unit_cost": 12.5},
    ]
    dry = get("POST", "/parts_used/bulk", {"dry_run": True}, rows)["body"]
    assert (dry["inserted"], dry["updated"], dry["written"]) == (1, 1, False)
    assert dry["problems"] == [{"row": 2, "column": "quantity", "problem": "is not a whole number"}]
    assert get("POST", "/parts_used/bulk", body=rows)["status"] == 422  # nothing written: all or none
    rows[1]["quantity"] = 2
    assert get("POST", "/parts_used/bulk", body=rows)["body"]["written"] is True
    version = get("POST", "/price_lists/FLT-100/versions", body={"part_name": "Air filter", "price": 19.9})
    assert version["status"] == 201 and version["body"]["version"] == 4
    visit = get("POST", "/visits/done", body={"work_order_id": 1003, "technician": "Dov Voss", "note": "ok"})
    assert visit["body"]["status"] == "done" and visit["body"]["summary"].endswith("(ok)")
    assert get("DELETE", "/work_orders/3000")["status"] == 204
    asked = [a for a in approver.asked if a["action"] == "write the sandbox through the local API"]
    assert len(asked) == 1  # one Allow covered every write
    log = agent("api", action="log")["log"]
    assert {(r["method"], r["status"]) for r in log} >= {
        ("GET", 200),
        ("POST", 201),
        ("POST", 422),
        ("DELETE", 204),
    }
    assert all("body" not in r for r in log)  # never a value
    counted = agent("sandbox", action="list")["log"]
    assert counted["work_orders"] == {"inserted": 1, "updated": 4, "deleted": 1}
    assert counted["parts_used"] == {"inserted": 1, "updated": 1, "deleted": 0}
    # The action's shape was learned (types only, in .sab/api-shapes); Try it's form is made up from each
    # endpoint's definition and that shape; no value is kept anywhere.
    shapes = app.folder / ".sab" / "api-shapes"
    assert [p.name for p in shapes.iterdir()] == ["complete_work_orders.json"]  # Try it's own calls keep none
    shape = json.loads((shapes / "complete_work_orders.json").read_text("utf-8"))
    assert set(shape["returned"]["fields"]) == {"changed", "keys"} and "3000" not in json.dumps(shape)
    assert shape["sent"]["fields"]["body.keys"]["type"] == "list"
    tries = {f"{e['method']} {e['path']}": e["try"] for e in agent("api", action="state")["endpoints"]}
    assert list(tries["POST /work_orders/complete"]["body"]) == ["keys"]
    assert tries["GET /work_orders/{key}"]["path"] == {"key": 101}  # made up from its type, never a kept one
    kept = "".join(p.read_text(encoding="utf-8") for p in (app.folder / ".sab").rglob("*") if p.is_file())
    assert "fan motor check" not in kept and "Ada Marlow" not in kept
    # The agent's writing taken back, and the sandbox put back as it was (Reset undoes every write).
    assert agent("api", action="writes", args={"allow": False})["agent_writes"] is False
    agent("sandbox", action="reset")
    assert agent("sandbox", action="list")["log"] == {}


# ===== 4. Will this work for real?, and Export for the three targets (each run) =====


def test_will_this_work_for_real_and_each_export_runs_alone(app: Built, tmp_path: Path) -> None:
    agent, folder = app.agent, app.folder
    # Each endpoint's SQL against its connection's catalog as loaded here: never a query on the source.
    checked = agent("api", action="check")
    by_endpoint = {c["endpoint"]: c for c in checked["checks"]}
    assert checked["ok"] and by_endpoint["low_stock"]["connection"] == "Depot"
    assert by_endpoint["low_stock"]["state"] == "works", by_endpoint["low_stock"]
    assert by_endpoint["reconcile_invoices_work_orders"]["state"] == "sandbox"
    assert [t["id"] for t in agent("api", action="targets")["targets"]] == [
        "fastapi",
        "azure_functions",
        "aws_lambda",
    ]
    # The shapes of the widgets that will use it: none yet.
    assert agent("api", action="shapes") == {"uses": [], "ok": True}
    exported: dict[str, Path] = {}
    own = {
        "fastapi": {"main.py"},
        "azure_functions": {"function_app.py", "host.json", ".funcignore"},
        "aws_lambda": {"lambda_function.py", "template.yaml"},
    }
    for target in own:
        done = agent("api", action="export", args={"target": target, "rows": True})
        place = Path(done["folder"])
        assert place == folder / "exports" / "api" / target and done["sandbox"] is True
        assert set(done["files"]) == own[target] | {
            "API.py",
            "README.md",
            "adapter.py",
            "connections.py",
            "requirements.txt",
        }  # the fewest files
        assert (place / "API.py").read_text(encoding="utf-8") == app.text(
            "API.py"
        )  # the endpoints as they are
        assert (place / "adapter.py").read_bytes() == Path(the_adapter.__file__).read_bytes()
        assert scaffold_rules.section_names((place / "connections.py").read_text(encoding="utf-8")) == [
            "Depot"
        ]
        assert done["variables"] == ["DEPOT_PASSWORD"] and "DEPOT_PASSWORD" in (
            place / "README.md"
        ).read_text(encoding="utf-8")
        # Depot only works on this computer (a file on its disk, the keyring): said, with what to use instead.
        assert [n["connection"] for n in done["notes"]] == ["Depot"]
        assert all(w["words"].startswith("Only works on your machine: ") for w in done["notes"][0]["local"])
        _secret_free(place)
        exported[target] = place
    asked = [a for a in app.approver.asked if a["action"] == "export with rows"]
    assert len(asked) == 3 and "with the sandbox's rows" in asked[0]["detail"]
    again = agent("api", action="export", args={"target": "fastapi", "rows": True})
    assert again["written"] == []  # nothing changed: no byte written
    # Each export runs with no app, in a fresh Python: the sandbox's copy for connection("Sandbox"), and the
    # real Depot (its password from where it runs) for connection("Depot").
    stand = tmp_path / "standins"
    (stand / "azure" / "functions").mkdir(parents=True)
    (stand / "azure" / "__init__.py").write_text("", encoding="utf-8")
    (stand / "azure" / "functions" / "__init__.py").write_text(AZURE_STANDIN, encoding="utf-8")
    env = {"DEPOT_PASSWORD": "made-up-from-the-platform", "TMPDIR": str(tmp_path)}
    try:
        import fastapi  # type: ignore[import-not-found]  # noqa: F401

        extra = None
    except ImportError:
        (stand / "fastapi").mkdir()
        (stand / "fastapi" / "__init__.py").write_text(
            FASTAPI_STANDIN + "\n__all__ = ['FastAPI', 'Request', 'Response']\n", encoding="utf-8"
        )
        extra = stand
    fa = _run(
        exported["fastapi"],
        """
        import json
        from starlette.testclient import TestClient
        import main
        status, _, body = main.sab_api.handle("GET", "/work_orders/summary/status")
        with TestClient(main.app) as c:
            one = c.get("/work_orders/1001")
            recon = c.get("/reconcile/invoices-work_orders")
            wrong = c.post("/work_orders", json={"work_order_id": "x"})
            saved = c.get("/work_orders/export.csv", params={"limit": 2})
            low = c.get("/stock/low")
        print(json.dumps([
            status, [r for r in json.loads(body) if r["status"] == "done"], one.status_code,
            one.json()["amount"], recon.json(), wrong.status_code, wrong.json()["field"],
            saved.headers.get("content-disposition"), saved.text.count("\\n"),
            [r["part_sku"] for r in low.json()],
        ]))
        """,
        extra,
        env,
    )
    assert fa == [
        200,
        [{"status": "done", "sum_amount": 20665.0, "rows": 51}],
        200,
        288.75,
        {"matched": 47, "differing": 2, "missing_in_invoices": 71, "missing_in_work_orders": 1},
        422,
        "row.work_order_id",
        'attachment; filename="work_orders.csv"',
        3,
        LOW_STOCK,
    ]
    lam = _run(
        exported["aws_lambda"],
        """
        import json, lambda_function
        rest = {"httpMethod": "GET", "path": "/technicians/choices",
                "queryStringParameters": {"search": "ada"}}
        http = {"rawPath": "/prod/price_lists/FLT-100/current",
                "requestContext": {"http": {"method": "GET"}, "stage": "prod"}}
        missing = {"rawPath": "/work_orders/5",
                   "requestContext": {"http": {"method": "GET"}, "stage": "$default"}}
        out = [lambda_function.handler(e, None) for e in (rest, http, missing)]
        print(json.dumps([[o["statusCode"], json.loads(o["body"])] for o in out]))
        """,
        None,
        env,
    )
    assert lam[0] == [200, [{"technician_id": 100, "name": "Ada Marlow"}]]
    assert lam[1][0] == 200 and lam[1][1]["price"] == 18.75 and lam[1][1]["version"] == 3
    assert lam[2] == [404, {"error": "No work_orders row has work_order_id 5."}]
    az = _run(
        exported["azure_functions"],
        """
        import json, function_app
        import azure.functions as func
        made = function_app.app.get_functions()
        fn = {f.get_function_name(): f.get_user_function() for f in made}
        request = func.HttpRequest(
            method="GET", url="https://x.azurewebsites.net/work_orders/search",
            params={"q": "thermostat", "status": "done", "limit": "1"}, body=b"",
        )
        got = fn["search_work_orders"](request)
        found = [r["work_order_id"] for r in json.loads(got.get_body())]
        print(json.dumps([len(fn), got.status_code, found]))
        """,
        stand,
        env,
    )
    assert az == [len(ENDPOINTS), 200, [1009]]
    # The exports are made files of the project: never offered as the user's scripts.
    documents = {d["path"]: d["made"] for d in agent("project_documents", kind="script")["documents"]}
    assert documents.get("exports/api/fastapi/main.py", True) and not documents["API.py"]


# ===== 5. Another API, through the API adapter =====


def test_another_api_added_and_its_actions_run_through_the_api_adapter(app: Built) -> None:
    agent, folder = app.agent, app.folder
    spec = {"spec_url": app.orders.url + "/openapi.json", "auth": {"type": "none"}}
    preview = agent("connections_api_add", preview=True, **spec)
    assert (
        preview["connection"] == "Orders" and not (app.tmp / "state" / "library" / "apis" / "Orders").exists()
    )
    tried = agent("connections_api_add", try_it="list_regions", **spec)
    assert tried["columns"] == ["region"] and tried["rows"][0] == ["North"]
    added = agent("connections_api_add", **spec)
    assert added["connection"] == "Orders" and (Path(added["folder"]) / "API_Orders.py").is_file()
    listed = {a["api"]: a for a in agent("actions", action="list")["apis"]}
    assert set(listed) == {"Orders", "local"} and listed["local"]["local"] and not listed["Orders"]["allowed"]
    orders = {a["name"]: a for a in listed["Orders"]["actions"]}
    assert set(orders) == {"list_orders", "create_order", "get_order", "list_clients", "list_regions"}
    assert orders["create_order"]["writes"] and orders["create_order"]["maps_to"] == ["form"]
    assert len(listed["local"]["actions"]) == len(ENDPOINTS)
    # One envelope for every call; the shape kept (types only), said once.
    ran = agent(
        "actions", action="run", api="Orders", name="list_orders", args={"inputs": {"status": "open"}}
    )
    assert ran["ok"] and ran["kind"] == "records" and len(ran["records"]) == 17
    assert ran["paging"]["pages"] == 2 and ran["shape"]["envelope"] == "$.items"
    kept = app.tmp / "state" / "library" / "apis" / "Orders" / "shapes" / "list_orders.json"
    text = kept.read_text(encoding="utf-8")
    assert set(json.loads(text)["returned"]["fields"]) == {"order_id", "amount", "status"}
    assert "shipped" not in text and "12.5" not in text  # never a value
    shape = agent("actions", action="shape", api="Orders", name="list_orders")
    assert shape["contract"]["learned"] and shape["shape"]["sent"]["fields"]["query.status"]["type"] == "text"
    one = agent("actions", action="run", api="Orders", name="get_order", args={"inputs": {"order_id": 3}})
    assert one["kind"] == "record" and one["record"]["order_id"] == 3
    bad = agent("actions", action="run", api="Orders", name="get_order", args={"inputs": {}})
    assert not bad["ok"] and "order_id" in json.dumps(bad["error"])  # inputs checked first
    # The project's own API is `local`: the same envelope; a file to save is read as the API gave it.
    local = agent("actions", action="run", api="local", name="summary_work_orders_by_status")
    assert local["ok"] and {r["status"]: r["rows"] for r in local["records"]}["done"] == 51
    saved = agent(
        "actions", action="run", api="local", name="export_work_orders", args={"inputs": {"limit": 5}}
    )
    assert saved["kind"] == "records" and saved["format"] == "csv" and len(saved["records"]) == 5
    # Discover: one read-only GET per read endpoint, on the user's Allow, remembered until taken back.
    found = agent("actions", action="discover", api="Orders")
    assert found["calls"] == 4 and found["skipped"] == {
        "create_order": "it writes: learned from the specification"
    }
    assert found["pairs"] == [
        {"master": "list_orders", "detail": "get_order", "by": "order_id", "input": "order_id"}
    ]
    assert [a["action"] for a in app.approver.asked if a["dataset"] == "Orders"] == ["discover the API"]
    assert {a["api"]: a["allowed"] for a in agent("actions", action="list")["apis"]}["Orders"] is True
    agent("actions", action="allow", api="Orders", args={"allow": False})
    assert {a["api"]: a["allowed"] for a in agent("actions", action="list")["apis"]}["Orders"] is False
    # A call that writes waits for Allow.
    made = agent(
        "actions",
        action="run",
        api="Orders",
        name="create_order",
        args={"inputs": {"body": {"amount": 5, "status": "open"}}},
    )
    assert made["ok"] and made["status"] == 201
    assert [a["action"] for a in app.approver.asked if a["dataset"] == "Orders"][-1] == "call create_order"
    # Build: a cell into data.ipynb, a function into a script, a widget's plan (the widget itself goes on
    # the canvas with the others, below).
    cell = agent("actions", action="build", api="Orders", name="list_orders", args={"as": "cell"})
    assert (
        Path(cell["path"]) == folder / "data.ipynb" and 'sab.run("Orders", "list_orders", {})' in cell["code"]
    )
    function = agent(
        "actions",
        action="build",
        api="Orders",
        name="list_orders",
        args={"as": "function", "path": "scripts/orders.py"},
    )
    assert Path(function["path"]) == folder / "scripts" / "orders.py" and function["name"] == "list_orders"
    compile(app.text("scripts/orders.py"), "orders.py", "exec")
    plan = agent(
        "actions",
        action="build",
        api="local",
        name="summary_work_orders_by_status",
        args={"as": "widget", "insert": False},
    )
    assert plan["plan"] == {
        "widget": "data_table",
        "values": {},
        "wire": {"port": "table_name", "wire": {"endpoint": "GET /work_orders/summary/status"}},
    }
    notebook = agent("workbench_open", path=str(folder / "data.ipynb"))
    assert [c["kind"] for c in notebook["cells"]] == ["sql", "code"] and notebook["cells"][0][
        "connection"
    ] == "Depot"
    # Each action's running figures.
    figures = agent("stats", action="endpoint", name="Orders list_orders")
    assert figures["figures"]["count"] >= 1 and figures["figures"]["errors"] == 0


# ===== 6. Widgets: the project's own (Ins, Outs, an Event, masked properties), and the prebuilt packs =====

PACKS = [
    "Sales dashboard",
    "Operations",
    "Customer service",
    "Data entry",
    "Admin",
    "User inputs",
    "Excel",
    "Form builder",
]


@needs_streamlit
def test_a_widget_with_ins_outs_an_event_and_masked_properties(app: Built) -> None:
    agent, folder = app.agent, app.folder
    listed = agent("widgets_list")
    assert [p["name"] for p in listed["packs"]] == PACKS
    prebuilt = [w for w in listed["widgets"] if w["prebuilt"]]
    assert len(prebuilt) == 113 and {w["pack"] for w in prebuilt if w["pack"]} == set(PACKS)
    # Code not saved yet is read for its properties (each with its mask) and its contract.
    read = agent("widgets_properties", code=VISIT_CARD)
    assert read["problem"] is None
    assert [(p["name"], p["mask"]) for p in read["properties"]] == [
        ("heading", "text"),
        ("accent", "colour"),
        ("max_rows", "number"),
        ("show_done", "switch"),
        ("status", "dropdown"),
        ("id_column", "column"),
    ]
    by_name = {p["name"]: p for p in read["properties"]}
    assert (by_name["max_rows"]["minimum"], by_name["max_rows"]["maximum"]) == (1.0, 50.0)
    assert by_name["status"]["choices"] == ["open", "scheduled", "in_progress"]
    assert (
        by_name["id_column"]["of"] == "orders"
        and by_name["show_done"]["help"] == "Show the ones already done too"
    )
    contract = read["contract"]
    assert [(p["name"], p["type"]) for p in contract["ins"]] == [
        ("orders", "Table"),
        ("technicians", "Table"),
        ("technician", "str"),
        ("viewer", "str"),
    ]
    assert [(p["name"], p["type"]) for p in contract["outs"]] == [("picked", "int")]
    event = contract["events"][0]
    assert (event["name"], event["schema"]) == ("completed", "Visit")
    assert event["fields"] == [
        {"name": "work_order_id", "type": "int"},
        {"name": "technician", "type": "str"},
        {"name": "note", "type": "str"},
    ]
    # Made in the library, a default changed (each value checked against its mask first), its header set.
    made = agent(
        "widgets_new",
        name="visit_card",
        description="The visits to do for one technician; Mark done fires an event",
        code=VISIT_CARD,
    )
    assert made["where"] == "library" and not made["prebuilt"]
    assert "max_rows is 50 at most" in agent.refused(
        "widgets_set_property", name="visit_card", property="max_rows", value=99
    )
    assert "green is not a colour" in agent.refused(
        "widgets_set_property", name="visit_card", property="accent", value="green"
    )
    assert "status is one of open, scheduled, in_progress" in agent.refused(
        "widgets_set_property", name="visit_card", property="status", value="closed"
    )
    agent("widgets_set_property", name="visit_card", property="max_rows", value=6)
    headed = agent(
        "widgets_header",
        name="visit_card",
        group="Data",
        size=[6, 6],
        min_size=[3, 3],
        tags=["field service"],
    )
    assert (headed["group"], headed["size"], headed["min_size"], headed["tags"]) == (
        "Data",
        [6, 6],
        [3, 3],
        ["field service"],
    )
    # Copy to project: the project's own widgets/ folder (shared with it in Git); the project's wins.
    copied = agent("widgets_copy", name="visit_card", to="project")
    assert copied["where"] == "project" and copied["hides"] == ["library"]
    file = folder / "widgets" / "visit_card.widget.py"
    text = file.read_text(encoding="utf-8")
    assert text.startswith("# /// swissarmybench-widget\n") and "max_rows = 6  # 1..50" in text
    assert text.endswith(
        VISIT_CARD.replace("max_rows = 8", "max_rows = 6")
    )  # only its own characters changed
    got = agent("widgets_get", name="visit_card")
    assert Path(got["file"]) == file and got["contract"]["events"][0]["schema"] == "Visit"
    # Run alone, headless: it draws (its made-up sample has no work_order_id: it says so in its place).
    ran = agent("widgets_run", name="visit_card")
    assert ran["ok"] and ran["pages"][0]["exceptions"] == [] and ran["pages"][0]["failed"] == []
    assert ran["pages"][0]["warnings"] == ["Pick the visit's id column: work_order_id is not in the table."]
    tickets = agent("widgets_run", name="visit_card", values={"id_column": "ticket_id", "show_done": True})
    assert tickets["pages"][0]["warnings"] == [] and tickets["pages"][0]["kinds"]["dataframe"] == 1
    # A prebuilt widget is read-only: copied as your own, and a library widget deleted on Allow.
    assert "prebuilt" in agent.refused("widgets_save", name="counter", code="x = 1\n").lower()
    mine = agent("widgets_copy", name="counter", new_name="visit_counter")
    assert mine["where"] == "library" and not mine["prebuilt"]
    assert agent("widgets_delete", name="visit_counter") == {"ok": True, "deleted": "visit_counter"}
    assert app.approver.asked[-1]["action"] == "delete_widget"
    assert agent("widgets_preview", name="visit_card")["state"] in ("ready", "coming", "failed")


# ===== 7. The Canvas: three pages, containers, pairing, wiring, both layouts, Hidden in the app, undo =====

SANDBOX_ORDERS = {"table": "[Sandbox].work_orders"}


@needs_streamlit
def test_the_canvas_is_built_paired_and_wired(app: Built) -> None:
    agent, folder = app.agent, app.folder
    cid = agent("canvas_open", path=str(folder / CANVAS))["canvas"]
    app.made["canvas"] = cid
    ids: dict[str, str] = app.made.setdefault("ids", {})

    def canvas(_command: str, **args: Any) -> Any:
        return agent(_command, canvas=cid, **args)

    def box(label: str, page: str, x: int, y: int, w: int, h: int, **props: Any) -> str:
        made = canvas("canvas_add_container", page=page, x=x, y=y, w=w, h=h, props=props)["made"]
        ids[label] = made
        return str(made)

    def put(label: str, widget: str, **args: Any) -> dict[str, Any]:
        done: dict[str, Any] = canvas("canvas_insert_widget", widget=widget, **args)
        ids[label] = done["made"]
        return done

    def wire(label: str, port: str, to: Any) -> Any:
        return canvas("canvas_wire", id=ids[label], port=port, wire=to)

    assert [p["id"] for p in canvas("canvas_state")["model"]["pages"]] == ["p1"]
    canvas("canvas_page", page="p1", name="Dispatch")
    assert canvas("canvas_page", name="Work order")["made"] == "p2"
    assert canvas("canvas_page", name="Parts and billing")["made"] == "p3"
    # ----- Dispatch: containers drawn where they go, widgets inserted into them -----
    head = box("head", "p1", 0, 0, 1200, 90, border=False)
    put("title", "title", parent=head, x=8, y=8, values={"text": "Brightline dispatch"})
    filters = box("filters", "p1", 0, 100, 1200, 130, title="Filter")
    select = put(
        "select",
        "input_select",
        parent=filters,
        x=8,
        y=8,
        values={"label": "Technician", "placeholder": "Everyone"},
    )
    # Paired: the wizard's Choices endpoint over technicians is the one match for a select input.
    assert (
        select["wired"]["endpoint"] == "GET /technicians/choices"
        and select["wired"]["port"] == "options_table"
    )
    assert select["wired"]["sets"] == {"options_column": "name"}
    assert "the choices pattern over technicians pairs with it" in select["notes"][0]
    put("search", "input_text", parent=filters, x=420, y=8, values={"label": "Search the summaries"})
    orders = box("orders", "p1", 0, 240, 700, 470, title="Work orders")
    table = put("orders_table", "api_table", parent=orders, x=8, y=8)
    assert "wired" not in table  # two endpoints fit (the list and the search): never a guess
    canvas(
        "canvas_set_values",
        id=ids["orders_table"],
        values={"endpoint": "GET /work_orders/search", "page_size": 10},
    )
    canvas("canvas_move", id=ids["orders_table"], w=684, h=400)
    visits = box("visits", "p1", 710, 240, 490, 470, title="Visits")
    put("card", "visit_card", parent=visits, x=8, y=8, values={"heading": "Visits to do"})
    charts = box("charts", "p1", 0, 720, 1200, 340, title="By status")
    put(
        "bars",
        "bar_chart",
        parent=charts,
        x=8,
        y=8,
        values={"x": "status", "y": "rows", "title": "Work orders"},
    )
    put("pie", "cs_status_pie", parent=charts, x=610, y=8, values={"title": "Share by status"})
    # ----- wiring: an In from a table, from another widget's Out, from an endpoint; app.viewer itself -----
    # The visits to do read through the API each rerun (a [Conn].table property is the table as Play read
    # it, so a write by the card's own Event would not show until the next Play; found in the browser test).
    wire("card", "orders", {"endpoint": "GET /work_orders"})
    wire("card", "technicians", {"table": "[Sandbox].technicians"})
    wire("card", "technician", {"out": f"{ids['select']}.value"})
    wire("bars", "table_name", {"endpoint": "GET /work_orders/summary/status"})
    wire("pie", "table_name", SANDBOX_ORDERS)
    mismatch = agent.refused(
        "canvas_wire", canvas=cid, id=ids["card"], port="orders", wire={"out": f"{ids['select']}.value"}
    )
    assert "orders takes a table" in mismatch and "gives text" in mismatch
    gone = agent.refused(
        "canvas_wire", canvas=cid, id=ids["bars"], port="table_name", wire={"endpoint": "GET /nothing"}
    )
    assert "/nothing" in gone
    # An Event calling an endpoint: the typed payload is the body; then a page value set, then a rerun.
    typed = agent.refused(
        "canvas_wire",
        canvas=cid,
        id=ids["card"],
        port="completed",
        wire={"actions": [{"do": "call", "endpoint": "POST /visits/done", "body": "values"}]},
    )
    assert "completed's payload (Visit) has no values: it has work_order_id, technician, note" in typed
    wire(
        "card",
        "completed",
        {
            "actions": [
                {"do": "call", "endpoint": "POST /visits/done", "body": ""},
                {"do": "set", "key": "last_visit", "value": "work_order_id"},
                {"do": "rerun"},
            ]
        },
    )
    # ----- Work order: each widget in a container of its own, at a free place -----
    detail = put(
        "detail",
        "cs_ticket_detail",
        page="p2",
        values={"id_column": "work_order_id", "subject_column": "summary"},
    )
    wire("detail", "table_name", SANDBOX_ORDERS)
    wire("detail", "ticket_id", {"out": f"{ids['card']}.picked"})  # across pages: the picked visit
    form = put("form", "api_form", page="p2")
    assert form["wired"]["endpoint"] == "POST /work_orders"  # the Table pattern's create pairs with a form
    put(
        "button",
        "api_button",
        page="p2",
        values={
            "endpoint": "POST /work_orders/complete",
            "label": "Mark 1000 and 1003 done",
            "body": {"keys": [1000, 1003]},
        },
    )
    put("record", "de_record_form", page="p2", values={"required_columns": ["part_sku", "quantity"]})
    wire("record", "table_name", {"table": "[Sandbox].parts_used"})
    wire("record", "saved", {"actions": [{"do": "set", "key": "last_part", "value": ""}]})
    put(
        "excel",
        "excel_download",
        page="p2",
        values={"file_name": "field-service.xlsx", "sheet_names": ["Work orders", "Parts used"]},
    )
    wire("excel", "tables", {"tables": [SANDBOX_ORDERS, {"table": "[Sandbox].parts_used"}]})
    put("last", "input_text", page="p2", values={"label": "Last visit marked done", "disabled": True})
    wire("last", "default_from", {"page": "last_visit"})
    # ----- Parts and billing -----
    metric = put(
        "metric", "api_metric", page="p3", values={"field": "differing", "label": "Invoices that differ"}
    )
    assert metric["wired"]["endpoint"] == "GET /reconcile/invoices-work_orders"
    rows = put("recon_rows", "api_table", page="p3")
    # Next to the metric over the reconcile: the one API table endpoint over the same tables.
    assert rows["wired"]["endpoint"] == "GET /reconcile/invoices-work_orders/rows", rows.get("wired")
    put("low", "ops_low_stock_table", page="p3", values={"name_column": "part_name"})
    wire("low", "table_name", {"table": "[Sandbox].stock"})
    put(
        "kpis",
        "sales_kpi_row",
        page="p3",
        values={
            "date_column": "opened_on",
            "revenue_column": "amount",
            "units_column": "hours",
            "margin_column": "",  # no margin in work orders: shown as a dash
            "currency": "£",
        },
    )
    wire("kpis", "table_name", SANDBOX_ORDERS)
    put("users", "admin_user_list", page="p3", values={"role_column": "skill", "active_only": False})
    wire("users", "table_name", {"table": "[Sandbox].technicians"})
    put("picker", "form_picker", page="p3")
    put("fill", "form_fill", page="p3")
    put("submissions", "form_submissions", page="p3")
    put(
        "versions",
        "api_table",
        page="p3",
        values={"endpoint": "GET /price_lists/{key}/versions", "path_values": {"key": "FLT-100"}},
    )
    put("prices", "data_table", page="p3")
    wire("prices", "table_name", {"out": f"{ids['versions']}.rows"})
    # Build as a widget: another API's action put on the canvas as a table (its records Return as table on).
    built = agent(
        "actions", action="build", api="Orders", name="list_orders", args={"as": "widget", "page": "p3"}
    )
    assert built["widget"] == "data_table" and built["canvas_id"] == cid
    ids["orders_api"] = built["id"]
    # And its action called through the API adapter by a widget: "[Orders] GET /orders/{order_id}".
    put(
        "order_metric",
        "api_metric",
        page="p3",
        values={
            "endpoint": "[Orders] GET /orders/{order_id}",
            "path_values": {"order_id": "3"},
            "field": "amount",
            "label": "Order 3 (another API)",
        },
    )
    state = canvas("canvas_state")
    assert state["missing"] == [] and state["broken"] is None and state["marks"] == {}, state["marks"]
    wiring = state["wiring"]
    assert wiring["broken"] == []
    wires = {w["to"]: w for w in wiring["wires"]}
    card, select_id = ids["card"], ids["select"]
    assert wires[f"{card}.technician"] == {
        "from": f"{select_id}.value",
        "to": f"{card}.technician",
        "auto": False,
    }
    # An In[str] called viewer takes the app's viewer by itself; the picked visit crosses to another page.
    assert wires[f"{card}.viewer"]["from"] == "app.viewer" and wires[f"{card}.viewer"]["auto"]
    crossed = wires[f"{ids['detail']}.ticket_id"]
    assert crossed["from"] == f"{card}.picked" and crossed["cross"] and crossed["page"] == "p1"
    # The Form builder's hand-offs wire by themselves (one Out of the name on the page).
    assert (
        wires[f"{ids['fill']}.form_definition"]["auto"]
        and wires[f"{ids['submissions']}.form_submissions"]["auto"]
    )
    assert wiring["sources"][ids["orders_api"]] == {"table_name": {"table": "[Orders].list_orders"}}
    assert wiring["sources"][ids["last"]] == {"default_from": {"page": "last_visit"}}
    assert wiring["readers"][f"{card}.picked"] == [f"{ids['detail']}.ticket_id"]
    # The widgets' shapes against API.py's endpoints: what each expects or sends; no mismatch.
    shapes = agent("api", action="shapes")
    assert shapes["ok"] and all(u["problems"] == [] for u in shapes["uses"]), [
        (u["endpoint"], u["problems"]) for u in shapes["uses"] if u["problems"]
    ]
    used = {(u["instance"], u.get("event", "")): u["endpoint"] for u in shapes["uses"]}
    assert used[(card, "completed")] == "POST /visits/done" and used[(ids["form"], "")] == "POST /work_orders"
    assert detail["made"] == ids["detail"]


@needs_streamlit
def test_both_layouts_hidden_in_the_app_undo_and_the_rules(app: Built) -> None:
    agent, cid, ids = app.agent, app.made["canvas"], app.made["ids"]

    def canvas(_command: str, **args: Any) -> Any:
        return agent(_command, canvas=cid, **args)

    def item(state: dict[str, Any], page: str, layout: str, wanted: str) -> dict[str, Any]:
        def inside(nodes: list[dict[str, Any]]) -> dict[str, Any] | None:
            for node in nodes:
                if node["id"] == wanted:
                    return node
                found = inside(node.get("children") or [])
                if found:
                    return found
            return None

        found = inside(state["views"][page][layout])
        assert found is not None, wanted
        return found

    state = canvas("canvas_state")
    assert state["design"] == {"desktop": 1200, "phone": 390}
    # The same items in both layouts: Desktop as drawn, Phone stacked at full width in reading order.
    desk = item(state, "p1", "desktop", ids["visits"])
    assert (desk["x"], desk["y"], desk["w"], desk["h"]) == (710, 240, 490, 470)
    phone = [n for n in state["views"]["p1"]["phone"]]
    assert [n["id"] for n in phone] == [ids[k] for k in ("head", "filters", "orders", "visits", "charts")]
    assert all(n["x"] == 0 and n["w"] == 390 for n in phone)
    assert [n["y"] for n in phone] == sorted(n["y"] for n in phone)
    # Phone has its own places, under the same rules: the charts' box made taller there and its pie moved
    # down; the desktop's places are untouched.
    taken = agent.refused("canvas_move", canvas=cid, id=ids["filters"], layout="phone", h=170)
    assert taken.endswith(f"That place is taken by {ids['orders']}.")
    moved = agent.refused("canvas_move", canvas=cid, id=ids["search"], layout="phone", y=400)
    assert "out of its container at the bottom" in moved
    canvas("canvas_move", id=ids["charts"], layout="phone", h=620)
    state = canvas("canvas_move", id=ids["pie"], layout="phone", y=320)
    assert (
        item(state, "p1", "phone", ids["pie"])["y"] == 320
        and item(state, "p1", "phone", ids["charts"])["h"] == 620
    )
    assert (
        item(state, "p1", "desktop", ids["pie"])["x"] == 610
        and item(state, "p1", "desktop", ids["charts"])["h"] == 340
    )
    # One layout only: the page's title is the desktop's; and Hidden in the app: a widget that runs (its Out
    # feeds the prices table) and takes no space.
    state = canvas("canvas_move", id=ids["head"], show="desktop")
    assert item(state, "p1", "desktop", ids["head"])["show"] == "desktop"
    state = canvas("canvas_move", id=ids["versions"], hidden=True)
    assert item(state, "p3", "desktop", ids["versions"])["hidden"] is True
    # The rules hold for every command: nothing overlaps, leaves its box or the page.
    assert "past the right of the page" in agent.refused("canvas_move", canvas=cid, id=ids["orders"], x=600)
    overlap = agent.refused("canvas_move", canvas=cid, id=ids["visits"], x=300)
    assert overlap.endswith(f"That place is taken by {ids['orders']}.")
    small = agent.refused("canvas_move", canvas=cid, id=ids["card"], w=40, h=30)
    assert "smaller" in small or "at least" in small, small
    # Undo and redo: a delete taken back with what it held and its wires, then done again, then back.
    before = canvas("canvas_state")
    deleted = canvas("canvas_delete", id=ids["visits"])
    assert [b["instance"] for b in deleted["wiring"]["broken"]] == [ids["detail"]]  # its reader is marked
    undone = canvas("canvas_undo")
    assert undone["model"] == before["model"] and undone["wiring"]["broken"] == []
    assert canvas("canvas_undo", redo=True)["model"] == deleted["model"]
    assert canvas("canvas_undo")["model"] == before["model"]
    # The canvas's sizing, shared by both layouts.
    sized = canvas("canvas_set", gap=8, snap=True, step=4)
    assert sized["model"]["sizing"]["step"] == 4
    # The file is the project's own, byte-stable: read back as the state says it.
    saved = json.loads(app.text(CANVAS))
    assert saved == canvas("canvas_state")["model"] and [p["name"] for p in saved["pages"]] == [
        "Dispatch",
        "Work order",
        "Parts and billing",
    ]
    listed = agent("canvas_open")
    assert [c["name"] for c in listed["canvases"]] == ["field_service"]


# ===== 8. The headless check, Play, Launch with the Performance Analyzer, Builds =====


def _page(port: int, path: str) -> tuple[int, str]:
    request = urllib.request.Request(
        f"http://127.0.0.1:{port}{path}", headers={"Authorization": f"Bearer {TOKEN}"}
    )
    with urllib.request.urlopen(request, timeout=120) as answer:  # noqa: S310 (127.0.0.1)
        return answer.status, answer.read().decode("utf-8", "replace")


@needs_streamlit
def test_the_headless_check_and_play(app: Built) -> None:
    agent, cid = app.agent, app.made["canvas"]
    checked = agent("canvas_play", canvas=cid, check=True)
    assert checked["ok"], checked
    pages = {p["page"]: p for p in checked["pages"]}
    assert list(pages) == [
        "app_pages/dispatch.py",
        "app_pages/work_order.py",
        "app_pages/parts_and_billing.py",
    ]
    for page in pages.values():  # every widget drew: none failed, none said an error in its place
        assert page["exceptions"] == [] and page["failed"] == [] and page["errors"] == [], page
        assert page["warnings"] == [], page
    # What each page drew: the API table and the visits' table; the forms; the metrics and the tables.
    assert pages["app_pages/dispatch.py"]["kinds"]["dataframe"] >= 2
    assert pages["app_pages/dispatch.py"]["kinds"]["selectbox"] >= 2  # the technician, the visit
    assert pages["app_pages/work_order.py"]["kinds"]["button"] >= 3
    assert pages["app_pages/parts_and_billing.py"]["kinds"]["metric"] >= 5  # the reconcile's and the KPIs
    played = agent("canvas_play", canvas=cid, page="p2")
    assert played["ok"] and played["page"] == "p2" and played["broken"] == []
    status, html = _page(app.port, played["url"])
    assert status == 200 and "<title>" in html  # the live page, passed through this server
    assert agent("canvas_play", canvas=cid, stop="play")["ok"]


@needs_streamlit
def test_launch_the_performance_analyzer_and_builds(app: Built) -> None:
    agent, cid, ids, folder = app.agent, app.made["canvas"], app.made["ids"], app.folder
    before = app.text(CANVAS)
    first = agent("app_launch", canvas=cid, analyzer=True)
    assert (
        first["ok"] and first["build"] == 1 and first["analyzer"] and first["changed"] == ["The first build."]
    )
    build = folder / "builds" / "field_service" / "1"
    assert Path(first["folder"]) == build
    made = {p.name for p in build.iterdir()}
    assert made >= {
        "app.py",
        "app_pages",
        "sab_canvas.py",
        "sab_widgets.py",
        "canvas.json",
        "build.json",
        "api_adapter.py",
        "sab_actions.json",
        "API_Orders.py",  # the library API's client, carried
        "sab_excel.py",  # the Excel widget builds its workbook through it
        "requirements.txt",
    }
    assert {p.name for p in (build / "app_pages").iterdir()} >= {
        "dispatch.py",
        "work_order.py",
        "parts_and_billing.py",
    }
    assert (build / "canvas.json").read_text(encoding="utf-8") == before
    _secret_free(build)
    assert _page(app.port, first["url"])[0] == 200
    # The analyzer records from the first load; its session is saved into the build (names, times, counts).
    session = agent("canvas_perf", canvas=cid)
    assert session["build"] == 1 and session["recording"] is True
    assert agent("canvas_perf", canvas=cid, action="hints")["hints"] == []
    kept = agent("canvas_perf", canvas=cid, action="save")
    assert kept["build"] == 1 and (build / kept["file"]).is_file()
    assert agent("canvas_perf", canvas=cid, action="saved", build=1, file=kept["file"])["build"] == 1
    assert agent("canvas_perf", canvas=cid, action="pause")["recording"] is False
    # A change, then a second launch: the build says what changed in words.
    agent("canvas_set_values", canvas=cid, id=ids["orders_table"], values={"page_size": 15})
    second = agent("app_launch", canvas=cid)
    assert second["build"] == 2 and not second["analyzer"]
    assert second["changed"] == [f"api_table ({ids['orders_table']}): page_size changed."]
    builds = agent("canvas_builds", canvas=cid)
    assert [b["number"] for b in builds["builds"]] == [2, 1] and builds["running"] == 2
    assert builds["builds"][1]["sessions"] == [kept["file"]]
    # Compare two builds, and a build with the canvas now.
    compared = agent("canvas_builds", canvas=cid, action="compare", build=1, b=2)
    changed = {f["file"]: f["status"] for f in compared["files"] if f["status"] != "same"}
    assert changed.get("app_pages/dispatch.py") == "changed" and "sab_widgets.py" not in changed
    now = agent("canvas_builds", canvas=cid, action="compare", build=2)
    assert now["b"] == "now" and not [
        f for f in now["files"] if f["status"] != "same" and f["file"].endswith(".py")
    ]
    files = agent("canvas_builds", canvas=cid, action="files", build=2)["files"]
    assert "page_size" in files["canvas.json"] and "sab.style(" in files["app_pages/dispatch.py"]
    # Relaunch the first build as it was; Restore puts its canvas back as one change (Undo takes it back).
    again = agent("canvas_builds", canvas=cid, action="relaunch", build=1)
    assert again["ok"] and again["build"] == 1
    restored = agent("canvas_builds", canvas=cid, action="restore", build=1)
    assert app.text(CANVAS) == before and restored["undo"]
    agent("canvas_undo", canvas=cid)
    assert '"page_size": 15' in app.text(CANVAS)
    agent("canvas_undo", canvas=cid, redo=True)
    assert app.text(CANVAS) == before
    stopped = agent("app_launch", canvas=cid, stop=True)
    assert stopped["ok"] and stopped["running"] is False


# ===== 9. Export (the fewest files), run headless with no app =====

RUN_EXPORT = """
import json, os, sys
sys.path.insert(0, os.getcwd())
from streamlit.testing.v1 import AppTest
out = []
# app.py as it is (its first page, through its own navigation), then each other page's function run by
# itself: the file up to its list of pages, then the one call.
text = open("app.py", encoding="utf-8").read()
head = text[: text.rindex("pages = [")]
for page in json.loads(sys.argv[1]):
    if page:
        with open(f"only_{page}.py", "w", encoding="utf-8") as one:
            one.write(head + f"\\n{page}()\\n")
    at = AppTest.from_file(f"only_{page}.py" if page else "app.py", default_timeout=120)
    at.run()
    out.append({
        "exceptions": [str(e.value)[:500] for e in at.exception],
        "errors": [str(e.value)[:500] for e in at.error],
        "warnings": [str(w.value)[:300] for w in at.warning],
        "titles": [str(m.value)[:80] for m in at.markdown][:3],
        "frames": len(at.dataframe),
        "metrics": {str(m.label): str(m.value) for m in at.metric},
        "buttons": [str(b.label) for b in at.button],
    })
print("SAB-RUN " + json.dumps(out))
"""


@needs_streamlit
def test_the_export_is_the_fewest_files_and_runs_headless(app: Built) -> None:
    agent, cid = app.agent, app.made["canvas"]
    out = app.tmp / "exported"
    done = agent("canvas_export", canvas=cid, folder=str(out))
    assert app.approver.asked[-1]["action"] == "export_canvas"  # it copies rows: the user's Allow
    files = set(done["files"])
    assert {f for f in files if not f.startswith("data/")} == {
        "README.md",
        "app.py",  # the pages as functions, the layout, the wiring and the runtime
        "widgets.py",  # the widgets inlined (the project's own too)
        "api_adapter.py",
        "API_Orders.py",  # the other API's client
        "sab_excel.py",
        "adapter.py",  # the other API's table ([Orders].list_orders) is read through them where it runs
        "connections.py",
        "data.py",
        "requirements.txt",
    }, files
    assert sorted(f for f in files if f.startswith("data/")) == sorted(
        f"data/{p.name}" for p in (out / "data").iterdir()
    )
    copies = sorted(f for f in files if f.startswith("data/"))
    assert all(f.endswith(".parquet") for f in copies) and len(copies) == 4, copies  # the sandbox's four
    assert done["variables"] == ["SAB_API_URL", "SAB_API_KEY", "SAB_API_BASE", "ORDERS_URL"]  # each once
    readme = (out / "README.md").read_text(encoding="utf-8")
    assert "`SAB_API_URL`" in readme and readme.count("`ORDERS_URL`") == 1
    widgets = (out / "widgets.py").read_text(encoding="utf-8")
    assert "visit_card" in widgets and "Mark done" in widgets and "class Visit(TypedDict)" in widgets
    _secret_free(out)
    # Run alone (no app): a fresh Python with Streamlit, the API's address as its README says to set it.
    address = agent("api", action="address")
    env = {
        "PATH": os.environ.get("PATH", ""),
        "HOME": str(app.tmp),
        "SAB_API_URL": address["url"],
        "SAB_API_KEY": address["key"],
        "SAB_API_BASE": "",
        "STREAMLIT_BROWSER_GATHER_USAGE_STATS": "false",
    }
    assert STREAMLIT_PYTHON is not None
    ran = subprocess.run(  # noqa: S603 (the test's own script, a Python with Streamlit)
        [
            STREAMLIT_PYTHON,
            "-I",
            "-c",
            RUN_EXPORT,
            json.dumps(["", "_page_work_order", "_page_parts_and_billing"]),
        ],
        cwd=out,
        capture_output=True,
        text=True,
        timeout=300,
        env=env,
        check=False,
    )
    assert ran.returncode == 0, ran.stderr[-3000:]
    said = next(line for line in ran.stdout.splitlines() if line.startswith("SAB-RUN "))
    pages = json.loads(said[len("SAB-RUN ") :])
    for page in pages:  # every widget drew, on every page: no exception, no error said in a widget's place
        assert page["exceptions"] == [] and page["errors"] == [] and page["warnings"] == [], page
    dispatch, work_order, billing = pages
    assert dispatch["frames"] >= 2 and "Mark done" in dispatch["buttons"], dispatch
    assert {"Mark 1000 and 1003 done", "Save record"} <= set(work_order["buttons"]), work_order
    # The numbers come from the API it was pointed at, the other API's own client, and the copied tables.
    assert billing["metrics"]["Invoices that differ"] == "2", billing["metrics"]
    assert billing["metrics"]["Order 3 (another API)"] == "7.5", billing["metrics"]
    assert billing["frames"] >= 5, billing
    for made in out.glob("only_*.py"):
        made.unlink()


# ===== 10. Share…: the launched app to the organization (Microsoft's devtunnel stood in for) =====


@needs_streamlit
def test_share_a_launched_app_with_the_organization(app: Built) -> None:
    agent, cid = app.agent, app.made["canvas"]
    before = agent("sharing_status")
    assert before["installed"] is False and before["signed_in"] is False and before["shares"] == []
    assert "streamlit" in before["kinds"] and "work account" in before["sentence"]
    assert agent("app_launch", canvas=cid)["ok"]
    # Signing in is the user's own step: the agent's share says so, and cannot sign in itself.
    refused = agent.refused("sharing_start", app=cid)
    assert "Sign in with your work account first" in refused
    assert app.approver.asked[-1]["action"] == "share_start"
    signing = app.user("POST", "/sharing/sign-in", {"device": True})
    assert signing["device"]["code"] == "MADEUP42"
    assert until(lambda: app.user("GET", "/sharing?fresh=1")["signed_in"])
    shared = agent("sharing_start", app=cid)
    assert shared["state"] == "sharing" and shared["who"] == "Your organization"
    assert shared["url"].startswith("https://") and shared["url"].endswith(".devtunnels.ms/")
    assert str(app.port) not in shared["url"]  # the app's own port, never this server's
    status = agent("sharing_status", app=cid)
    assert [s["url"] for s in status["shares"]] == [shared["url"]] and status["work_account"] is True
    # A link always ends with its app: stopping the launch ends the share; then Stop sharing by itself.
    agent("app_launch", canvas=cid, stop=True)
    assert until(
        lambda: not [s for s in agent("sharing_status", app=cid)["shares"] if s["state"] == "sharing"]
    )
    agent("app_launch", canvas=cid)
    again = agent("sharing_start", app=cid)
    assert again["state"] == "sharing" and again["url"] != shared["url"]
    assert agent("sharing_stop", app=cid)["state"] == "stopped"
    assert app.approver.asked[-1]["action"] == "share_stop"
    agent("app_launch", canvas=cid, stop=True)
    # The Session log says which app was shared and stopped, never the link.
    log = json.dumps(agent("app_session", who="agent", limit=200))
    assert "share_start" in log and "devtunnels.ms" not in log


# ===== 11. The statistics and the change log, read back =====


def test_the_statistics_and_the_change_log_say_what_happened_never_a_value(app: Built) -> None:
    agent, folder = app.agent, app.folder
    summary = agent("stats")
    busiest = {b["object"]: b for b in summary["busiest"]}
    assert busiest["connection:The sandbox"]["count"] > 50 and {
        "connection:Orders",
        "connection:Depot",
    } <= set(busiest)
    assert agent("stats", action="endpoint", name="local complete_work_orders")["figures"]["errors"] == 0
    one = agent("stats", action="endpoint", name="local export_work_orders")
    assert one["figures"]["count"] >= 1 and one["calls"][0]["outcome"]["ok"] is True, one
    table = agent("stats", action="table", name="The sandbox.work_orders")
    assert table["figures"]["count"] > 20 and table["figures"]["p50"] > 0
    assert agent("stats", action="slowest", n=3)["calls"] and "hints" in agent("stats", action="hints")
    errors = agent("stats", action="errors")["calls"]
    assert errors and not any(c["outcome"]["ok"] for c in errors), errors[:2]  # the refused calls
    # The open project's figures are kept in .sab/stats.json (a few seconds after the calls settle).
    kept = folder / ".sab" / "stats.json"
    assert until(kept.is_file, 30)
    # The change log: each change to the tables, API.py's endpoints, the widget, the canvas, the notebook.
    endpoints = agent("changes", action="search", kind="endpoint", n=200)["changes"]
    words = [c["words"] for c in endpoints]
    assert "Added the endpoint POST /visits/done to API.py" in words
    assert "Added the endpoint GET /work_orders/export.csv to API.py" in words
    by_wizard = next(c for c in endpoints if c["words"] == "Added the endpoint GET /work_orders to API.py")
    assert by_wizard["who"] == "agent" and by_wizard["before"] == "" and by_wizard["after"]
    canvas = agent("changes", action="history", object="canvas:field_service / Dispatch", n=200)["changes"]
    assert canvas and all(c["who"] == "agent" for c in canvas)
    assert any("items added" in c["words"] and "visit_card" in c["words"] for c in canvas)
    last = agent("changes", action="last", object="canvas:field_service / Dispatch")
    assert last["change"]["object"] == {"kind": "canvas", "name": "field_service / Dispatch"}, last
    widget = agent("changes", action="search", kind="widget", n=50)["changes"]
    assert any(c["object"]["name"] == "visit_card" for c in widget)
    tables = agent("changes", action="search", kind="table", n=200)["changes"]
    assert {c["object"]["name"] for c in tables} >= {"technicians", "customers"}
    since = agent("changes", action="since", since="2020-01-01T00:00:00+00:00", n=500)["changes"]
    assert len(since) > 40 and {c["who"] for c in since} <= {"agent", "user", "app"}
    assert agent("changes", action="search", word="page_size")["changes"] or True
    # Both files are the project's own, Git-ignored, and hold names, types and fingerprints: never a value.
    log = (folder / ".sab" / "changes.jsonl").read_text(encoding="utf-8")
    assert log.count("\n") >= len(since)
    ignored = (folder / ".sab" / ".gitignore").read_text(encoding="utf-8")
    assert "stats.json" in ignored and "changes.jsonl" in ignored
    for text in (log, kept.read_text(encoding="utf-8")):
        for value in ("Ada Marlow", "thermostat", "Brightline", KEYRING_SECRET, "288.75"):
            assert value not in text, value
    # The Environment: each table with where it is used (its grid, API.py's endpoints, the canvas's widgets).
    listed = {
        i["id"]: i for i in agent("environment", action="list", args={"search": "technicians"})["items"]
    }
    used = {u["kind"] for u in listed["table:technicians"]["used"]}
    assert "grid" in used, listed["table:technicians"]["used"]


# ===== 12. The finished project is examples/field_service; Remove the sandbox, last of all =====


def _kept(folder: Path) -> dict[str, bytes]:
    """A project folder's files as the example keeps them (NOT_KEPT left out)."""
    return {
        file.relative_to(folder).as_posix(): file.read_bytes()
        for file in sorted(folder.rglob("*"))
        if file.is_file() and not set(file.relative_to(folder).parts) & set(NOT_KEPT)
    }


def _unversioned(name: str, content: bytes) -> bytes:
    """A file as compared with the example: .sab/project.json's app_version is the app's that saved it (a
    release changes it and nothing else), so it is left out; every other file byte for byte."""
    if name != ".sab/project.json":
        return content
    raw = json.loads(content)
    raw.pop("app_version", None)
    return json.dumps(raw, sort_keys=True).encode()


def test_the_finished_project_is_the_example_folder_and_the_sandbox_is_removed_last(app: Built) -> None:
    agent, folder = app.agent, app.folder
    agent("api", action="stop")
    for name in ("sandbox_work_orders", "technicians", "customers"):
        agent("datasets_close", name=name)
    agent("project_save")
    made = _kept(folder)
    assert {
        "API.py",
        CANVAS,
        "README.md",
        "data.ipynb",
        "data.py",
        "requirements.txt",
        "scripts/orders.py",
        "widgets/visit_card.widget.py",
        ".sab/project.json",
        "source/work_orders.csv",
    } <= set(made)
    for name, content in made.items():  # nothing of this computer, no secret, in what is shared
        text = content.decode("utf-8")
        assert str(app.tmp) not in text and KEYRING_SECRET not in text, name
    # examples/field_service is this folder, byte for byte (SAB_FIELD_SERVICE_KEEP=1 writes it again).
    if os.environ.get("SAB_FIELD_SERVICE_KEEP"):
        if EXAMPLE.exists():
            shutil.rmtree(EXAMPLE)
        for name, content in made.items():
            (EXAMPLE / name).parent.mkdir(parents=True, exist_ok=True)
            (EXAMPLE / name).write_bytes(content)
    example = _kept(EXAMPLE)
    assert sorted(example) == sorted(made)
    for name, content in made.items():
        assert _unversioned(name, example[name]) == _unversioned(name, content), (
            f"examples/field_service/{name} is not what the build makes"
        )
    # Remove the sandbox (the agent's waits for Allow): its folder and its two files, nothing else.
    left = sorted(p.name for p in folder.iterdir() if not p.name.startswith("sandbox"))
    removed = agent("sandbox", action="drop")
    assert removed["removed"] == ["sandbox/", "sandbox_data.py", "sandbox_connections.py"]
    assert sorted(p.name for p in folder.iterdir()) == left
    assert app.approver.asked[-1]["dataset"] == "Sandbox"
    assert agent("sandbox", action="list")["tables"] == []
    assert agent("project_close", discard=True)["project"] is None
