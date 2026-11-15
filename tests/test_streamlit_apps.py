"""Streamlit pieces and the page designer on the running server (docs/ideas.md, 2026-11-15): an app's
pieces and pages over HTTP and by the agent's commands; the table hand-over (Parquet written, only
the tables a page names); the out-of-date rule; the export folder; the door the live pages come
through. And, with a Python that has Streamlit, the real thing: the pages run in Streamlit itself.

Streamlit is not this app's dependency. The tests that need it are skipped unless
SWISSARMYGRID_STREAMLIT_PYTHON names a Python with streamlit, pandas and pyarrow (or this Python has
them). Made-up data only."""

from __future__ import annotations

import ast
import json
import os
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pyarrow as pa
import pyarrow.parquet as pq
import pytest
from starlette.testclient import TestClient

from swissarmygrid.cli.commands import CommandError, execute
from swissarmygrid.server import streamlit_apps
from tests.conftest import AGENT, AUTH, BASE, PORT, make_client, push
from tests.test_cli import Live, data_of, live  # noqa: F401 (the running server)
from tests.test_cli import run as command

FILTER = '# Region filter\nregion = st.selectbox("Region", sorted(orders["region"].unique()))'
TOTAL = '# Total\nst.metric("Total", int(orders[orders["region"] == region]["amount"].sum()))'
ORDERS = pa.table(
    {
        "order_id": [1, 2, 3, 4, 5, 6],
        "region": ["East", "West", "East", "North", "West", "East"],
        "amount": [100, 250, 40, 75, 10, 5],
    }
)
CUSTOMERS = pa.table({"customer": ["Acme", "Globex"], "region": ["East", "West"]})
PIECES = [{"cell": 4, "code": FILTER}, {"cell": 5, "code": TOTAL}]


def _streamlit_python() -> str | None:
    """A Python with Streamlit, pandas and pyarrow, for the tests that run the real thing."""
    for python in (os.environ.get("SWISSARMYGRID_STREAMLIT_PYTHON"), sys.executable):
        if not python or not Path(python).is_file():
            continue
        try:
            if not streamlit_apps.check(python)["missing"]:
                return python
        except ValueError:
            continue
    return None


STREAMLIT_PYTHON = _streamlit_python()
needs_streamlit = pytest.mark.skipif(
    STREAMLIT_PYTHON is None,
    reason="no Python with Streamlit here (set SWISSARMYGRID_STREAMLIT_PYTHON to one)",
)


class FakeProcess:
    def __init__(self, python: str) -> None:
        self.port = 1
        self.python = python
        self.up = True

    def alive(self) -> bool:
        return self.up

    async def stop(self) -> None:
        self.up = False


class FakeRunner:
    """Stands in for the Streamlit process: the app's files and tables are still written for real."""

    def __init__(self, missing: list[str] | None = None) -> None:
        self.missing = missing or []
        self.started: list[tuple[str, str, str]] = []
        self.installed: list[tuple[str, list[str]]] = []
        self.processes: list[FakeProcess] = []

    def default_python(self) -> str:
        return "/made/up/python"

    async def check(self, python: str) -> dict[str, Any]:
        return {"python": python, "missing": list(self.missing)}

    async def start(self, python: str, folder: str, base: str) -> FakeProcess:
        self.started.append((python, folder, base))
        self.processes.append(FakeProcess(python))
        return self.processes[-1]

    async def install(self, python: str, packages: list[str]) -> tuple[int | None, str]:
        self.installed.append((python, packages))
        self.missing = []
        return 0, "installed"


@pytest.fixture
def served(tmp_path: Path) -> Iterator[tuple[TestClient, FakeRunner]]:
    with make_client(tmp_path) as client:
        runner = FakeRunner()
        client.app.state.ctx.streamlit._runner = runner  # type: ignore[attr-defined]
        assert push(client, "orders", ORDERS).status_code == 200
        assert push(client, "customers", CUSTOMERS).status_code == 200
        yield client, runner


def _open(client: TestClient, **more: Any) -> dict[str, Any]:
    body = {"title": "sales.ipynb", "pieces": PIECES, "window": "w1"} | more
    opened = client.post("/streamlit/apps", headers=AUTH, json=body)
    assert opened.status_code == 200, opened.text
    return dict(opened.json())


def _ok(response: Any) -> dict[str, Any]:
    assert response.status_code == 200, response.text
    return dict(response.json())


# ===== pieces and pages =====


def test_an_app_holds_its_pieces_and_says_what_each_makes_and_reads(
    served: tuple[TestClient, FakeRunner],
) -> None:
    client, _ = served
    state = _open(client)
    assert state["running"] is False and state["path"] is None and state["pages"] == []
    assert [(p["cell"], p["name"], p["state"]) for p in state["pieces"]] == [
        (4, "Region filter", "notRun"),
        (5, "Total", "notRun"),
    ]
    picker, total = state["pieces"]
    assert picker["makes"] == ["region"] and picker["reads"] == [] and picker["tables"] == ["orders"]
    assert total["makes"] == [] and total["reads"] == ["region"] and total["inputs"] == [4]
    assert client.get("/streamlit/apps", headers=AUTH).json()["apps"][0]["title"] == "sales.ipynb"
    # The document as it is typed: a piece changed, one added, one gone.
    app = state["app"]
    synced = _ok(
        client.put(
            f"/streamlit/apps/{app}",
            headers=AUTH,
            json={"pieces": [{"cell": 5, "code": TOTAL}, {"cell": 9, "code": "x = st.slider(\n"}]},
        )
    )
    assert [p["cell"] for p in synced["pieces"]] == [5, 9]
    assert synced["pieces"][1]["problem"].startswith("line 1")
    for bad in ({"pieces": [{"cell": 4}]}, {"pieces": [{"cell": 0, "code": ""}]}, {"pieces": "x"}):
        assert client.put(f"/streamlit/apps/{app}", headers=AUTH, json=bad).status_code == 400
    assert client.get("/streamlit/apps/nope", headers=AUTH).status_code == 404


def test_pieces_are_pushed_to_pages_moved_resized_and_taken_off(
    served: tuple[TestClient, FakeRunner],
) -> None:
    client, _ = served
    app = _open(client)["app"]
    base = f"/streamlit/apps/{app}"
    # Push to a new page: the page is made with the piece on it.
    made = _ok(client.post(f"{base}/pages", headers=AUTH, json={"cell": 4}))
    assert made["page"] == "p1" and made["pages"][0]["name"] == "Page 1"
    assert made["pages"][0]["pieces"] == [{"id": "s1", "cell": 4, "w": 6, "h": None}]
    pushed = _ok(client.post(f"{base}/pages/p1/pieces", headers=AUTH, json={"cell": 5, "w": 12}))
    assert pushed["piece"] == "s2"
    page = pushed["pages"][0]
    assert [s["id"] for s in page["pieces"]] == ["s1", "s2"] and page["rows"] == [["s1"], ["s2"]]
    assert page["order"] == ["s1", "s2"] and page["problems"] == [] and page["tables"] == ["orders"]
    # Place the filter BELOW the total: it still runs first.
    moved = _ok(client.patch(f"{base}/pages/p1/pieces/s1", headers=AUTH, json={"index": 1}))
    page = moved["pages"][0]
    assert [s["id"] for s in page["pieces"]] == ["s2", "s1"] and page["order"] == ["s1", "s2"]
    # Resize: columns of 12, rows of 40 pixels; a row holds what fits.
    sized = _ok(client.patch(f"{base}/pages/p1/pieces/s2", headers=AUTH, json={"w": 6, "h": 4}))
    page = sized["pages"][0]
    assert page["pieces"][0] == {"id": "s2", "cell": 5, "w": 6, "h": 4} and page["rows"] == [["s2", "s1"]]
    assert _ok(client.patch(f"{base}/pages/p1/pieces/s2", headers=AUTH, json={"w": 99, "h": None}))["pages"][
        0
    ]["pieces"][0] == {"id": "s2", "cell": 5, "w": 12, "h": None}
    # A second page; rename; a piece sent across; pages reordered; removed.
    second = _ok(client.post(f"{base}/pages", headers=AUTH, json={"name": "Details"}))
    assert [p["id"] for p in second["pages"]] == ["p1", "p2"]
    renamed = _ok(client.patch(f"{base}/pages/p1", headers=AUTH, json={"name": "Sales overview"}))
    assert [p["name"] for p in renamed["pages"]] == ["Sales overview", "Details"]
    sent = _ok(client.patch(f"{base}/pages/p1/pieces/s2", headers=AUTH, json={"page": "p2"}))
    assert [[s["id"] for s in p["pieces"]] for p in sent["pages"]] == [["s1"], ["s2"]]
    # The total alone on a page: the page says what it lacks.
    assert "which is not on this page" in sent["pages"][1]["problems"][0]
    first = _ok(client.patch(f"{base}/pages/p2", headers=AUTH, json={"index": 0}))
    assert [p["id"] for p in first["pages"]] == ["p2", "p1"]
    gone = _ok(client.delete(f"{base}/pages/p2/pieces/s2", headers=AUTH))
    assert gone["pages"][0]["pieces"] == []
    assert [p["id"] for p in _ok(client.delete(f"{base}/pages/p2", headers=AUTH))["pages"]] == ["p1"]
    # What cannot be: a cell that is not a piece, a page or a piece that is not there, a bad name.
    assert client.post(f"{base}/pages/p1/pieces", headers=AUTH, json={"cell": 77}).status_code == 400
    assert client.post(f"{base}/pages/p9/pieces", headers=AUTH, json={"cell": 4}).status_code == 404
    assert client.patch(f"{base}/pages/p1/pieces/s9", headers=AUTH, json={"w": 3}).status_code == 404
    assert client.patch(f"{base}/pages/p1", headers=AUTH, json={"name": ""}).status_code == 400
    # The audit log says who: the agent's pushes are the agent's.
    client.post(f"{base}/pages", headers=AGENT, json={"name": "Agent's"})
    log = client.app.state.ctx.ws.audit.tail(50)  # type: ignore[attr-defined]
    assert any(e["actor"] == "agent" and e["action"] == "streamlit_add_page" for e in log)


# ===== the table hand-over, and the out-of-date rule =====


def _files(runner: FakeRunner) -> Path:
    return Path(runner.started[-1][1])


def test_run_writes_the_pieces_the_pages_and_only_the_tables_they_name(
    served: tuple[TestClient, FakeRunner],
) -> None:
    client, runner = served
    app = _open(client, python="/a/notebook/python")["app"]
    base = f"/streamlit/apps/{app}"
    _ok(client.post(f"{base}/pages", headers=AUTH, json={"cell": 5, "w": 12}))
    _ok(client.post(f"{base}/pages/p1/pieces", headers=AUTH, json={"cell": 4, "w": 4}))
    ran = _ok(client.post(f"{base}/run", headers=AUTH))
    assert ran["running"] is True and ran["problem"] is None and ran["notes"] == []
    # One process, in the notebook's own Python, under the app's own secret path.
    python, folder, path = runner.started[0]
    assert python == "/a/notebook/python" and len(runner.started) == 1
    assert path == ran["path"].rstrip("/") and path.startswith(f"/streamlit/live/{app}-")
    assert ran["address"] == f"http://127.0.0.1:{PORT}{path}/"
    root = Path(folder)
    assert (
        root.name.startswith("swissarmygrid-streamlit-")
        and root.parent == Path(os.path.realpath(root)).parent
    )
    names = sorted(p.name for p in root.iterdir())
    assert names == [
        "app.py",
        "data",
        "home.py",
        "manifest.json",
        "page_p1_1.py",
        "piece_4_1.py",
        "piece_5_1.py",
    ]
    manifest = json.loads((root / "manifest.json").read_text())
    assert [(p["kind"], p["path"], p["default"]) for p in manifest["pages"]] == [
        ("home", "home", True),
        ("piece", "piece-4", False),
        ("piece", "piece-5", False),
        ("page", "page-p1", False),
    ]
    # Only the table the code names is handed over, as Parquet, as the grid has it.
    assert sorted(p.name for p in (root / "data").iterdir()) == ["orders.parquet"]
    assert pq.read_table(root / "data" / "orders.parquet").to_pydict() == ORDERS.to_pydict()
    page = (root / "page_p1_1.py").read_text()
    ast.parse(page)
    assert 'orders = _table("orders"' in page and "customers" not in page
    assert page.index("with _slot_s2:") < page.index("with _slot_s1:")  # the filter runs first
    # The total alone, in its cell: the filter comes with it.
    alone = (root / "piece_5_1.py").read_text()
    assert "region comes from the piece in cell 4" in alone and "st.metric" in alone
    assert [p["state"] for p in ran["pieces"]] == ["current", "current"]
    assert (
        ran["pieces"][0]["preview"] == f"{path}/piece-4" and ran["pages"][0]["address"] == f"{path}/page-p1"
    )


def test_a_changed_table_or_changed_code_makes_a_piece_out_of_date_until_it_runs(
    served: tuple[TestClient, FakeRunner],
) -> None:
    client, runner = served
    app = _open(client, pieces=[*PIECES, {"cell": 6, "code": "st.dataframe(customers)"}])["app"]
    base = f"/streamlit/apps/{app}"
    _ok(client.post(f"{base}/pages", headers=AUTH, json={"cell": 5}))
    _ok(client.post(f"{base}/run", headers=AUTH))
    root = _files(runner)
    written = (root / "data" / "customers.parquet").stat().st_mtime_ns
    # A new grid step on orders: the pieces that name orders go out of date; the customers one does not.
    orders_grid = next(
        g["grid"] for g in client.get("/grids", headers=AUTH).json()["grids"] if g["dataset"] == "orders"
    )
    step = {"kind": "filter", "params": {"column": "region", "op": "ne", "value": "North"}}
    assert client.post(f"/grids/{orders_grid}/steps", headers=AUTH, json={"steps": [step]}).status_code == 200
    state = client.get(base, headers=AUTH).json()
    assert [(p["cell"], p["state"], p["changed"]) for p in state["pieces"]] == [
        (4, "outOfDate", ["orders"]),
        (5, "outOfDate", ["orders"]),
        (6, "current", []),
    ]
    assert state["pages"][0]["out_of_date"] is True
    # Nothing ran by itself: the file still holds the table as it was.
    assert pq.read_table(root / "data" / "orders.parquet").num_rows == 6
    # Run: the data is the table after its steps, and every piece is current again.
    time.sleep(0.02)
    ran = _ok(client.post(f"{base}/run", headers=AUTH))
    assert {p["state"] for p in ran["pieces"]} == {"current"} and ran["generation"] == 2
    held = pq.read_table(root / "data" / "orders.parquet").to_pydict()
    assert held["region"] == ["East", "West", "East", "West", "East"] and len(runner.started) == 1
    # A table that did not change is not written again; the earlier pages are kept one run, then go.
    assert (root / "data" / "customers.parquet").stat().st_mtime_ns == written
    assert {"page_p1_1.py", "page_p1_2.py"} <= {p.name for p in root.iterdir()}
    _ok(client.post(f"{base}/run", headers=AUTH))
    assert "page_p1_1.py" not in {p.name for p in root.iterdir()}
    # A sort made by clicking a header is a way of looking: it changes nothing.
    sort = {"kind": "sort", "params": {"keys": [["amount", "desc"]], "header": True}}
    client.post(f"/grids/{orders_grid}/steps", headers=AUTH, json={"steps": [step, sort]})
    assert {p["state"] for p in client.get(base, headers=AUTH).json()["pieces"]} == {"current"}
    # The table pushed again (its maker ran): out of date.
    assert push(client, "orders", ORDERS.slice(0, 3)).status_code == 200
    assert client.get(base, headers=AUTH).json()["pieces"][0]["state"] == "outOfDate"
    _ok(client.post(f"{base}/run", headers=AUTH))

    # Changed code: only that piece; the uses line never counts; undoing the edit clears it.
    def sync(code: str) -> list[tuple[str, bool]]:
        body = {
            "pieces": [{"cell": 4, "code": code}, PIECES[1], {"cell": 6, "code": "st.dataframe(customers)"}]
        }
        got = _ok(client.put(base, headers=AUTH, json=body))
        return [(p["state"], p["code_changed"]) for p in got["pieces"]]

    assert sync(FILTER + "\nst.write(region)") == [
        ("outOfDate", True),
        ("current", False),
        ("current", False),
    ]
    assert sync("# uses orders @cell3\n" + FILTER)[0] == ("current", False)
    assert sync(FILTER)[0] == ("current", False)
    # A change in the designer while the app runs is shown at once (it is a run).
    before = client.get(base, headers=AUTH).json()["generation"]
    moved = _ok(client.post(f"{base}/pages/p1/pieces", headers=AUTH, json={"cell": 4}))
    assert moved["generation"] == before + 1


def test_stopping_removes_the_temporary_folder_and_the_kernel_or_window_going_stops_the_app(
    served: tuple[TestClient, FakeRunner],
) -> None:
    client, runner = served
    apps = client.app.state.ctx.streamlit  # type: ignore[attr-defined]
    app = _open(client, kernel="k1")["app"]
    base = f"/streamlit/apps/{app}"
    _ok(client.post(f"{base}/pages", headers=AUTH, json={"cell": 4}))
    _ok(client.post(f"{base}/run", headers=AUTH))
    folder = _files(runner)
    assert folder.is_dir() and apps.port_of(runner.started[0][2].rsplit("/", 1)[-1]) == 1
    stopped = _ok(client.post(f"{base}/stop", headers=AUTH))
    assert stopped["running"] is False and not folder.exists() and runner.processes[0].up is False
    assert [p["state"] for p in stopped["pieces"]] == ["notRun", "notRun"]
    assert len(stopped["pages"]) == 1  # the pages stay: they are the notebook's
    # Another Python chosen for the notebook: the next run starts there.
    _ok(client.post(f"{base}/run", headers=AUTH, json={"python": "/first/python"}))
    _ok(client.post(f"{base}/run", headers=AUTH, json={"python": "/second/python"}))
    assert [s[0] for s in runner.started] == ["/made/up/python", "/first/python", "/second/python"]
    assert [p.up for p in runner.processes] == [False, False, True]
    # Its kernel stops: so does the process, and its folder goes.
    folder = _files(runner)
    client.portal.call(apps.kernel_stopped, "another")  # type: ignore[union-attr]
    assert runner.processes[-1].up is True
    client.portal.call(apps.kernel_stopped, "k1")  # type: ignore[union-attr]
    assert runner.processes[-1].up is False and not folder.exists()
    # Its window gone a minute: the app goes. One the agent opened (no window) stays.
    agents = client.post(
        "/streamlit/apps", headers=AGENT, json={"title": "agent's", "pieces": PIECES}
    ).json()["app"]
    clock = [1000.0]
    apps._now = lambda: clock[0]
    assert client.portal.call(apps.stop_orphans, {"w1"}) == []
    assert client.portal.call(apps.stop_orphans, set()) == []
    clock[0] += 61
    assert client.portal.call(apps.stop_orphans, set()) == [app]
    assert [a["app"] for a in client.get("/streamlit/apps", headers=AUTH).json()["apps"]] == [agents]
    # The document closed.
    assert client.delete(f"/streamlit/apps/{agents}", headers=AUTH).status_code == 200
    assert client.get("/streamlit/apps", headers=AUTH).json()["apps"] == []


def test_a_python_without_streamlit_is_said_and_install_goes_into_that_python(
    served: tuple[TestClient, FakeRunner],
) -> None:
    client, runner = served
    runner.missing = ["streamlit", "pyarrow"]
    app = _open(client, python="/a/notebook/python")["app"]
    ran = _ok(client.post(f"/streamlit/apps/{app}/run", headers=AUTH))
    assert ran["running"] is False and runner.started == []
    assert ran["problem"] == {
        "kind": "missing",
        "packages": ["streamlit", "pyarrow"],
        "python": "/a/notebook/python",
        "command": "uv pip install --python /a/notebook/python streamlit pyarrow",
    }
    done = _ok(client.post(f"/streamlit/apps/{app}/install", headers=AUTH))
    assert done["ok"] is True and runner.installed == [("/a/notebook/python", ["streamlit", "pyarrow"])]
    assert _ok(client.post(f"/streamlit/apps/{app}/run", headers=AUTH))["running"] is True


def test_this_apps_own_python_has_no_streamlit(tmp_path: Path) -> None:
    """Streamlit is not a dependency of the app: the real check, on this Python."""
    if not streamlit_apps.check(sys.executable)["missing"]:
        pytest.skip("this Python happens to have Streamlit")
    with make_client(tmp_path) as client:
        app = _open(client)["app"]
        ran = _ok(client.post(f"/streamlit/apps/{app}/run", headers=AUTH))
        assert ran["problem"]["kind"] == "missing" and "streamlit" in ran["problem"]["packages"]
        assert ran["problem"]["python"] == sys.executable and ran["running"] is False
    project = (Path(__file__).parents[1] / "pyproject.toml").read_text(encoding="utf-8")
    assert "streamlit" not in project.lower()


# ===== export =====


def test_export_writes_a_folder_that_needs_nothing_of_this_app(
    served: tuple[TestClient, FakeRunner], tmp_path: Path
) -> None:
    client, _ = served
    app = _open(client)["app"]
    base = f"/streamlit/apps/{app}"
    target = tmp_path / "exported" / "sales app"
    assert (
        client.post(f"{base}/export", headers=AUTH, json={"folder": str(target)}).status_code == 400
    )  # no page
    _ok(client.post(f"{base}/pages", headers=AUTH, json={"name": "Sales overview", "cell": 5, "w": 12}))
    _ok(client.post(f"{base}/pages/p1/pieces", headers=AUTH, json={"cell": 4, "w": 4}))
    _ok(client.post(f"{base}/pages", headers=AUTH, json={"name": "Filter only", "cell": 4}))
    orders_grid = next(
        g["grid"] for g in client.get("/grids", headers=AUTH).json()["grids"] if g["dataset"] == "orders"
    )
    step = {"kind": "filter", "params": {"column": "amount", "op": "gt", "value": 20}}
    client.post(f"/grids/{orders_grid}/steps", headers=AUTH, json={"steps": [step]})
    assert (
        client.post(f"{base}/export", headers=AUTH, json={"folder": str(target)}).status_code == 404
    )  # no parent
    target.parent.mkdir()
    (target.parent / "a file").write_text("x")
    assert (
        client.post(
            f"{base}/export", headers=AUTH, json={"folder": str(target.parent / "a file")}
        ).status_code
        == 404
    )
    done = _ok(client.post(f"{base}/export", headers=AUTH, json={"folder": str(target)}))
    assert done["folder"] == str(target) and done["problems"] == [] and done["tables"] == ["orders"]
    assert done["files"] == [
        "README.txt",
        "app.py",
        "app_pages/filter_only.py",
        "app_pages/sales_overview.py",
        "data/orders.parquet",
        "requirements.txt",
    ]
    assert sorted(str(p.relative_to(target)) for p in target.rglob("*") if p.is_file()) == done["files"]
    # The data is each table after its steps; the code names nothing of this app.
    assert pq.read_table(target / "data" / "orders.parquet").to_pydict()["amount"] == [100, 250, 40, 75]
    assert (target / "requirements.txt").read_text() == "streamlit>=1.36\npandas\npyarrow\n"
    for file in target.rglob("*.py"):
        text = file.read_text()
        ast.parse(text)
        assert "import swissarmygrid" not in text and "sag." not in text
    assert "streamlit run app.py" in (target / "README.txt").read_text()
    # Exported again into the same folder: its files are replaced, nothing else is touched.
    (target / "notes.txt").write_text("mine")
    _ok(client.post(f"{base}/export", headers=AUTH, json={"folder": str(target)}))
    assert (target / "notes.txt").read_text() == "mine"


# ===== an app opened from its file (the agent, without the Workbench window) =====


def test_the_agent_opens_a_saved_notebooks_app_and_works_its_pages(live: Live, tmp_path: Path) -> None:  # noqa: F811
    cells = [
        {"kind": "code", "source": "x = 1"},
        {"kind": "streamlit", "source": FILTER},
        {"kind": "streamlit", "source": TOTAL},
    ]
    path = str(tmp_path / "sales.ipynb")
    command(
        "workbench_save",
        path=path,
        cells=cells,
        pages=[{"name": "Sales overview", "pieces": [{"cell": 3, "w": 12}]}],
    )
    opened = data_of(execute("workbench_open", {"path": path}))
    assert [c["kind"] for c in opened["cells"]] == ["code", "streamlit", "streamlit"]
    assert opened["pages"][0]["name"] == "Sales overview"
    app = command("streamlit_open", path=path)
    assert app["title"] == "sales.ipynb" and [p["cell"] for p in app["pieces"]] == [2, 3]
    assert [p["id"] for p in app["pages"]] == ["p1"]
    assert command("streamlit_apps")["apps"][0]["app"] == app["app"]
    pushed = command("streamlit_piece_push", app=app["app"], page="p1", cell=2, w=4)
    assert pushed["piece"] == "s2"
    placed = command("streamlit_piece_place", app=app["app"], page="p1", piece="s2", index=0, w=5, h=3)
    assert placed["pages"][0]["pieces"][0] == {"id": "s2", "cell": 2, "w": 5, "h": 3}
    assert (
        command("streamlit_piece_place", app=app["app"], page="p1", piece="s2", h=0)["pages"][0]["pieces"][0][
            "h"
        ]
        is None
    )
    added = command("streamlit_page_add", app=app["app"], name="Second")
    assert added["page"] == "p2"
    assert (
        command("streamlit_page_change", app=app["app"], page="p2", name="Details")["pages"][1]["name"]
        == "Details"
    )
    moved = command("streamlit_piece_place", app=app["app"], page="p1", piece="s2", to_page="p2")
    assert [s["id"] for s in moved["pages"][1]["pieces"]] == ["s2"]
    assert (
        len(command("streamlit_piece_remove", app=app["app"], page="p2", piece="s2")["pages"][1]["pieces"])
        == 0
    )
    assert [p["id"] for p in command("streamlit_page_remove", app=app["app"], page="p2")["pages"]] == ["p1"]
    layout = command("streamlit_app", app=app["app"])["pages"][0]
    assert layout["rows"] == [["s1"]] and layout["order"] == ["s1"]
    synced = command("streamlit_sync", app=app["app"], pieces=[{"cell": 2, "code": "st.write(1)"}])
    assert [p["name"] for p in synced["pieces"]] == ["Piece 2"]
    assert command("streamlit_address", app=app["app"])["running"] is False
    out = command("streamlit_export", app=app["app"], folder=str(tmp_path / "out"))
    assert "app.py" in out["files"] and (tmp_path / "out" / "app.py").is_file()
    assert command("streamlit_close", app=app["app"]) == {"ok": True}
    with pytest.raises(CommandError, match="not open"):
        execute("streamlit_app", {"app": app["app"]})
    # A script's app: its numbered Streamlit cells and its pages block.
    script = tmp_path / "sales.py"
    script.write_text(
        f"# %% [4] [streamlit]\n{FILTER}\n# %% [5] [streamlit]\n{TOTAL}\n# %% [streamlit-pages]\n"
        '# {"id": "p1", "name": "Sales", "pieces": [{"id": "s1", "cell": 5, "w": 12}]}\n'
    )
    scripted = command("streamlit_open", path=str(script))
    assert [p["cell"] for p in scripted["pieces"]] == [4, 5] and scripted["pages"][0]["name"] == "Sales"
    with pytest.raises(CommandError, match="is not there"):
        execute("streamlit_open", {"path": str(tmp_path / "missing.ipynb")})


def test_running_a_notebook_as_the_agent_leaves_streamlit_cells_to_the_app(
    live: Live,  # noqa: F811
    tmp_path: Path,
) -> None:
    path = str(tmp_path / "mixed.ipynb")
    cells = [
        {"kind": "code", "source": "x = 41 + 1\nx"},
        {"kind": "streamlit", "source": "import nothing_like_this"},
    ]
    pages = [{"id": "p1", "name": "Kept", "pieces": [{"id": "s1", "cell": 2, "w": 12, "h": None}]}]
    command("workbench_save", path=path, cells=cells, pages=pages)
    ran = data_of(execute("workbench_run_notebook", {"path": path}))
    command("workbench_kernel", kernel=ran["kernel"], action="stop")
    assert ran["cells_run"] == 1  # the piece did not run in the kernel
    assert (
        data_of(execute("workbench_open", {"path": path}))["pages"] == pages
    )  # and the pages were saved back


# ===== the door the live pages come through =====


def test_live_pages_need_the_apps_own_secret_and_only_this_computer(
    served: tuple[TestClient, FakeRunner],
) -> None:
    client, _ = served
    app = _open(client)["app"]
    _ok(client.post(f"/streamlit/apps/{app}/pages", headers=AUTH, json={"cell": 4}))
    ran = _ok(client.post(f"/streamlit/apps/{app}/run", headers=AUTH))
    path = ran["path"]
    # No token is asked for on these paths (a frame cannot send one): the secret in the path is.
    # With the right secret the request is passed on (nothing listens on the fake's port: 502).
    assert client.get(f"{path}piece-4").status_code == 502
    assert client.get(f"{path}piece-4", headers={"Origin": "null"}).status_code == 502
    assert client.get(f"{path}piece-4", headers={"Origin": BASE}).status_code == 502
    # A wrong secret, another app's id, no secret: there is no such page.
    wrong = path.replace(path[-9:-1], "00000000")
    for bad in (
        wrong,
        f"/streamlit/live/{app}/",
        f"/streamlit/live/{app}-/",
        "/streamlit/live/nope-secret/x",
    ):
        assert client.get(bad).status_code == 404, bad
    assert client.get("/streamlit/live/").status_code in (401, 404)
    # Another site, or another host name, is refused before the secret is looked at.
    assert client.get(f"{path}piece-4", headers={"Origin": "https://example.com"}).status_code == 403
    assert client.get(f"{path}piece-4", headers={"Host": "evil.example"}).status_code == 403
    # `Origin: null` opens nothing else, and the app's own routes still need the token.
    assert client.get("/streamlit/apps", headers={"Origin": "null"}).status_code == 403
    assert client.get("/streamlit/apps", headers=AUTH | {"Origin": "null"}).status_code == 403
    assert client.get("/streamlit/apps").status_code == 401
    assert client.post(f"/streamlit/apps/{app}/run").status_code == 401
    # The designer's page shell is public like the Workbench's (no data in it).
    assert client.get("/designer").status_code == 200
    # A stopped app's address leads nowhere.
    client.post(f"/streamlit/apps/{app}/stop", headers=AUTH)
    assert client.get(f"{path}piece-4").status_code == 404


def test_the_frame_policy_of_the_workbench_is_as_it_was() -> None:
    """The live pages show inside the Workbench without weakening its policy: frames from this
    server only, as before."""
    static = Path(__file__).parents[1] / "web" / "static"
    for page in ("workbench.html", "designer.html"):
        text = (static / page).read_text(encoding="utf-8")
        assert "frame-src 'self';" in text and "127.0.0.1:" not in text


# ===== the real thing: Streamlit itself =====


def _fetch(url: str, timeout: float = 20) -> tuple[int, str]:
    try:
        with urllib.request.urlopen(url, timeout=timeout) as response:  # noqa: S310 (this computer)
            return response.status, response.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as error:
        return error.code, error.read().decode("utf-8", "replace")


APP_TEST = """
import json, sys
from streamlit.testing.v1 import AppTest
at = AppTest.from_file(sys.argv[1], default_timeout=60).run()
out = {"errors": [e.value for e in at.error] + [str(e.value) for e in at.exception]}
out["options"] = list(at.selectbox[0].options) if at.selectbox else []
out["first"] = at.metric[0].value if at.metric else None
if at.selectbox:
    at.selectbox[0].set_value(sys.argv[2]).run()
    out["second"] = at.metric[0].value if at.metric else None
    out["keys"] = [w.key for w in at.selectbox]
print(json.dumps(out))
"""


def _app_test(python: str, page: Path, pick: str) -> dict[str, Any]:
    done = subprocess.run(  # noqa: S603 (the test's own Streamlit Python)
        [python, "-c", APP_TEST, str(page), pick], capture_output=True, text=True, timeout=180, check=False
    )
    assert done.returncode == 0, done.stderr[-2000:]
    return dict(json.loads(done.stdout.strip().splitlines()[-1]))


@needs_streamlit
def test_the_real_streamlit_runs_the_pieces_the_page_and_the_export(live: Live, tmp_path: Path) -> None:  # noqa: F811
    assert STREAMLIT_PYTHON is not None
    grid = command(
        "datasets_paste",
        name="orders",
        text="order_id\tregion\tamount\n1\tEast\t100\n2\tWest\t250\n3\tEast\t40\n4\tNorth\t75\n",
    )["grid"]
    opened = live.user(
        "POST", "/streamlit/apps", {"title": "sales.ipynb", "pieces": PIECES, "python": STREAMLIT_PYTHON}
    )
    app = opened["app"]
    # Pushed to a new page; the filter placed BELOW the total.
    command("streamlit_page_add", app=app, name="Sales overview", cell=5, w=12)
    command("streamlit_piece_push", app=app, page="p1", cell=4, w=4)
    ran = command("streamlit_run", app=app)
    assert ran["running"] is True and ran["problem"] is None, ran["problem"]
    try:
        where = command("streamlit_address", app=app)
        assert where["running"] is True and set(where["pages"]) == {"Sales overview"}
        # The process listens on 127.0.0.1 only, and answers through this server under the secret.
        port = live.user("GET", f"/streamlit/apps/{app}")  # the state never names the Streamlit port
        assert "port" not in json.dumps(port)
        for address in (
            where["app"],
            where["pages"]["Sales overview"],
            where["pieces"]["4"],
            where["pieces"]["5"],
        ):
            status, text = _fetch(address)
            assert status == 200 and "<title>" in text, address
        status, _ = _fetch(where["app"] + "_stcore/health")
        assert status == 200
        assert _fetch(where["app"].replace(f"/{app}-", f"/{app}-0"))[0] == 404
        # Streamlit's own socket comes through too (its first words are a handshake that completes).
        from websockets.sync.client import connect

        socket_address = where["app"].replace("http://", "ws://") + "_stcore/stream"
        with connect(socket_address, subprotocols=["streamlit"], open_timeout=20) as stream:  # type: ignore[list-item]
            assert stream.subprotocol == "streamlit"
        # The pages as Streamlit runs them: the filter drives the total, though it sits below it.
        folder = Path(ran["folder"])
        assert folder.name.startswith("swissarmygrid-streamlit-")
        page = _app_test(STREAMLIT_PYTHON, next(folder.glob("page_p1_*.py")), "West")
        assert page["errors"] == [] and page["options"] == ["East", "North", "West"]
        assert page["first"] == "140" and page["second"] == "250" and page["keys"] == ["s2_1"]
        alone = _app_test(STREAMLIT_PYTHON, next(folder.glob("piece_5_*.py")), "North")
        assert alone["errors"] == [] and alone["first"] == "140" and alone["second"] == "75"
        # A grid step: out of date; run: the new data.
        command("steps_add", grid=grid, kind="filter", params={"column": "amount", "op": "gt", "value": 50})
        assert {p["state"] for p in command("streamlit_app", app=app)["pieces"]} == {"outOfDate"}
        again = command("streamlit_run", app=app)
        assert {p["state"] for p in again["pieces"]} == {"current"}
        fresh = _app_test(STREAMLIT_PYTHON, next(folder.glob(f"page_p1_{again['generation']}.py")), "West")
        assert (
            fresh["options"] == ["East", "North", "West"]
            and fresh["first"] == "100"
            and fresh["second"] == "250"
        )
        # A second page; then the export, run by Streamlit with nothing of this app beside it.
        command("streamlit_page_add", app=app, name="Filter only", cell=4)
        out = command("streamlit_export", app=app, folder=str(tmp_path / "exported"))
        assert out["problems"] == []
    finally:
        stopped = command("streamlit_stop", app=app)
    assert stopped["running"] is False and not folder.exists()
    assert _fetch(where["app"])[0] == 404
    exported = tmp_path / "exported"
    module = _app_test(STREAMLIT_PYTHON, exported / "app_pages" / "sales_overview.py", "West")
    assert module["errors"] == [] and module["first"] == "100" and module["second"] == "250"
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port = int(probe.getsockname()[1])
    environ = {k: v for k, v in os.environ.items() if not k.startswith(("SWISSARMYGRID", "PYTHONPATH"))}
    process = subprocess.Popen(  # noqa: S603 (the exported app, in the test's own Streamlit Python)
        [
            STREAMLIT_PYTHON,
            "-m",
            "streamlit",
            "run",
            "app.py",
            "--server.address=127.0.0.1",
            f"--server.port={port}",
            "--server.headless=true",
            "--browser.gatherUsageStats=false",
        ],
        cwd=exported,
        env=environ,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        deadline = time.monotonic() + 60
        while time.monotonic() < deadline:
            try:
                if _fetch(f"http://127.0.0.1:{port}/_stcore/health", 2)[0] == 200:
                    break
            except OSError:
                time.sleep(0.3)
        for page_path in ("", "filter_only"):
            status, text = _fetch(f"http://127.0.0.1:{port}/{page_path}")
            assert status == 200 and "<title>" in text
    finally:
        process.terminate()
        process.wait(20)


@needs_streamlit
def test_a_streamlit_process_ends_when_the_server_that_started_it_goes(tmp_path: Path) -> None:
    """The server killed outright: its Streamlit process notices and ends."""
    assert STREAMLIT_PYTHON is not None
    (tmp_path / "app.py").write_text("import streamlit as st\nst.write('hello')\n")
    parent = (
        "import asyncio, sys\n"
        "from swissarmygrid.server import streamlit_apps\n"
        "async def main():\n"
        "    running = await streamlit_apps.start(sys.argv[1], sys.argv[2], '/streamlit/live/a-b')\n"
        "    print(running.process.pid, running.port, flush=True)\n"
        "    await asyncio.sleep(600)\n"
        "asyncio.run(main())\n"
    )
    server = subprocess.Popen(  # noqa: S603 (a stand-in for the server)
        [sys.executable, "-c", parent, STREAMLIT_PYTHON, str(tmp_path)], stdout=subprocess.PIPE, text=True
    )
    try:
        assert server.stdout is not None
        pid, port = (int(part) for part in server.stdout.readline().split())
        assert _fetch(f"http://127.0.0.1:{port}/streamlit/live/a-b/_stcore/health")[0] == 200
        assert pid > 0
        # Only this computer: nothing answers on another of its addresses.
        other = socket.gethostbyname(socket.gethostname())
        if not other.startswith("127."):
            with pytest.raises(OSError):
                _fetch(f"http://{other}:{port}/streamlit/live/a-b/_stcore/health", 2)
    finally:
        server.kill()
        server.wait(10)
    deadline = time.monotonic() + 20
    gone = False
    while time.monotonic() < deadline and not gone:
        try:
            _fetch(f"http://127.0.0.1:{port}/streamlit/live/a-b/_stcore/health", 2)
            time.sleep(0.3)
        except OSError:
            gone = True
    assert gone, "the Streamlit process outlived the server that started it"
