"""The Streamlit canvas, live cells and projects on the running server (docs/ideas.md, 2026-11-15):
a document's Python cells that call Streamlit; a canvas's links to cells over HTTP and by the agent's
commands (place, move, resize, pages); Play from the cells' current code, saved or not; the
out-of-date rule; a missing cell; the app's file; the export folder; a project's data.ipynb and its
export data.py; Save as (one zip, no rows); the door the live pages come through. And, with a Python
that has Streamlit, the real thing: the pages run in Streamlit itself.

Streamlit is not this app's dependency. The tests that need it are skipped unless
SWISSARMYBENCH_STREAMLIT_PYTHON names a Python with streamlit, pandas and pyarrow (or this Python has
them). Made-up data only."""

from __future__ import annotations

import ast
import json
import os
import socket
import sqlite3
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
import zipfile
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

import pyarrow as pa
import pyarrow.parquet as pq
import pytest
from starlette.testclient import TestClient

from swissarmybench.cli.commands import CommandError, execute
from swissarmybench.domain import notebooks
from swissarmybench.renamed import env
from swissarmybench.server import streamlit_apps
from tests.conftest import AGENT, AUTH, BASE, make_client, push
from tests.test_cli import Live, data_of, live  # noqa: F401 (the running server)
from tests.test_cli import run as command
from tests.test_connections import sqlite_connection

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


def _streamlit_python() -> str | None:
    """A Python with Streamlit, pandas and pyarrow, for the tests that run the real thing."""
    # SWISSARMYGRID_STREAMLIT_PYTHON, its name before the rename, is still read (renamed.env).
    for python in (env("SWISSARMYBENCH_STREAMLIT_PYTHON"), sys.executable):
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
    reason="no Python with Streamlit here (set SWISSARMYBENCH_STREAMLIT_PYTHON to one)",
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


CELLS = [{"cell": 1, "code": "import pandas as pd"}, {"cell": 4, "code": FILTER}, {"cell": 5, "code": TOTAL}]


def _open(client: TestClient, **more: Any) -> dict[str, Any]:
    body = {"title": "sales.ipynb", "cells": CELLS, "window": "w1"} | more
    opened = client.post("/streamlit/apps", headers=AUTH, json=body)
    assert opened.status_code == 200, opened.text
    return dict(opened.json())


def _ok(response: Any) -> dict[str, Any]:
    assert response.status_code == 200, response.text
    return dict(response.json())


def _notebook(folder: Path, name: str = "sales.ipynb", total: str = TOTAL) -> Path:
    """A saved notebook: imports (1), a note, the filter (3), the total (4), plain Python (5)."""
    cells = [
        notebooks.Cell("code", "import pandas as pd"),
        notebooks.Cell("markdown", "# Sales"),
        notebooks.Cell("code", FILTER),
        notebooks.Cell("code", total),
        notebooks.Cell("code", "threshold = 50"),
    ]
    path = folder / name
    path.write_text(notebooks.write_notebook(cells), encoding="utf-8")
    return path


def _canvas(client: TestClient, **more: Any) -> dict[str, Any]:
    body = {"canvas": True, "title": "sales", "window": "w1", "pages": []} | more
    return _ok(client.post("/streamlit/apps", headers=AUTH, json=body))


def _files(runner: FakeRunner) -> Path:
    return Path(runner.started[-1][1])


@contextmanager
def answering(
    pending: Callable[[], list[dict[str, Any]]], answer: Callable[[str, bool], Any], approve: bool = True
) -> Iterator[list[dict[str, Any]]]:
    """The user at the page while the block runs: each approval request the agent makes is answered
    (Allow, or Deny), and kept, as the page's prompt showed it."""
    asked: list[dict[str, Any]] = []
    done = threading.Event()

    def watch() -> None:
        while not done.is_set():
            # A request answered a moment ago can still be listed until its asker moves on.
            for request in [r for r in pending() if r["id"] not in {a["id"] for a in asked}]:
                asked.append(request)
                answer(request["id"], approve)
            time.sleep(0.02)

    watcher = threading.Thread(target=watch, daemon=True)
    watcher.start()
    try:
        yield asked
    finally:
        done.set()
        watcher.join(5)


def allowing(live: Live, approve: bool = True) -> Any:  # noqa: F811
    """`answering` against the running server, as the user (no X-Actor)."""
    return answering(
        lambda: live.user("GET", "/agent/approvals")["pending"],
        lambda request, yes: live.user("POST", f"/agent/approvals/{request}", {"approve": yes}),
        approve,
    )


# ===== a document's live cells: any Python cell that calls Streamlit =====


def test_a_documents_python_cells_that_call_streamlit_are_its_live_cells(
    served: tuple[TestClient, FakeRunner],
) -> None:
    client, runner = served
    state = _open(client, document="/made/up/sales.ipynb", python="/a/notebook/python")
    assert state["kind"] == "document" and state["running"] is False and "pages" not in state
    # The import cell is plain Python: it is not live (and still runs in the kernel).
    assert [
        (p["cell"], p["name"], p["makes"], p["reads"], p["tables"], p["inputs"], p["state"])
        for p in state["pieces"]
    ] == [
        (4, "Region filter", ["region"], [], ["orders"], [], "notRun"),
        (5, "Total", [], ["region"], ["orders"], [4], "notRun"),
    ]
    app = state["app"]
    ran = _ok(client.post(f"/streamlit/apps/{app}/run", headers=AUTH))
    python, folder, path = runner.started[0]
    assert python == "/a/notebook/python" and path.startswith(f"/streamlit/live/{app}-")
    root = Path(folder)
    assert sorted(p.name for p in root.iterdir()) == [
        "app.py",
        "data",
        "home.py",
        "manifest.json",
        "piece_4_1.py",
        "piece_5_1.py",
    ]
    assert sorted(p.name for p in (root / "data").iterdir()) == ["orders.parquet"]
    alone = (root / "piece_5_1.py").read_text()
    assert "region comes from cell 4" in alone and "st.metric" in alone
    assert [p["state"] for p in ran["pieces"]] == ["current", "current"] and ran["pieces"][0][
        "preview"
    ] == f"{path}/piece-4"
    # Typed on: out of date until it runs. A cell that stops calling Streamlit is no longer live.
    typed = [CELLS[0], CELLS[1], {"cell": 5, "code": TOTAL.replace("Total", "Sum")}]
    state = _ok(client.put(f"/streamlit/apps/{app}", headers=AUTH, json={"cells": typed}))
    assert [(p["cell"], p["state"], p["code_changed"]) for p in state["pieces"]] == [
        (4, "current", False),
        (5, "outOfDate", True),
    ]
    plain = [CELLS[0], CELLS[1], {"cell": 5, "code": "total = orders['amount'].sum()"}]
    assert [
        p["cell"]
        for p in _ok(client.put(f"/streamlit/apps/{app}", headers=AUTH, json={"cells": plain}))["pieces"]
    ] == [4]
    # It has no pages: those are a Streamlit app's.
    refused = client.post(f"/streamlit/apps/{app}/pages", headers=AUTH, json={})
    assert refused.status_code == 400 and "Open a Streamlit app" in refused.text
    for bad in ({"cells": [{"cell": 4}]}, {"cells": [{"cell": 4, "code": "a"}, {"cell": 4, "code": "b"}]}):
        assert client.put(f"/streamlit/apps/{app}", headers=AUTH, json=bad).status_code == 400
    assert client.get("/streamlit/apps/nope", headers=AUTH).status_code == 404


def test_opening_a_notebook_marks_the_cells_that_call_streamlit(
    served: tuple[TestClient, FakeRunner], tmp_path: Path
) -> None:
    client, _ = served
    path = _notebook(tmp_path)
    opened = _ok(client.post("/workbench/open", headers=AUTH, json={"path": str(path)}))
    assert [(c["number"], c["kind"], c.get("live", False)) for c in opened["cells"]] == [
        (1, "code", False),
        (2, "markdown", False),
        (3, "code", True),
        (4, "code", True),
        (5, "code", False),
    ]
    assert "pages" not in opened


def test_the_pane_lists_what_an_open_canvas_links_to_and_data_ipynbs_named_cells(
    served: tuple[TestClient, FakeRunner], tmp_path: Path
) -> None:
    """2026-11-16: a canvas whose notebook no window holds showed "No cells call Streamlit"; the pane
    reads the notebooks a canvas links to from their files, as the canvas does, and a project's
    data.ipynb lists its named cells (the model a page reads) beside its Streamlit cells."""
    client, _ = served
    project = tmp_path / "shop"
    project.mkdir()
    mockups = _notebook(project, "app mockups.ipynb")  # not opened by any window
    page = {
        "name": "Overview",
        "blocks": [{"document": str(mockups), "cell": 3, "row": 1, "column": 1, "w": 6}],
    }
    assert _ok(client.get("/streamlit/cells", headers=AUTH))["documents"] == []
    _canvas(client, pages=[page])
    pane = _ok(client.get("/streamlit/cells", headers=AUTH))["documents"]
    assert [(d["title"], d["open"]) for d in pane] == [("app mockups.ipynb", False)]
    assert [c["cell"] for c in pane[0]["cells"]] == [3, 4, 2]  # the two that call Streamlit, then Text
    # The project's data.ipynb: its named cells (no Streamlit in them) are listed too; unnamed ones not.
    (project / "data.ipynb").write_text(
        notebooks.write_notebook(
            [
                notebooks.Cell("code", "import pandas as pd"),
                notebooks.Cell("code", "by_region = orders.groupby('region').sum()", name="by_region"),
            ]
        ),
        encoding="utf-8",
    )
    listed = _ok(client.get("/streamlit/cells", headers=AUTH, params={"folder": str(project)}))["documents"]
    data = next(d for d in listed if d["title"] == "data.ipynb")
    assert [(c["cell"], c["name"], c["named"]) for c in data["cells"]] == [(2, "by_region", True)]
    assert [d["title"] for d in listed].count("app mockups.ipynb") == 1  # linked and in the project: once


def test_the_streamlit_cells_pane_lists_every_cell_that_calls_streamlit_by_name(
    served: tuple[TestClient, FakeRunner], tmp_path: Path
) -> None:
    client, _ = served
    project = tmp_path / "sales"
    project.mkdir()
    named = [{"cell": 1, "code": "import pandas as pd"}, {"cell": 4, "code": FILTER, "name": "Pick a region"}]
    # An open notebook (its window sends the names with the cells), saved or not.
    opened = _open(
        client, document=str(project / "mockups.ipynb"), cells=[*named, {"cell": 5, "code": TOTAL}]
    )
    assert [p["name"] for p in opened["pieces"]] == ["Pick a region", "Total"]
    # A notebook of the project's on disk that no window holds; and one with no cell that calls Streamlit.
    on_disk = project / "more.ipynb"
    on_disk.write_text(
        notebooks.write_notebook(
            [notebooks.Cell("code", "x = 1"), notebooks.Cell("code", 'st.write("hi")', name="Hello")]
        )
    )
    (project / "plain.py").write_text("# %% [1] Just Python\nx = 1\n")
    pane = _ok(client.get("/streamlit/cells", headers=AUTH, params={"folder": str(project)}))
    assert [(d["title"], d["open"], Path(d["document"]).name) for d in pane["documents"]] == [
        ("sales.ipynb", True, "mockups.ipynb"),
        ("more.ipynb", False, "more.ipynb"),
    ]
    assert [
        (c["cell"], c["name"], c["named"], c["where"], c["makes"], c["tables"], c["reads"])
        for c in pane["documents"][0]["cells"]
    ] == [
        (4, "Pick a region", True, "mockups.ipynb @cell4", ["region"], ["orders"], []),
        (5, "Total", False, "mockups.ipynb @cell5", [], ["orders"], ["region"]),
    ]
    assert [(c["cell"], c["name"]) for c in pane["documents"][1]["cells"]] == [(2, "Hello")]
    # Without a project: the open documents only. The agent lists the same.
    assert len(_ok(client.get("/streamlit/cells", headers=AGENT))["documents"]) == 1
    # A name changes nothing a link holds: the canvas's block is called by it.
    canvas = _canvas(client)["app"]
    placed = _ok(
        client.post(
            f"/streamlit/apps/{canvas}/pages", headers=AUTH, json={"document": str(on_disk), "cell": 2}
        )
    )
    assert [(b["cell"], b["name"]) for b in placed["pages"][0]["blocks"]] == [(2, "Hello")]
    renamed = [*named[:1], {"cell": 4, "code": FILTER, "name": "Region"}, {"cell": 5, "code": TOTAL}]
    state = _ok(client.put(f"/streamlit/apps/{opened['app']}", headers=AUTH, json={"cells": renamed}))
    assert state["pieces"][0]["name"] == "Region"
    bad = [{"cell": 4, "code": FILTER, "name": "two\nlines"}]
    assert (
        client.put(f"/streamlit/apps/{opened['app']}", headers=AUTH, json={"cells": bad}).status_code == 400
    )


# ===== the canvas: blocks are links to cells =====


def test_a_canvas_holds_links_to_cells_and_reads_them_as_they_are_now(
    served: tuple[TestClient, FakeRunner], tmp_path: Path
) -> None:
    client, _ = served
    path = str(_notebook(tmp_path))
    app = _canvas(client)["app"]
    base = f"/streamlit/apps/{app}"
    page = _ok(client.post(f"{base}/pages", headers=AUTH, json={"name": "Sales overview"}))["page"]
    placed = _ok(client.post(f"{base}/pages/{page}/blocks", headers=AUTH, json={"document": path, "cell": 4}))
    assert placed["block"] == "b1"
    state = _ok(
        client.post(f"{base}/pages/{page}/blocks", headers=AUTH, json={"document": path, "cell": 3, "w": 4})
    )
    blocks = state["pages"][0]["blocks"]
    # The second goes beside the first (the row has room); each says its cell's title, where it is,
    # and what it makes and reads. From the file: the notebook is not open anywhere.
    assert [(b["id"], b["row"], b["column"], b["w"], b["name"], b["where"]) for b in blocks] == [
        ("b1", 1, 1, 6, "Total", "sales.ipynb @cell4"),
        ("b2", 1, 7, 4, "Region filter", "sales.ipynb @cell3"),
    ]
    assert (
        blocks[0]["reads"] == ["region"]
        and blocks[0]["tables"] == ["orders"]
        and blocks[1]["makes"] == ["region"]
    )
    assert state["pages"][0]["order"] == ["b2", "b1"] and state["pages"][0]["problems"] == []
    assert blocks[0]["document"] == path and blocks[0]["missing"] is None and blocks[0]["state"] == "notRun"
    # Any Python cell can be placed, one that never calls Streamlit too; a Markdown or HTML cell too
    # (text cells on the canvas, 2026-11-15). Not a SQL cell; not a missing cell.
    _ok(client.post(f"{base}/pages/{page}/blocks", headers=AUTH, json={"document": path, "cell": 5}))
    refused = client.post(f"{base}/pages/{page}/blocks", headers=AUTH, json={"document": path, "cell": 99})
    assert refused.status_code == 400 and "sales.ipynb has no cell 99 for a page" in refused.text
    missing = client.post(
        f"{base}/pages/{page}/blocks", headers=AUTH, json={"document": str(tmp_path / "no.ipynb"), "cell": 1}
    )
    assert missing.status_code == 404
    # Move: to a row of its own between the two rows; resize; the grid settles.
    moved = _ok(
        client.patch(
            f"{base}/pages/{page}/blocks/b2",
            headers=AUTH,
            json={"row": 1, "column": 3, "insert": True, "w": 8, "h": 5},
        )
    )
    assert [(b["id"], b["row"], b["column"], b["w"], b["h"]) for b in moved["pages"][0]["blocks"]] == [
        ("b2", 1, 3, 8, 5),
        ("b1", 2, 1, 6, None),
        ("b3", 3, 1, 6, None),
    ]
    assert moved["pages"][0]["rows"] == [["b2"], ["b1"], ["b3"]]
    # Onto a neighbour's columns: the neighbour goes below.
    over = _ok(client.patch(f"{base}/pages/{page}/blocks/b3", headers=AUTH, json={"row": 2, "column": 4}))
    assert over["pages"][0]["rows"] == [["b2"], ["b3"], ["b1"]]
    # Pages: add, rename, move a block to another, remove.
    second = _ok(client.post(f"{base}/pages", headers=AUTH, json={}))
    assert [p["name"] for p in second["pages"]] == ["Sales overview", "Page 2"]
    _ok(client.patch(f"{base}/pages/p2", headers=AUTH, json={"name": "Details", "index": 0}))
    sent = _ok(client.patch(f"{base}/pages/{page}/blocks/b3", headers=AUTH, json={"page": "p2"}))
    assert [(p["name"], [b["id"] for b in p["blocks"]]) for p in sent["pages"]] == [
        ("Details", ["b3"]),
        ("Sales overview", ["b2", "b1"]),
    ]
    _ok(client.delete(f"{base}/pages/p2/blocks/b3", headers=AUTH))
    gone = _ok(client.delete(f"{base}/pages/p2", headers=AUTH))
    assert [p["id"] for p in gone["pages"]] == ["p1"]
    assert client.delete(f"{base}/pages/p1/blocks/nope", headers=AUTH).status_code == 404
    listed = client.get("/streamlit/apps", headers=AUTH).json()["apps"]
    assert listed == [
        {
            "app": app,
            "kind": "canvas",
            "title": "sales",
            "document": None,
            "running": False,
            "pages": [{"id": "p1", "name": "Sales overview", "blocks": 2}],
        }
    ]
    # The notebook's Markdown cell (2, "# Sales") goes on the page too: a text block, named by its words.
    text = _ok(client.post(f"{base}/pages/{page}/blocks", headers=AUTH, json={"document": path, "cell": 2}))
    block = next(b for b in text["pages"][0]["blocks"] if b["cell"] == 2)
    assert (block["kind"], block["name"], block["makes"], block["reads"]) == ("markdown", "Sales", [], [])
    assert {b["kind"] for b in text["pages"][0]["blocks"] if b["cell"] != 2} == {"code"}


def test_play_runs_the_linked_cells_current_code_and_says_when_a_page_is_out_of_date(
    served: tuple[TestClient, FakeRunner], tmp_path: Path
) -> None:
    client, runner = served
    path = str(_notebook(tmp_path))
    app = _canvas(client)["app"]
    base = f"/streamlit/apps/{app}"
    _ok(client.post(f"{base}/pages", headers=AUTH, json={"document": path, "cell": 4, "w": 12}))
    _ok(client.post(f"{base}/pages/p1/blocks", headers=AUTH, json={"document": path, "cell": 3, "w": 4}))
    ran = _ok(client.post(f"{base}/run", headers=AUTH))
    assert ran["running"] is True and ran["problem"] is None and ran["notes"] == []
    root = _files(runner)
    # sab_lineage.py: the playing page notes each block's values for the lineage overlay (only here).
    assert sorted(p.name for p in root.iterdir()) == [
        "app.py",
        "data",
        "home.py",
        "manifest.json",
        "page_p1_1.py",
        "sab_lineage.py",
    ]
    assert pq.read_table(root / "data" / "orders.parquet").to_pydict() == ORDERS.to_pydict()
    code = (root / "page_p1_1.py").read_text()
    ast.parse(code)
    assert code.index("with _slot_b2:") < code.index("with _slot_b1:") and '"Total"' in code
    page = ran["pages"][0]
    assert page["out_of_date"] is False and page["address"] == f"{ran['path']}page-p1"
    assert [b["state"] for b in page["blocks"]] == ["current", "current"]
    # The notebook is opened in a Workbench window and a linked cell typed on, not saved: the canvas
    # reads the open document, and its page is out of date. Nothing runs by itself.
    typed = [
        {"cell": 1, "code": "import pandas as pd"},
        {"cell": 3, "code": FILTER},
        {"cell": 4, "code": TOTAL.replace('"Total"', '"Sum"')},
        {"cell": 5, "code": "threshold = 50"},
    ]
    doc = _open(client, document=path, cells=typed, unsaved=True)["app"]
    state = _ok(client.get(base, headers=AUTH))
    assert state["pages"][0]["out_of_date"] is True and state["unsaved"] == ["sales.ipynb"]
    assert [(b["id"], b["state"]) for b in state["pages"][0]["blocks"]] == [
        ("b1", "outOfDate"),
        ("b2", "current"),
    ]
    assert '"Total"' in next(root.glob("page_p1_*.py")).read_text()
    again = _ok(client.post(f"{base}/run", headers=AUTH))
    assert again["pages"][0]["out_of_date"] is False and len(runner.started) == 1  # the same process
    assert '"Sum"' in (root / "page_p1_2.py").read_text()
    # A table a block names changes in the grid: out of date again.
    grid = client.get("/grids", headers=AUTH).json()["grids"][0]["grid"]
    step = {"kind": "limit", "params": {"n": 2}}
    assert client.post(f"/grids/{grid}/steps", headers=AUTH, json={"steps": [step]}).status_code == 200
    stale = _ok(client.get(base, headers=AUTH))["pages"][0]
    assert stale["out_of_date"] is True and stale["blocks"][0]["changed"] == ["orders"]
    _ok(client.post(f"{base}/run", headers=AUTH))
    assert pq.read_table(root / "data" / "orders.parquet").num_rows == 2
    # The layout changed while the page shows: out of date until Play.
    laid = _ok(client.patch(f"{base}/pages/p1/blocks/b2", headers=AUTH, json={"w": 6}))
    assert laid["pages"][0]["out_of_date"] is True and "page_p1_4.py" not in [p.name for p in root.iterdir()]
    _ok(client.post(f"{base}/run", headers=AUTH))
    # The cell is deleted in the open notebook: the block says so, with the path and the number.
    less = [c for c in typed if c["cell"] != 4]
    _ok(client.put(f"/streamlit/apps/{doc}", headers=AUTH, json={"cells": less}))
    lost = _ok(client.get(base, headers=AUTH))["pages"][0]
    assert lost["blocks"][0]["state"] == "missing" and lost["out_of_date"] is True
    assert lost["blocks"][0]["missing"] == f"sales.ipynb has no cell 4 for a page now ({path})."
    assert lost["blocks"][0]["missing"] in lost["problems"][0]
    # The notebook closes and its file goes: every block of it says the file is missing.
    assert client.delete(f"/streamlit/apps/{doc}", headers=AUTH).status_code == 200
    Path(path).unlink()
    nowhere = _ok(client.get(base, headers=AUTH))["pages"][0]["blocks"]
    assert all(
        b["state"] == "missing" and f"{path} is missing: this block links to its cell" in b["missing"]
        for b in nowhere
    )
    ran = _ok(client.post(f"{base}/run", headers=AUTH))
    assert ran["pages"][0]["out_of_date"] is False  # it ran as it is: the page says what is missing
    assert "is missing" in next(root.glob(f"page_p1_{ran['generation']}.py")).read_text()
    # Stopped: the folder goes; the pages stay.
    stopped = _ok(client.post(f"{base}/stop", headers=AUTH))
    assert stopped["running"] is False and not root.exists() and len(stopped["pages"]) == 1


def test_the_canvas_runs_in_its_first_linked_files_own_python_and_stops_with_its_window(
    served: tuple[TestClient, FakeRunner], tmp_path: Path
) -> None:
    client, runner = served
    apps = client.app.state.ctx.streamlit  # type: ignore[attr-defined]
    path = str(_notebook(tmp_path))
    _open(client, document=path, python="/the/notebook/python", cells=[{"cell": 3, "code": FILTER}])
    app = _canvas(client)["app"]
    base = f"/streamlit/apps/{app}"
    _ok(client.post(f"{base}/pages", headers=AUTH, json={"document": path, "cell": 3}))
    ran = _ok(client.post(f"{base}/run", headers=AUTH))
    assert ran["python"] == "/the/notebook/python" and runner.started[0][0] == "/the/notebook/python"
    runner.missing = ["streamlit"]
    _ok(client.post(f"{base}/stop", headers=AUTH))
    missing = _ok(client.post(f"{base}/run", headers=AUTH))
    assert missing["problem"]["kind"] == "missing" and missing["problem"]["python"] == "/the/notebook/python"
    # The one missing-package shape (domain/packages.py): the prompt's feature and the command.
    assert missing["problem"]["feature"] == "Streamlit apps" and "streamlit" in missing["problem"]["command"]
    done = _ok(client.post(f"{base}/install", headers=AUTH))
    assert done["ok"] is True and runner.installed == [("/the/notebook/python", ["streamlit"])]
    _ok(client.post(f"{base}/run", headers=AUTH))
    folder = _files(runner)
    # Its window gone a minute: the apps go. One the agent opened (no window) stays.
    agents = client.post("/streamlit/apps", headers=AGENT, json={"canvas": True, "pages": []}).json()["app"]
    clock = [1000.0]
    apps._now = lambda: clock[0]
    assert client.portal.call(apps.stop_orphans, {"w1"}) == []  # type: ignore[union-attr]
    assert client.portal.call(apps.stop_orphans, set()) == []  # type: ignore[union-attr]
    clock[0] += 61
    assert len(client.portal.call(apps.stop_orphans, set())) == 2  # type: ignore[union-attr]
    assert not folder.exists() and runner.processes[-1].up is False
    assert [a["app"] for a in client.get("/streamlit/apps", headers=AUTH).json()["apps"]] == [agents]


def test_a_document_app_stops_with_its_kernel(served: tuple[TestClient, FakeRunner]) -> None:
    client, runner = served
    apps = client.app.state.ctx.streamlit  # type: ignore[attr-defined]
    app = _open(client, kernel="k1")["app"]
    _ok(client.post(f"/streamlit/apps/{app}/run", headers=AUTH))
    folder = _files(runner)
    assert apps.port_of(runner.started[0][2].rsplit("/", 1)[-1]) == 1
    client.portal.call(apps.kernel_stopped, "another")  # type: ignore[union-attr]
    assert runner.processes[-1].up is True
    client.portal.call(apps.kernel_stopped, "k1")  # type: ignore[union-attr]
    assert runner.processes[-1].up is False and not folder.exists()
    # Another Python chosen for the notebook: the next run starts there.
    _ok(client.post(f"/streamlit/apps/{app}/run", headers=AUTH, json={"python": "/first/python"}))
    _ok(client.post(f"/streamlit/apps/{app}/run", headers=AUTH, json={"python": "/second/python"}))
    assert [s[0] for s in runner.started] == ["/made/up/python", "/first/python", "/second/python"]


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


# ===== the app's file: saved by the Workbench, opened again =====


def test_the_apps_file_saves_links_relative_to_itself_and_opens_again(
    served: tuple[TestClient, FakeRunner], tmp_path: Path
) -> None:
    client, _ = served
    (tmp_path / "nb").mkdir()
    path = str(_notebook(tmp_path / "nb"))
    app = _canvas(client)["app"]
    base = f"/streamlit/apps/{app}"
    _ok(
        client.post(
            f"{base}/pages", headers=AUTH, json={"name": "Sales", "document": path, "cell": 4, "w": 12}
        )
    )
    state = _ok(
        client.post(
            f"{base}/pages/p1/blocks", headers=AUTH, json={"document": path, "cell": 3, "w": 4, "h": 3}
        )
    )
    target = tmp_path / "apps"
    target.mkdir()
    saved = _ok(
        client.post(
            "/workbench/save",
            headers=AUTH,
            json={"path": str(target / "sales.stapp.json"), "pages": state["pages"]},
        )
    )
    text = Path(saved["path"]).read_text()
    assert json.loads(text) == {
        "swissarmybench": "streamlit-app",
        "version": 1,
        "pages": [
            {
                "name": "Sales",
                "blocks": [
                    {
                        "document": "../nb/sales.ipynb",
                        "cell": 4,
                        "row": 1,
                        "column": 1,
                        "width": 12,
                        "height": None,
                    },
                    {
                        "document": "../nb/sales.ipynb",
                        "cell": 3,
                        "row": 2,
                        "column": 1,
                        "width": 4,
                        "height": 3,
                    },
                ],
            }
        ],
    }
    assert "st.metric" not in text and len(text.splitlines()) == 13  # no code; one block a line
    opened = _ok(client.post("/workbench/open", headers=AUTH, json={"path": saved["path"]}))
    assert opened["kind"] == "app" and [b["document"] for b in opened["pages"][0]["blocks"]] == [path, path]
    assert saved["path"] in [r["path"] for r in client.get("/workbench/home", headers=AUTH).json()["recent"]]
    # The agent opens it from its file, without a window.
    again = _ok(client.post("/streamlit/apps", headers=AGENT, json={"path": saved["path"]}))
    assert again["kind"] == "canvas" and again["title"] == "sales" and again["document"] == saved["path"]
    assert [(b["name"], b["w"], b["h"]) for b in again["pages"][0]["blocks"]] == [
        ("Total", 12, None),
        ("Region filter", 4, 3),
    ]
    # Not an app's file.
    bad = tmp_path / "bad.stapp.json"
    bad.write_text("{}")
    assert client.post("/workbench/open", headers=AUTH, json={"path": str(bad)}).status_code == 400
    # A notebook is saved without pages, whatever the page sends.
    cells = [{"kind": "streamlit", "source": FILTER, "height": 300}]
    kept = _ok(
        client.post(
            "/workbench/save",
            headers=AUTH,
            json={"path": str(tmp_path / "old.ipynb"), "cells": cells, "pages": state["pages"]},
        )
    )
    raw = json.loads(Path(kept["path"]).read_text())
    assert raw["metadata"]["swissarmybench"] == {"next_cell": 2}
    assert raw["cells"][0]["metadata"]["swissarmybench"] == {"height": 300, "number": 1}


# ===== export: a folder that runs alone =====


def test_export_writes_a_folder_that_needs_nothing_of_this_app(
    served: tuple[TestClient, FakeRunner], tmp_path: Path
) -> None:
    client, _ = served
    path = str(_notebook(tmp_path))
    app = _canvas(client)["app"]
    base = f"/streamlit/apps/{app}"
    assert (
        client.post(f"{base}/export", headers=AUTH, json={"folder": str(tmp_path / "out")}).status_code == 400
    )
    _ok(
        client.post(
            f"{base}/pages",
            headers=AUTH,
            json={"name": "Sales overview", "document": path, "cell": 4, "w": 12},
        )
    )
    _ok(client.post(f"{base}/pages/p1/blocks", headers=AUTH, json={"document": path, "cell": 3}))
    done = _ok(client.post(f"{base}/export", headers=AUTH, json={"folder": str(tmp_path / "out")}))
    out = tmp_path / "out"
    assert done["folder"] == str(out) and done["problems"] == [] and done["tables"] == ["orders"]
    assert done["files"] == [
        "README.txt",
        "app.py",
        "app_pages/sales_overview.py",
        "data/orders.parquet",
        "requirements.txt",
    ]
    assert pq.read_table(out / "data" / "orders.parquet").to_pydict() == ORDERS.to_pydict()
    ast.parse((out / "app_pages" / "sales_overview.py").read_text())
    assert client.post(f"{base}/export", headers=AUTH, json={}).status_code == 400
    assert (
        client.post(
            f"{base}/export", headers=AUTH, json={"folder": str(tmp_path / "no" / "where")}
        ).status_code
        == 404
    )


# ===== projects: data.ipynb -> data.py, the canvas -> pages/*.py; Save as =====


def test_a_new_project_starts_with_the_data_and_save_as_zips_it_without_rows(tmp_path: Path) -> None:
    csv = tmp_path / "orders.csv"
    csv.write_text("order_id,region,amount\n1,East,100\n2,West,250\n3,East,40\n4,North,75\n")
    with make_client(tmp_path / "state") as client:
        client.app.state.ctx.streamlit._runner = FakeRunner()  # type: ignore[attr-defined]
        opened = client.post("/datasets/orders/load", headers=AUTH, json={"path": str(csv)})
        assert opened.status_code == 200, opened.text
        grid = opened.json()["grid"]
        step = {"kind": "filter", "params": {"column": "amount", "op": "gt", "value": 50}}
        assert client.post(f"/grids/{grid}/steps", headers=AUTH, json={"steps": [step]}).status_code == 200
        pasted = client.post(
            "/datasets/customers/paste", headers=AUTH, content="name\tregion\nAcme\tEast\nGlobex\tWest\n"
        )
        assert pasted.status_code == 200, pasted.text
        made = _ok(
            client.post(
                "/projects",
                headers=AUTH,
                json={"folder": str(tmp_path), "name": "sales", "notebooks": ["analysis", "mockups"]},
            )
        )
        folder = tmp_path / "sales"
        assert made["folder"] == str(folder) and made["name"] == "sales"
        # The Workbench opens data.ipynb first, then the canvas, then the notebooks; data.py is an export.
        assert [Path(p).name for p in made["files"]] == [
            "data.ipynb",
            "sales.stapp.json",
            "analysis.ipynb",
            "mockups.ipynb",
        ]
        # The project's type (.sab/project.json: the base's, bi) beside its files.
        assert json.loads((folder / ".sab" / "project.json").read_text()) == {"type": "bi"}
        assert sorted(p.name for p in folder.iterdir() if not p.name.startswith(".")) == [
            "analysis.ipynb",
            "data.ipynb",
            "data.py",
            "mockups.ipynb",
            "requirements.txt",
            "sales.stapp.json",
        ]
        # data.ipynb: each open table's read-only cell. data.py: its export.
        cells, _ = notebooks.read_document((folder / "data.ipynb").read_text())
        assert [c.table for c in cells if c.role == "transformations"] == ["customers", "orders"]
        data = (folder / "data.py").read_text()
        ast.parse(data)
        assert f"orders = duckdb.read_csv({str(csv)!r}).df()" in data and '"amount" > 50' in data
        assert (
            "Acme" not in data and "# ===== FILL IN: customers =====" in data
        )  # no rows: a pasted table is a stub
        first, _ = notebooks.read_document((folder / "analysis.ipynb").read_text())
        assert first[0].source == "from data import customers, orders"
        assert (folder / "requirements.txt").read_text() == "streamlit>=1.36\npandas\nduckdb\n"
        # Made twice: refused, nothing written over.
        assert (
            client.post(
                "/projects", headers=AUTH, json={"folder": str(tmp_path), "name": "sales"}
            ).status_code
            == 409
        )
        assert (
            client.post("/projects", headers=AUTH, json={"folder": str(tmp_path), "name": "a/b"}).status_code
            == 400
        )
        again = _ok(client.post("/projects/open", headers=AUTH, json={"folder": str(folder)}))
        assert again["files"] == made["files"]
        assert client.post("/projects/open", headers=AUTH, json={"folder": str(tmp_path)}).status_code == 404
        # The user works in data.ipynb: a code cell that shapes a variable. Open in a window, not
        # saved: Export data.py takes it as it is.
        every = [
            {"kind": c.kind, "source": c.source, "role": c.role, "table": c.table, "number": c.number}
            for c in cells
        ]
        every.append(
            {
                "kind": "code",
                "source": "big = orders[orders['amount'] > 200]",
                "role": "",
                "table": None,
                "number": 50,
            }
        )
        _open(
            client,
            title="data.ipynb",
            document=str(folder / "data.ipynb"),
            cells=[{"cell": 50, "code": every[-1]["source"]}],
            every=every,
            unsaved=True,
        )
        exported = _ok(client.post("/projects/export-data", headers=AUTH, json={"folder": str(folder)}))
        assert exported["names"] == ["customers", "orders", "big"] and exported["fill_in"] == ["customers"]
        assert "big = orders[orders['amount'] > 200]" in (folder / "data.py").read_text()
        # A mock-up notebook's cells on the app's canvas; Save as.
        notebook = _notebook(
            folder,
            "mockups.ipynb",
            '# Total\nst.metric("Total", int(orders[orders["region"] == region]["amount"].sum()) + len(big))',
        )
        app = _ok(
            client.post("/streamlit/apps", headers=AUTH, json={"path": str(folder / "sales.stapp.json")})
        )["app"]
        base = f"/streamlit/apps/{app}"
        _ok(
            client.post(
                f"{base}/pages",
                headers=AUTH,
                json={"name": "Overview", "document": str(notebook), "cell": 4, "w": 12},
            )
        )
        state = _ok(
            client.post(f"{base}/pages/p1/blocks", headers=AUTH, json={"document": str(notebook), "cell": 3})
        )
        outside = _notebook(tmp_path, "elsewhere.ipynb")
        state = _ok(
            client.post(
                f"{base}/pages", headers=AUTH, json={"name": "Filter", "document": str(outside), "cell": 3}
            )
        )
        _ok(
            client.post(
                "/workbench/save",
                headers=AUTH,
                json={"path": str(folder / "sales.stapp.json"), "pages": state["pages"], "force": True},
            )
        )
        # Play writes data.py again and gives the page the names it reads from it.
        ran = _ok(client.post(f"{base}/run", headers=AUTH))
        # A page of the user's own in pages/ (and one named as a page of this app will be) stays.
        (folder / "pages").mkdir()
        (folder / "pages" / "mine.py").write_text("import streamlit as st\nst.write('mine')\n")
        (folder / "pages" / "filter.py").write_text("import streamlit as st\nst.write('my filter')\n")
        live = Path(ran["folder"])
        page = next(live.glob("page_p1_*.py")).read_text()
        assert (
            "from data import big" in page
            and 'orders = _table("orders"' in page
            and (live / "data.py").is_file()
        )
        done = _ok(client.post(f"{base}/save-as", headers=AUTH, json={"path": str(tmp_path / "sales-app")}))
        assert done["path"] == str(tmp_path / "sales-app.zip") and done["project"] == str(folder)
        assert done["files"] == [
            "README.txt",
            "data.ipynb",
            "data.py",
            "elsewhere.ipynb",
            "mockups.ipynb",
            "pages/filter.py",
            "pages/overview.py",
            "requirements.txt",
            "sales.stapp.json",
        ]
        assert done["data"] == ["orders", "big"] and done["fill_in"] == ["customers"]
        assert any("data.ipynb has changes that are not saved" in p for p in done["problems"])
        assert any("data.py cannot read customers again" in p for p in done["problems"])
        assert any(p.startswith("pages/filter.py is not a page this app saved") for p in done["problems"])
        assert (folder / "pages" / "filter.py").read_text().endswith("st.write('my filter')\n")
        assert (folder / "pages" / "mine.py").is_file()
        # The project's own exports were written again.
        overview = (folder / "pages" / "overview.py").read_text()
        ast.parse(overview)
        assert overview.startswith(
            "# Overview\n"
            "# Written from sales.stapp.json by Swiss Army Bench: change the canvas, not this file.\n"
            "import pandas as pd\nimport streamlit as st\n\nfrom data import orders, big\n"
        )
        assert sorted(p.name for p in (folder / "pages").iterdir()) == ["filter.py", "mine.py", "overview.py"]
        # A page this app saved and no longer has goes; the user's own stay.
        _ok(client.delete(f"{base}/pages/p1", headers=AUTH))
        again = _ok(client.post(f"{base}/save-as", headers=AUTH, json={"path": str(tmp_path / "again.zip")}))
        assert sorted(p.name for p in (folder / "pages").iterdir()) == ["filter.py", "mine.py"]
        assert "pages/filter.py" in again["files"] and "pages/overview.py" not in again["files"]
        with zipfile.ZipFile(done["path"]) as held:
            names = sorted(held.namelist())
            texts = {name: held.read(name).decode("utf-8") for name in names}
        assert names == done["files"]
        # No rows anywhere: not the pasted table's, not an output's. No Parquet.
        assert not any("Acme" in text or "Globex" in text for text in texts.values())
        assert not any(name.endswith(".parquet") for name in names)
        assert texts["pages/overview.py"] == overview and texts["data.py"] == (folder / "data.py").read_text()
        assert "FILL IN: data.py cannot read customers again" in texts["README.txt"]
        # The zip opens again: its canvas links to the files beside it.
        unzipped = tmp_path / "unzipped"
        with zipfile.ZipFile(done["path"]) as held:
            held.extractall(unzipped)
        back = _ok(
            client.post("/streamlit/apps", headers=AGENT, json={"path": str(unzipped / "sales.stapp.json")})
        )
        assert [[(b["name"], b["missing"]) for b in p["blocks"]] for p in back["pages"]] == [
            [("Total", None), ("Region filter", None)],
            [("Region filter", None)],
        ]
        assert [Path(b["document"]).name for p in back["pages"] for b in p["blocks"]] == [
            "mockups.ipynb",
            "mockups.ipynb",
            "elsewhere.ipynb",
        ]
        project = _ok(client.post("/projects/open", headers=AUTH, json={"folder": str(unzipped)}))
        assert [Path(p).name for p in project["files"]] == [
            "data.ipynb",
            "sales.stapp.json",
            "elsewhere.ipynb",
            "mockups.ipynb",
        ]
        # The exported modules import cleanly where there is no Streamlit: data.py as it is.
        show = "[list(data.orders['amount']), data.customers, list(data.big['region'])]"
        code = f"import json, sys\nsys.path.insert(0, sys.argv[1])\nimport data\nprint(json.dumps({show}))"
        imported = subprocess.run(  # noqa: S603 (this Python, on the unzipped project)
            [sys.executable, "-c", code, str(unzipped)],
            capture_output=True,
            text=True,
            timeout=120,
            check=False,
        )
        assert imported.returncode == 0, imported.stderr[-2000:]
        assert json.loads(imported.stdout.strip().splitlines()[-1]) == [[100, 250, 75], None, ["West"]]
        # An app that is not saved has no project to zip.
        loose = _canvas(client)["app"]
        assert (
            client.post(
                f"/streamlit/apps/{loose}/save-as", headers=AUTH, json={"path": str(tmp_path / "x.zip")}
            ).status_code
            == 409
        )


def test_a_project_from_a_connection_reads_it_again_in_a_plain_python(
    live: Live,  # noqa: F811
    tmp_path: Path,
) -> None:
    """data.py reads a connection's table again: `sab.sql` on the connection, then the grid's steps as
    one DuckDB query. It imports in a Python of its own with no Streamlit (as a notebook's kernel)."""
    database = tmp_path / "shop.sqlite"
    with sqlite3.connect(database) as made_up:
        made_up.execute("CREATE TABLE orders (order_id INTEGER, region TEXT, amount INTEGER)")
        made_up.executemany(
            "INSERT INTO orders VALUES (?, ?, ?)",
            [(1, "East", 100), (2, "West", 250), (3, "East", 40), (4, "North", 75)],
        )
    live.user("POST", "/connections", sqlite_connection(database))
    grid = live.user("POST", "/connections/Shop/open", {"table": "orders"})["grid"]
    step = {"kind": "filter", "params": {"column": "amount", "op": "gt", "value": 50}}
    live.user("POST", f"/grids/{grid}/steps", {"steps": [step]})
    made = live.user("POST", "/projects", {"folder": str(tmp_path), "name": "shop"})
    folder = Path(made["folder"])
    data = (folder / "data.py").read_text()
    ast.parse(data)
    # The connection by name (never its code or a password), then the steps as one DuckDB query.
    assert "sab.sql('Shop', " in data and '"amount" > 50' in data and "sqlite3" not in data
    assert data.index("sab.sql('Shop', ") < data.index('"amount" > 50')
    assert "# swissarmybench:" in (folder / "requirements.txt").read_text()
    code = (
        "import json, sys\nsys.path.insert(0, sys.argv[1])\nimport data\n"
        "print(json.dumps(sorted(int(a) for a in data.orders['amount'])))\n"
        "print('streamlit' in sys.modules)"
    )
    done = subprocess.run(  # noqa: S603 (this Python, on the project the test made)
        [sys.executable, "-c", code, str(folder)],
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
        env=os.environ | {"SWISSARMYBENCH_OPEN": "0"},
    )
    assert done.returncode == 0, done.stderr[-2000:]
    shown, streamlit = done.stdout.strip().splitlines()[-2:]
    assert json.loads(shown) == [75, 100, 250] and streamlit == "False"


# ===== the agent: every action is a command =====


def test_the_agent_builds_a_canvas_plays_it_and_saves_it(live: Live, tmp_path: Path) -> None:  # noqa: F811
    command("datasets_paste", name="orders", text="order_id\tregion\tamount\n1\tEast\t100\n2\tWest\t250\n")
    path = str(_notebook(tmp_path))
    app = command("streamlit_open")["app"]
    page = command("streamlit_page_add", app=app, name="Sales")["page"]
    command("streamlit_block_place", app=app, page=page, document=path, cell=4, w=12)
    placed = command("streamlit_block_place", app=app, page=page, document=path, cell=3, row=1, column=1, w=4)
    assert placed["block"] == "b2" and placed["pages"][0]["rows"] == [["b2"], ["b1"]]
    moved = command("streamlit_block_change", app=app, page=page, block="b2", row=2, column=9, h=4)
    # The moved block keeps its place; the full-width one it would lie on goes below.
    assert [(b["id"], b["row"], b["column"], b["h"]) for b in moved["pages"][0]["blocks"]] == [
        ("b2", 1, 9, 4),
        ("b1", 2, 1, None),
    ]
    fitted = command("streamlit_block_change", app=app, page=page, block="b2", h=0)
    assert fitted["pages"][0]["blocks"][0]["h"] is None
    command("streamlit_page_add", app=app)
    command("streamlit_page_change", app=app, page="p2", name="Spare")
    command("streamlit_block_change", app=app, page=page, block="b2", to_page="p2")
    command("streamlit_block_remove", app=app, page="p2", block="b2")
    assert [p["name"] for p in command("streamlit_page_remove", app=app, page="p2")["pages"]] == ["Sales"]
    saved = command("streamlit_save", app=app, path=str(tmp_path / "sales"))
    assert saved["path"] == str(tmp_path / "sales.stapp.json")
    assert command("streamlit_app", app=app)["document"] == saved["path"]
    assert [a["kind"] for a in command("streamlit_apps")["apps"]] == ["canvas"]
    ran = command("streamlit_run", app=app)
    if ran["problem"] is not None:  # this Python has no Streamlit: the agent is told how to install
        assert (
            ran["problem"]["kind"] == "missing" and command("streamlit_address", app=app)["running"] is False
        )
    # The export copies the rows: it waits for the user's Allow (the owner, 2026-11-15).
    with allowing(live) as asked:
        out = command("streamlit_export", app=app, folder=str(tmp_path / "out"))
    assert len(out["problems"]) == 1 and (tmp_path / "out" / "app.py").is_file()  # the filter was taken off
    assert [(a["action"], a["dataset"]) for a in asked] == [("export the Streamlit app", "sales.stapp.json")]
    # orders was pasted: its rows are written out in data.ipynb's cell, so New project asks too.
    with allowing(live) as asked:
        made = command("project_new", folder=str(tmp_path), name="proj", app=False, notebooks=["analysis"])
    assert [a["action"] for a in asked] == ["make the project"] and "orders (2 rows)" in asked[0]["detail"]
    assert [Path(p).name for p in made["files"]] == ["data.ipynb", "analysis.ipynb"]
    assert command("project_files", folder=made["folder"])["files"] == made["files"]
    assert command("project_export_data", folder=made["folder"])["names"] == ["orders"]
    # Save as makes the app's folder a project first: its data.ipynb holds the pasted rows.
    with allowing(live) as asked:
        zipped = command("streamlit_save_as", app=app, path=str(tmp_path / "done.zip"))
    assert [a["action"] for a in asked] == ["zip the Streamlit app"]
    assert (
        "data.py" in zipped["files"]
        and "pages/sales.py" in zipped["files"]
        and (tmp_path / "data.ipynb").is_file()
    )
    command("streamlit_stop", app=app)
    command("streamlit_close", app=app)
    with pytest.raises(CommandError, match="not open"):
        command("streamlit_app", app=app)


def test_running_a_notebook_as_the_agent_leaves_the_cells_that_call_streamlit_out(
    live: Live,  # noqa: F811
    tmp_path: Path,
) -> None:
    path = _notebook(tmp_path)
    done = data_of(execute("workbench_run_notebook", {"path": str(path)}))
    command("workbench_kernel", kernel=done["kernel"], action="stop")
    # Cells 1 and 5 ran in the kernel; the two that call Streamlit did not (they would only warn).
    assert done["cells_run"] == 2
    cells, _ = notebooks.read_document(path.read_text())
    assert [c.execution_count is not None for c in cells if c.kind == "code"] == [True, False, False, True]


# ===== the door the live pages come through =====


def test_live_pages_need_the_apps_own_secret_and_only_this_computer(
    served: tuple[TestClient, FakeRunner],
) -> None:
    client, _ = served
    app = _open(client)["app"]
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
    # The page designer's window is gone: the canvas is a Workbench document.
    assert client.get("/designer").status_code in (401, 404)
    # A stopped app's address leads nowhere.
    client.post(f"/streamlit/apps/{app}/stop", headers=AUTH)
    assert client.get(f"{path}piece-4").status_code == 404


def test_the_frame_policy_of_the_workbench_is_as_it_was() -> None:
    """The live pages show inside the Workbench without weakening its policy: frames from this
    server only, as before."""
    static = Path(__file__).parents[1] / "web" / "static"
    text = (static / "workbench.html").read_text(encoding="utf-8")
    assert "frame-src 'self';" in text and "127.0.0.1:" not in text
    assert not (static / "designer.html").exists()


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


MULTI_PAGE = """
import json, sys
from streamlit.testing.v1 import AppTest
at = AppTest.from_file(sys.argv[1], default_timeout=60).run()
def seen():
    return {
        "errors": [e.value for e in at.error] + [str(e.value) for e in at.exception],
        "metrics": [m.value for m in at.metric],
        "boxes": [w.key for w in at.selectbox],
    }
out = {"first": seen()}
at.selectbox[0].set_value("West").run()
out["picked"] = seen()
at.switch_page("pages/filter_only.py").run()
out["second"] = seen()
print(json.dumps(out))
"""


def _app_test(python: str, page: Path, pick: str, cwd: Path | None = None) -> dict[str, Any]:
    done = subprocess.run(  # noqa: S603 (the test's own Streamlit Python)
        [python, "-c", APP_TEST, str(page), pick],
        capture_output=True,
        text=True,
        timeout=180,
        check=False,
        cwd=cwd,
    )
    assert done.returncode == 0, done.stderr[-2000:]
    return dict(json.loads(done.stdout.strip().splitlines()[-1]))


@needs_streamlit
def test_the_real_streamlit_runs_the_canvas_the_live_cells_the_export_and_the_saved_pages(
    live: Live,  # noqa: F811
    tmp_path: Path,
) -> None:
    assert STREAMLIT_PYTHON is not None
    csv = tmp_path / "orders.csv"
    csv.write_text("order_id,region,amount\n1,East,100\n2,West,250\n3,East,40\n4,North,75\n")
    grid = command("datasets_load", name="orders", path=str(csv))["grid"]
    project = command("project_new", folder=str(tmp_path), name="sales", notebooks=["mockups"])
    folder = Path(project["folder"])
    notebook = _notebook(folder, "mockups.ipynb")
    # The notebook's own live cells, as the Workbench window shows them in their cells.
    document = live.user(
        "POST",
        "/streamlit/apps",
        {
            "title": "mockups.ipynb",
            "document": str(notebook),
            "python": STREAMLIT_PYTHON,
            "cells": [{"cell": 3, "code": FILTER}, {"cell": 4, "code": TOTAL}],
        },
    )["app"]
    app = command("streamlit_open", path=str(folder / "sales.stapp.json"))["app"]
    # The filter placed BELOW the total.
    command("streamlit_page_add", app=app, name="Sales overview")
    command("streamlit_block_place", app=app, page="p1", document=str(notebook), cell=4, w=12)
    command("streamlit_block_place", app=app, page="p1", document=str(notebook), cell=3, w=4)
    command("streamlit_save", app=app)
    ran = command("streamlit_run", app=app)
    assert ran["running"] is True and ran["problem"] is None, ran["problem"]
    assert ran["python"] == STREAMLIT_PYTHON  # the linked notebook's own
    alone = command("streamlit_run", app=document)
    try:
        where = command("streamlit_address", app=app)
        assert where["running"] is True and set(where["pages"]) == {"Sales overview"}
        cells = command("streamlit_address", app=document)["cells"]
        # The process listens on 127.0.0.1 only, and answers through this server under the secret.
        assert "port" not in json.dumps(live.user("GET", f"/streamlit/apps/{app}"))
        for address in (where["app"], where["pages"]["Sales overview"], cells["3"], cells["4"]):
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
        # The page as Streamlit runs it: the filter drives the total, though it sits below it.
        temporary = Path(ran["folder"])
        assert temporary.name.startswith("swissarmybench-streamlit-")
        page = _app_test(STREAMLIT_PYTHON, next(temporary.glob("page_p1_*.py")), "West")
        assert page["errors"] == [] and page["options"] == ["East", "North", "West"]
        assert page["first"] == "140" and page["second"] == "250" and page["keys"] == ["b2_1"]
        # The page noted each block's values as it ran, for the lineage overlay (the filter's choice too).
        noted = json.loads((temporary / "lineage-p1.json").read_text(encoding="utf-8"))
        assert noted["blocks"]["b2"]["values"]["region"]["text"] == "West"
        single = _app_test(STREAMLIT_PYTHON, next(Path(alone["folder"]).glob("piece_4_*.py")), "North")
        assert single["errors"] == [] and single["first"] == "140" and single["second"] == "75"
        # A grid step: out of date; Play: the new data.
        command("steps_add", grid=grid, kind="filter", params={"column": "amount", "op": "gt", "value": 50})
        assert command("streamlit_app", app=app)["pages"][0]["out_of_date"] is True
        again = command("streamlit_run", app=app)
        assert again["pages"][0]["out_of_date"] is False
        fresh = _app_test(STREAMLIT_PYTHON, next(temporary.glob(f"page_p1_{again['generation']}.py")), "West")
        assert (
            fresh["options"] == ["East", "North", "West"]
            and fresh["first"] == "100"
            and fresh["second"] == "250"
        )
        # A second page; the export, run by Streamlit with nothing of this app beside it; Save as.
        command("streamlit_page_add", app=app, name="Filter only")
        command("streamlit_block_place", app=app, page="p2", document=str(notebook), cell=3)
        with allowing(live) as asked:
            out = command("streamlit_export", app=app, folder=str(tmp_path / "exported"))
        assert out["problems"] == [] and [a["action"] for a in asked] == ["export the Streamlit app"]
        # The project has its data.ipynb, which reads a file: Save as writes no rows and asks nothing.
        zipped = command("streamlit_save_as", app=app, path=str(tmp_path / "sales.zip"))
        assert zipped["problems"] == [] and zipped["fill_in"] == []
    finally:
        stopped = command("streamlit_stop", app=app)
        command("streamlit_close", app=document)
    assert stopped["running"] is False and not temporary.exists()
    assert _fetch(where["app"])[0] == 404
    # The saved pages run as pages of another app: they import their table from data.py, which
    # reads the file again and applies the grid's step. Under Streamlit data.py's load is kept.
    unzipped = tmp_path / "unzipped"
    with zipfile.ZipFile(zipped["path"]) as held:
        held.extractall(unzipped)
    saved = _app_test(STREAMLIT_PYTHON, unzipped / "pages" / "sales_overview.py", "West", cwd=unzipped)
    assert saved["errors"] == [] and saved["first"] == "100" and saved["second"] == "250"
    assert "cache_resource" in (unzipped / "data.py").read_text()
    # And dropped into a multi-page app of the user's own: its st.navigation over the saved pages, each
    # page run in turn in one session (their widgets' keys do not clash; data.py is loaded once).
    (unzipped / "app.py").write_text(
        "import streamlit as st\n\nst.navigation([\n"
        '    st.Page("pages/sales_overview.py", title="Sales overview", default=True),\n'
        '    st.Page("pages/filter_only.py", title="Filter only"),\n'
        "]).run()\n"
    )
    walked = subprocess.run(  # noqa: S603 (the test's own Streamlit Python)
        [STREAMLIT_PYTHON, "-c", MULTI_PAGE, str(unzipped / "app.py")],
        capture_output=True,
        text=True,
        timeout=180,
        check=False,
        cwd=unzipped,
    )
    assert walked.returncode == 0, walked.stderr[-2000:]
    assert json.loads(walked.stdout.strip().splitlines()[-1]) == {
        "first": {"errors": [], "metrics": ["100"], "boxes": ["b2_1"]},
        "picked": {"errors": [], "metrics": ["250"], "boxes": ["b2_1"]},
        "second": {"errors": [], "metrics": [], "boxes": ["b3_1"]},
    }
    exported = tmp_path / "exported"
    module = _app_test(STREAMLIT_PYTHON, exported / "app_pages" / "sales_overview.py", "West")
    assert module["errors"] == [] and module["first"] == "100" and module["second"] == "250"
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port = int(probe.getsockname()[1])
    environ = {k: v for k, v in os.environ.items() if not k.startswith(("SWISSARMYBENCH", "PYTHONPATH"))}
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
        "from swissarmybench.server import streamlit_apps\n"
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


# ===== Markdown and HTML cells on a canvas (text cells on the canvas, 2026-11-15) =====

KPI_TEXT = "## Sales in {{ region }}\nTotal for {{ region }}: **{{ total }}**"
KPI_HTML = (
    '<div class="kpi"><b>{{ total }}</b> in {{ region }}</div><script>window.sabTotal = {{ total }};</script>'
)
TOTAL_VALUE = '# Total value\ntotal = int(orders[orders["region"] == region]["amount"].sum())'
HOSTILE_VALUE = "</script><b>*x*</b>"


def _text_notebook(folder: Path) -> Path:
    """A saved notebook: the filter (1), the total (2), a Markdown cell (3), an HTML cell (4), a note (5)."""
    cells = [
        notebooks.Cell("code", FILTER),
        notebooks.Cell("code", TOTAL_VALUE),
        notebooks.Cell("markdown", KPI_TEXT),
        notebooks.Cell("html", KPI_HTML, name="KPI card"),
        notebooks.Cell("markdown", "Made-up figures, for testing."),
    ]
    path = folder / "story.ipynb"
    path.write_text(notebooks.write_notebook(cells), encoding="utf-8")
    return path


def test_markdown_and_html_cells_go_on_a_page_by_the_canvas_commands(
    served: tuple[TestClient, FakeRunner], tmp_path: Path
) -> None:
    client, runner = served
    path = str(_text_notebook(tmp_path))
    app = _canvas(client)["app"]
    base = f"/streamlit/apps/{app}"
    page = _ok(client.post(f"{base}/pages", headers=AUTH, json={"name": "Overview"}))["page"]
    # The text first on the page, the filter last: the run order still puts the filter first.
    for cell in (3, 4, 2, 1):
        _ok(client.post(f"{base}/pages/{page}/blocks", headers=AUTH, json={"document": path, "cell": cell}))
    state = _ok(client.get(base, headers=AUTH))["pages"][0]
    blocks = {b["cell"]: b for b in state["blocks"]}
    assert [(blocks[c]["kind"], blocks[c]["name"]) for c in (3, 4, 1)] == [
        ("markdown", "Sales in {{ region }}"),
        ("html", "KPI card"),
        ("code", "Region filter"),
    ]
    assert blocks[3]["reads"] == ["region", "total"] and blocks[3]["makes"] == []
    assert blocks[4]["reads"] == ["total", "region"]
    ids = {c: blocks[c]["id"] for c in blocks}
    assert state["order"] == [ids[1], ids[2], ids[3], ids[4]] and state["problems"] == []
    # Play: the page's code, and the rules that fill the names beside it (nothing new to install).
    ran = _ok(client.post(f"{base}/run", headers=AUTH))
    root = _files(runner)
    code = next(root.glob("page_p1_*.py")).read_text(encoding="utf-8")
    assert "st.markdown(_sab_text.page_markdown(" in code and "unsafe_allow_javascript=True" in code
    helper = (root / "sab_text.py").read_text(encoding="utf-8")
    assert helper.startswith("# Written by Swiss Army Bench") and "def page_markdown" in helper
    assert all(b["state"] == "current" for b in ran["pages"][0]["blocks"])
    # A plain Markdown cell needs no copy; an empty one is not offered.
    second = _ok(client.post(f"{base}/pages", headers=AUTH, json={"name": "Notes"}))["page"]
    _ok(client.post(f"{base}/pages/{second}/blocks", headers=AUTH, json={"document": path, "cell": 5}))
    notes = _ok(client.get(base, headers=AUTH))["pages"][1]["blocks"][0]
    assert (notes["kind"], notes["name"], notes["reads"]) == ("markdown", "Made-up figures, for testing.", [])


def test_a_windows_markdown_and_html_cells_are_listed_under_text_and_never_live(
    served: tuple[TestClient, FakeRunner], tmp_path: Path
) -> None:
    client, _ = served
    document = str(tmp_path / "story.ipynb")
    cells = [
        {"cell": 1, "code": FILTER},
        {"cell": 2, "code": KPI_TEXT, "kind": "markdown"},
        {"cell": 3, "code": KPI_HTML, "kind": "html", "name": "KPI card"},
        {"cell": 4, "code": "   ", "kind": "markdown"},
    ]
    opened = _open(client, document=document, cells=cells)
    # Only the Python cell that calls Streamlit is live in its cell; the text cells are not.
    assert [p["cell"] for p in opened["pieces"]] == [1]
    pane = _ok(client.get("/streamlit/cells", headers=AUTH))["documents"][0]["cells"]
    assert [(c["cell"], c["kind"], c["name"], c["reads"]) for c in pane] == [
        (1, "code", "Region filter", []),
        (2, "markdown", "Sales in {{ region }}", ["region", "total"]),
        (3, "html", "KPI card", ["total", "region"]),
    ]
    # A script's HTML cell sends its lines; the server reads the HTML from its string.
    script = [{"cell": 7, "code": 'r"""\n<p>{{ region }}</p>\n"""', "kind": "html", "form": "script"}]
    state = _ok(client.put(f"/streamlit/apps/{opened['app']}", headers=AUTH, json={"cells": script}))
    assert state["pieces"] == []
    listed = _ok(client.get("/streamlit/cells", headers=AUTH))["documents"][0]["cells"]
    assert [(c["cell"], c["kind"], c["reads"]) for c in listed] == [(7, "html", ["region"])]
    bad = [{"cell": 8, "code": "x", "kind": "sql"}]
    assert (
        client.put(f"/streamlit/apps/{opened['app']}", headers=AUTH, json={"cells": bad}).status_code == 400
    )


TEXT_APP_TEST = """
import json, sys
from streamlit.testing.v1 import AppTest
at = AppTest.from_file(sys.argv[1], default_timeout=60).run()
def seen():
    return {
        "errors": [e.value for e in at.error] + [str(e.value) for e in at.exception],
        "markdown": [m.value for m in at.markdown],
        "html": [[h.proto.body, h.proto.unsafe_allow_javascript] for h in at.get("html")],
    }
out = {"first": seen()}
at.selectbox[0].set_value(sys.argv[2]).run()
out["picked"] = seen()
print(json.dumps(out))
"""


def _text_app_test(page: Path, pick: str, cwd: Path) -> dict[str, Any]:
    assert STREAMLIT_PYTHON is not None
    done = subprocess.run(  # noqa: S603 (the test's own Streamlit Python)
        [STREAMLIT_PYTHON, "-c", TEXT_APP_TEST, str(page), pick],
        capture_output=True,
        text=True,
        timeout=180,
        check=False,
        cwd=cwd,
    )
    assert done.returncode == 0, done.stderr[-2000:]
    return dict(json.loads(done.stdout.strip().splitlines()[-1]))


@needs_streamlit
def test_the_real_streamlit_fills_a_markdown_and_an_html_block_from_a_filter(
    live: Live,  # noqa: F811
    tmp_path: Path,
) -> None:
    assert STREAMLIT_PYTHON is not None
    csv = tmp_path / "orders.csv"
    csv.write_text("order_id,region,amount\n1,East,100\n2,West,250\n3,East,40\n4,North,75\n")
    command("datasets_load", name="orders", path=str(csv))
    project = command("project_new", folder=str(tmp_path), name="story", notebooks=["mockups"])
    folder = Path(project["folder"])
    notebook = folder / "story.ipynb"
    markdown, card, hostile = (
        KPI_TEXT + "\n\nNote: {{ hostile }}",
        KPI_HTML + "<p>{{ hostile }}</p>",
        f"hostile = {HOSTILE_VALUE!r}",
    )
    cells = [
        notebooks.Cell("code", FILTER),
        notebooks.Cell("code", TOTAL_VALUE),
        notebooks.Cell("markdown", markdown),
        notebooks.Cell("html", card, name="KPI card"),
        notebooks.Cell("code", hostile),
    ]
    notebook.write_text(notebooks.write_notebook(cells), encoding="utf-8")
    # The notebook is open in a window (its Python: the test's Streamlit one), which sends its cells.
    sent = [
        {"cell": 1, "code": FILTER},
        {"cell": 2, "code": TOTAL_VALUE},
        {"cell": 3, "code": markdown, "kind": "markdown"},
        {"cell": 4, "code": card, "kind": "html", "name": "KPI card"},
        {"cell": 5, "code": hostile},
    ]
    window = {"title": "story.ipynb", "document": str(notebook), "python": STREAMLIT_PYTHON, "cells": sent}
    document = live.user("POST", "/streamlit/apps", window)["app"]
    app = command("streamlit_open", path=str(folder / "story.stapp.json"))["app"]
    command("streamlit_page_add", app=app, name="Overview")
    # The golden rule: the agent places them with the canvas's own commands.
    for cell in (3, 4, 1, 2, 5):
        command("streamlit_block_place", app=app, page="p1", document=str(notebook), cell=cell)
    command("streamlit_save", app=app)
    ran = command("streamlit_run", app=app)
    try:
        assert ran["running"] is True and ran["problem"] is None, ran["problem"]
        temporary = Path(ran["folder"])
        seen = _text_app_test(next(temporary.glob("page_p1_*.py")), "West", temporary)
        # Choosing a region changes the Markdown's text and the HTML's; a value is text, never markup.
        first, picked = seen["first"], seen["picked"]
        assert first["errors"] == [] and picked["errors"] == []
        assert first["markdown"][0].startswith("## Sales in East\nTotal for East: **140**")
        assert picked["markdown"][0].startswith("## Sales in West\nTotal for West: **250**")
        assert "&lt;/script&gt;&lt;b&gt;\\*x\\*&lt;/b&gt;" in picked["markdown"][0]
        body, scripts = picked["html"][0]
        assert scripts is True and "<b>250</b> in West" in body and "window.sabTotal = 250;" in body
        assert "<p>&lt;/script&gt;&lt;b&gt;*x*&lt;/b&gt;</p>" in body
        with allowing(live):
            exported = command("streamlit_export", app=app, folder=str(tmp_path / "exported"))
        zipped = command("streamlit_save_as", app=app, path=str(tmp_path / "story.zip"))
    finally:
        command("streamlit_stop", app=app)
        command("streamlit_close", app=document)
    # The export runs alone: its pages import sab_text.py beside app.py; nothing new is needed.
    out = Path(exported["folder"])
    assert (out / "sab_text.py").is_file() and "streamlit>=1.52" in (out / "requirements.txt").read_text()
    assert "nothing new installed" in (out / "README.txt").read_text()
    alone = _text_app_test(out / "app_pages" / "overview.py", "North", out)
    assert alone["picked"]["errors"] == [] and alone["picked"]["markdown"][0].startswith("## Sales in North")
    # The saved project's pages: sab_text.py beside data.py, and the README says nothing new is needed.
    unzipped = tmp_path / "unzipped"
    with zipfile.ZipFile(zipped["path"]) as held:
        held.extractall(unzipped)
        names = held.namelist()
    assert "sab_text.py" in names and "nothing new installed" in (unzipped / "README.txt").read_text()
    saved = _text_app_test(unzipped / "pages" / "overview.py", "West", unzipped)
    assert saved["picked"]["errors"] == [] and "Total for West: **250**" in saved["picked"]["markdown"][0]
    assert saved["picked"]["html"][0][1] is True
