"""One Python per project (the owner, 2026-11-21; Plans/environment.plan.md, step 4): the project's own
`.venv` made by the app (stood in: tests/libraries_standin.py, nothing downloaded), the ONE session every
notebook and script of the project runs in (real kernels, this test's own Python), a notebook's older
environment of its own read once and offered, and a loose file's kernel as before. Made-up data only."""

from __future__ import annotations

import io
import json
import sys
import time
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pyarrow as pa
import pyarrow.ipc as ipc
import pytest
from starlette.testclient import TestClient

from swissarmybench.adapters import environment as environment_files
from swissarmybench.cli import commands
from swissarmybench.domain import project_python as rules
from swissarmybench.server import environments
from tests import libraries_standin
from tests.conftest import AGENT, AUTH, PORT, make_client, push


def ok(response: Any) -> Any:
    assert response.status_code == 200, response.text
    return response.json()


def run(client: TestClient, kernel: str, code: str, **extra: Any) -> list[dict[str, Any]]:
    answer = client.post(f"/workbench/kernels/{kernel}/execute", json={"code": code, **extra}, headers=AUTH)
    assert answer.status_code == 200, answer.text
    return [json.loads(line) for line in answer.text.splitlines() if line]


def text_of(items: list[dict[str, Any]]) -> str:
    return "".join(str(i.get("text", "")) for i in items if i.get("output_type") == "stream")


def start(client: TestClient, **body: Any) -> dict[str, Any]:
    started: dict[str, Any] = ok(client.post("/workbench/kernels", json=body, headers=AUTH))
    return started


@pytest.fixture
def client(tmp_path: Path) -> Iterator[TestClient]:
    with make_client(tmp_path) as test_client:
        yield test_client


@pytest.fixture
def project(client: TestClient, tmp_path: Path) -> Path:
    folder = tmp_path / "work" / "Shop"
    ok(client.post("/project/new", json={"path": str(folder)}, headers=AUTH))
    (folder / "load.py").write_text("orders_loaded = 3\n", encoding="utf-8")
    (folder / "report.ipynb").write_text(
        json.dumps({"nbformat": 4, "nbformat_minor": 5, "metadata": {}, "cells": []}), encoding="utf-8"
    )
    return folder


# ===== the rules =====


def test_a_document_is_the_projects_when_its_path_is_inside_the_folder() -> None:
    assert rules.in_project("/work/Shop/data.ipynb", "/work/Shop")
    assert rules.in_project("C:\\Work\\Shop\\scripts\\etl\\load.py", "c:/work/shop/")
    assert not rules.in_project("/work/Shop", "/work/Shop")  # the folder itself is no document
    assert not rules.in_project("/work/Shopping/data.ipynb", "/work/Shop")
    assert not rules.in_project("/work/Shop/../Other/x.py", "/work/Shop")
    assert not rules.in_project(None, "/work/Shop") and not rules.in_project("/work/Shop/x.py", None)


def test_the_venv_is_made_with_the_kernel_the_excel_readers_and_requirements() -> None:
    text = (
        "# the shop's libraries\npandas==2.3.3\nduckdb >= 1.4\n-r other.txt\n./local/wheel.whl\n"
        "openpyxl==3.1.5\n"
    )
    assert rules.venv_packages(text) == [
        "ipykernel",
        "openpyxl==3.1.5",
        "xlrd",
        "pandas==2.3.3",
        "duckdb>=1.4",
    ]
    assert rules.venv_packages("") == ["ipykernel", "openpyxl", "xlrd"]


def test_the_libraries_someone_chose_are_the_ones_no_other_needs() -> None:
    requires = {
        "pandas": ["numpy>=1.26", "python-dateutil>=2.8"],
        "numpy": [],
        "python-dateutil": ["six>=1.5"],
        "six": [],
        "ipykernel": ["traitlets"],
        "traitlets": [],
        "pip": [],
        "Plotly": ["narwhals"],
        "narwhals": [],
    }
    there = rules.chosen(requires)
    assert there == ["pandas", "Plotly"]
    # What the project lacks: not what requirements.txt names, nor what its Python already has.
    assert rules.offered(there, "pandas==2.3.3\n", []) == ["Plotly"]
    assert rules.offered(there, "", ["plotly", "numpy"]) == ["pandas"]
    said = rules.offer_words("/work/Shop/report.ipynb", ["Plotly"])
    assert said.startswith("report.ipynb had its own environment.") and "1 library (Plotly)" in said
    assert "already has its libraries" in rules.offer_words("/work/Shop/report.ipynb", [])


def test_each_state_says_one_plain_line() -> None:
    assert rules.State(None, sys.executable, False).status == "none"
    making = rules.State("/work/Shop", sys.executable, False, making=True)
    assert making.status == "making" and "app's own Python until it is ready" in making.words
    assert rules.State("/work/Shop", "/work/Shop/.venv/bin/python", True).status == "ready"
    failed = rules.State("/work/Shop", sys.executable, False, problem="no uv")
    assert failed.status == "failed" and "Try again" in failed.words
    assert rules.made_words(0, "") is None
    assert "over 10 minutes" in str(rules.made_words(None, ""))
    assert "No interpreter" in str(rules.made_words(2, "line\nerror: No interpreter found"))
    for words in (rules.SESSION_WORDS, rules.RESTARTED_WORDS, rules.READY_WORDS):
        assert "kernel" not in words.lower()  # the owner reads these: a session, never a kernel


# ===== one session for the whole project =====


def test_every_document_of_the_project_runs_in_one_session(client: TestClient, project: Path) -> None:
    notebook, script = str(project / "report.ipynb"), str(project / "load.py")
    opened = ok(client.post("/workbench/open", json={"path": notebook}, headers=AUTH))
    assert opened["session"]["shared"] is True and "One Python session" in opened["session"]["words"]
    first = start(client, path=notebook, window="w1")
    second = start(client, path=script, window="w2")
    untitled = start(client, project=True, window="w1")
    assert first["kernel"] == second["kernel"] == untitled["kernel"]
    assert first["session"]["shared"] is True
    kernel = first["kernel"]
    # One namespace: what the notebook makes, the script reads; the session runs in the project's folder.
    run(client, kernel, "shop_total = 41 + 1", document=notebook)
    said = run(client, kernel, "import os\nprint(shop_total, os.path.basename(os.getcwd()))", document=script)
    assert text_of(said).split() == ["42", "Shop"]
    # Run file: the script's own names land in the same session.
    run(client, kernel, "", kind="file", path=script)
    assert "3" in text_of(run(client, kernel, "print(orders_loaded)"))
    # Closing one document leaves the session running for the others.
    left = ok(client.delete(f"/workbench/kernels/{kernel}", headers=AUTH))
    assert left == {"ok": True, "stopped": False, "session": True}
    assert "42" in text_of(run(client, kernel, "print(shop_total)"))
    # One session, so one row for the name in the Environment.
    time.sleep(0.2)
    listed = ok(client.get("/environment", headers=AUTH))
    names = [i["name"] for i in listed["items"] if i["kind"] == "variable"]
    assert names.count("shop_total") == 1
    # Restart is the session's: every document's variables go, and each window is told.
    with client.websocket_connect("/ws?catalog=1", headers=AUTH | {"Host": f"127.0.0.1:{PORT}"}) as socket:
        ok(client.post(f"/workbench/kernels/{kernel}/restart", headers=AUTH))
        heard = socket.receive_json()
        while heard.get("type") != "session_restarted":
            heard = socket.receive_json()
    assert heard["kernel"] == kernel and "every variable is cleared" in heard["words"]
    again = run(client, kernel, "print('shop_total' in globals())", document=script)
    assert "False" in text_of(again)
    # The session is the project's: it ends when the project closes, and a run then starts a new one.
    ok(client.post("/project/close", json={"discard": True}, headers=AUTH))
    gone = client.post(f"/workbench/kernels/{kernel}/execute", json={"code": "1"}, headers=AUTH)
    assert gone.status_code == 404


def test_the_run_says_which_document_it_is_for(client: TestClient, project: Path) -> None:
    """A connection's slot and a table a run sends are counted as the document whose code runs, not the
    first document that joined the session."""
    notebook, script = str(project / "report.ipynb"), str(project / "load.py")
    kernel = start(client, path=notebook)["kernel"]
    start(client, path=script)
    workbench = client.app.state.ctx.workbench  # type: ignore[attr-defined]
    assert workbench.document_of(kernel) == notebook
    run(client, kernel, "x = 1", document=script)
    assert workbench.document_of(kernel) == script and workbench.runner_of(kernel) == (
        "user",
        "Script load.py",
    )
    assert workbench.kernel_for(notebook) == kernel and workbench.kernel_for(script) == kernel
    # One session a project: a document of the project that never started it is still its (the sweep,
    # 2026-11-22: the debugger refused a project's script with "run it once first" while the session ran);
    # a file outside the project is not.
    other = str(project / "scripts" / "pricing.py")
    assert workbench.kernel_for(other) == kernel
    assert workbench.kernel_for(str(project.parent / "loose.py")) is None
    assert workbench.running_documents() == sorted([notebook, script])
    assert workbench.kernel_count() == 1


def test_the_session_is_no_windows_a_popped_out_document_keeps_it(client: TestClient, project: Path) -> None:
    """A document popped out into a window of its own takes its kernel with it; the project's one session
    is no window's, so that window closing (or a minute without it) never stops it for the others."""
    import asyncio

    notebook = str(project / "report.ipynb")
    kernel = start(client, path=notebook, window="main-window")["kernel"]
    run(client, kernel, "kept = 7", document=notebook)
    document = {"kind": "notebook", "path": notebook, "cells": []}
    handed = ok(
        client.post("/workbench/handoffs", json={"document": document, "kernel": kernel}, headers=AUTH)
    )
    taken = ok(
        client.post(
            f"/workbench/handoffs/{handed['id']}/take",
            json={"window": "popped-window", "page": "notebooks"},
            headers=AUTH,
        )
    )
    assert taken["kernel"] == kernel
    workbench = client.app.state.ctx.workbench  # type: ignore[attr-defined]
    workbench._now = lambda: 10_000_000_000.0  # long after: every window that ever held it is gone
    assert asyncio.run(workbench.stop_orphans(set())) == []
    assert asyncio.run(workbench.stop_orphans(set())) == []
    assert workbench.session_kernel() == kernel
    assert "7" in text_of(run(client, kernel, "print(kept)"))


def test_a_table_the_session_sends_names_the_document_whose_code_made_it() -> None:
    """A project's documents share one kernel, so the kernel alone no longer says which document a table's
    read-only cell belongs in: the document the run was for is kept as the table arrives."""
    from swissarmybench.domain.table_cells import Origin
    from swissarmybench.services.table_cells import Origins

    running = {"k1": "/work/Shop/load.py"}
    origins = Origins()
    origins.document_of = lambda kernel: running.get(kernel or "")
    origins.note("orders", Origin(kind="python", kernel="k1"))
    running["k1"] = "/work/Shop/report.ipynb"  # another document's code runs in the same session
    origins.note("late", Origin(kind="python", kernel="k1"))
    assert origins.document("orders") == "/work/Shop/load.py"
    assert origins.document("late") == "/work/Shop/report.ipynb"
    origins.rename("orders", "sales")
    assert origins.document("sales") == "/work/Shop/load.py" and origins.document("orders") is None
    origins.note("sales", Origin(kind="file", path="/work/Shop/sales.csv"))  # read again from a file
    assert origins.document("sales") is None
    origins.forget("late")
    assert origins.document("late") is None


def test_a_loose_file_keeps_a_session_of_its_own(client: TestClient, project: Path, tmp_path: Path) -> None:
    loose = tmp_path / "elsewhere" / "scratch.py"
    loose.parent.mkdir()
    loose.write_text("x = 1\n", encoding="utf-8")
    opened = ok(client.post("/workbench/open", json={"path": str(loose)}, headers=AUTH))
    assert opened["session"] is None
    shared = start(client, path=str(project / "load.py"))["kernel"]
    own = start(client, path=str(loose))
    other = start(client)  # no document, not said to be the project's (the Widgets window's)
    assert own["session"] is None and len({shared, own["kernel"], other["kernel"]}) == 3
    run(client, shared, "only_here = 1")
    assert "False" in text_of(run(client, own["kernel"], "print('only_here' in globals())"))
    # Its own kernel stops with its document, as before.
    assert ok(client.delete(f"/workbench/kernels/{own['kernel']}", headers=AUTH))["stopped"] is True
    # The project's session stops only when asked for by name.
    stopped = ok(client.delete(f"/workbench/kernels/{shared}?session=1", headers=AUTH))
    assert stopped == {"ok": True, "stopped": True, "session": True}
    fresh = start(client, path=str(project / "load.py"))["kernel"]
    assert fresh != shared


def test_with_no_project_open_every_document_has_its_own(client: TestClient, tmp_path: Path) -> None:
    one = start(client, path=str(tmp_path / "a.ipynb"))
    two = start(client, path=str(tmp_path / "b.py"), project=True)
    assert one["kernel"] != two["kernel"] and one["session"] is None and two["session"] is None
    assert ok(client.get("/environment/python", headers=AUTH))["status"] == "none"


# ===== the project's own .venv =====


@pytest.fixture
def making(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    monkeypatch.setenv(environments.STANDIN, str(Path(libraries_standin.__file__)))
    with make_client(tmp_path, project_venv=True) as test_client:
        yield test_client


def wait_for(client: TestClient, status: str) -> dict[str, Any]:
    for _ in range(200):
        state: dict[str, Any] = ok(client.get("/environment/python", headers=AUTH))
        if state["status"] == status:
            return state
        time.sleep(0.05)
    raise AssertionError(f"never {status}: {state}")


def test_a_new_project_gets_its_own_python_made_without_holding_the_page(
    making: TestClient, tmp_path: Path
) -> None:
    folder = tmp_path / "work" / "Shop"
    with making.websocket_connect("/ws?catalog=1", headers=AUTH | {"Host": f"127.0.0.1:{PORT}"}) as socket:
        ok(making.post("/project/new", json={"path": str(folder)}, headers=AUTH))
        heard = socket.receive_json()
        while heard.get("type") != "project_python":
            heard = socket.receive_json()
    assert heard["status"] == "making" and "app's own Python until it is ready" in heard["said"]
    ready = wait_for(making, "ready")
    assert ready["own"] is True and Path(ready["python"]).is_relative_to(folder / ".venv")
    assert "its own Python" in ready["words"] and "One Python session" in ready["session"]
    # Made with the kernel, the Excel readers and what requirements.txt names.
    site = libraries_standin.site_packages(folder)
    made = {p.name.split("-")[0] for p in site.glob("*.dist-info")}
    assert {"ipykernel", "openpyxl", "xlrd"} <= made
    # Git never takes it: the scaffold's .gitignore names it.
    assert ".venv/" in (folder / ".gitignore").read_text(encoding="utf-8")
    # A made-up .venv's Python does not run: the session starts in the app's own Python, and says so.
    started = start(making, path=str(folder / "data.ipynb"))
    assert started["session"]["shared"] and Path(started["python"]) == Path(sys.executable)
    assert any("does not run" in p for p in started["vaults"]["problems"])
    assert "2" in text_of(run(making, started["kernel"], "print(1 + 1)"))


def test_opening_a_project_without_one_makes_it_and_a_failure_is_said_with_try_again(
    making: TestClient, tmp_path: Path
) -> None:
    folder = tmp_path / "work" / "Ledger"
    folder.mkdir(parents=True)
    (folder / "venv-fails.txt").write_text("the stand-in fails while this is here", encoding="utf-8")
    (folder / "requirements.txt").write_text("polars==1.36.0\n", encoding="utf-8")
    ok(making.post("/project/open", json={"path": str(folder), "make": True}, headers=AUTH))
    failed = wait_for(making, "failed")
    assert failed["own"] is False and "No interpreter found" in failed["problem"]
    assert "could not be made" in failed["words"] and not (folder / ".venv").exists()
    # Try again (the user's click, the agent's environment(action="set_python")).
    (folder / "venv-fails.txt").unlink()
    assert {"python", "set_python"} <= set(commands._ENVIRONMENT)
    ok(making.post("/environment/python", json={"make": True}, headers=AGENT))
    ready = wait_for(making, "ready")
    assert ready["problem"] is None
    site = libraries_standin.site_packages(folder)
    assert (site / "polars-1.36.0.dist-info").is_dir()  # requirements.txt's own line
    # Made once: asking again is refused in one line.
    refused = making.post("/environment/python", json={"make": True}, headers=AUTH)
    assert refused.status_code == 409 and "already has its own Python" in refused.text


def test_a_project_that_has_one_is_left_alone(making: TestClient, tmp_path: Path) -> None:
    folder = tmp_path / "work" / "Shop"
    folder.mkdir(parents=True)
    libraries_standin.make_venv(folder, {"pandas": "2.3.3"})
    ok(making.post("/project/open", json={"path": str(folder), "make": True}, headers=AUTH))
    state = ok(making.get("/environment/python", headers=AUTH))
    assert state["status"] == "ready"
    assert not list(libraries_standin.site_packages(folder).glob("ipykernel-*"))  # nothing was made again


@pytest.mark.skipif(sys.platform == "win32", reason="a link to a program needs a right on Windows")
def test_a_venv_that_links_to_the_apps_python_is_still_its_own_environment(tmp_path: Path) -> None:
    """Found with a real `.venv` (uv links its Python to the one it was made from): the project's libraries
    were read as the app's own. A Python is the app's by its place, never by what its link points to."""
    python = libraries_standin.make_venv(tmp_path, {"tabulate": "0.10.0"})
    python.unlink()
    python.symlink_to(sys.executable)
    assert environment_files.installed(str(python)) == {"tabulate": "0.10.0"}
    assert environment_files.requires(str(python)) == {"tabulate": []}
    assert "pytest" in environment_files.installed(sys.executable)


# ===== a notebook that had its own environment =====


def test_a_notebooks_own_environment_is_read_once_and_offered(
    client: TestClient, project: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv(environments.STANDIN, str(Path(libraries_standin.__file__)))
    notebook = str(project / "report.ipynb")
    # Its older environment (made up): seaborn chosen, which brought matplotlib; duckdb the app has already.
    old = tmp_path / "old-environment"
    python = libraries_standin.make_venv(
        old, {"seaborn": "0.13.2", "matplotlib": "3.10.0", "made-up-lib": "1.0"}
    )
    site = libraries_standin.site_packages(old)
    with (site / "seaborn-0.13.2.dist-info" / "METADATA").open("a", encoding="utf-8") as file:
        file.write("Requires-Dist: matplotlib>=3.4\nRequires-Dist: statsmodels; extra == 'stats'\n")
    documents = client.app.state.ctx.workbench._documents  # type: ignore[attr-defined]
    documents.remember_environment(notebook, str(python))
    opened = ok(client.post("/workbench/open", json={"path": notebook}, headers=AUTH))
    moved = opened["moved_environment"]
    assert moved["libraries"] == ["made-up-lib", "seaborn"]
    assert moved["words"].startswith("report.ipynb had its own environment. It now runs in the project's")
    assert opened["python"] == sys.executable  # the project's Python (the app's own until its .venv is there)
    # Read once: the next open says nothing, and the offer waits on the Environment until answered.
    assert "moved_environment" not in ok(
        client.post("/workbench/open", json={"path": notebook}, headers=AUTH)
    )
    state = ok(client.get("/environment/python", headers=AUTH))
    assert [o["document"] for o in state["offers"]] == [notebook]
    # Add them: installed (stood in) into the project's Python and written to requirements.txt.
    libraries_standin.make_venv(project, {})
    ok(client.post("/environment/python", json={"offer": notebook, "add": True}, headers=AUTH))
    wanted = (project / "requirements.txt").read_text(encoding="utf-8")
    assert "seaborn" in wanted and "made-up-lib" in wanted
    assert ok(client.get("/environment/python", headers=AUTH))["offers"] == []
    gone = client.post("/environment/python", json={"offer": notebook, "add": False}, headers=AUTH)
    assert gone.status_code == 404


# ===== a table is shared at once =====


def test_every_table_in_the_environment_is_read_by_name_without_a_grid(client: TestClient) -> None:
    """A table whose last grid was closed is still in the Environment: it is read by name as it is (the
    adapter's door a session's `sab.table` and DuckDB SQL read through), never opened as a grid first; one a
    grid shows is read as that grid shows it, its steps applied."""
    orders = pa.table({"order_id": [1, 2, 3], "amount": [10.5, 7.0, 40.0]})
    grid = ok(push(client, "orders", orders))["grid"]
    steps = [{"kind": "filter", "params": {"column": "amount", "op": "gt", "value": 8}}]
    ok(client.post(f"/grids/{grid}/steps", json={"steps": steps}, headers=AUTH))
    shown = client.get("/workbench/tables/orders/arrow", headers=AUTH)
    assert ipc.open_stream(io.BytesIO(shown.content)).read_all().num_rows == 2
    # Its grid closed: the table stays in the Environment, with no grid.
    ok(client.delete(f"/grids/{grid}", headers=AUTH))
    row = next(i for i in ok(client.get("/environment", headers=AUTH))["items"] if i["id"] == "table:orders")
    assert row["grids"] == []
    listed = ok(client.post("/workbench/tables/adapter/tables", json={}, headers=AUTH))["tables"]
    assert [(t["name"], [c["name"] for c in t["columns"]]) for t in listed] == [
        ("orders", ["order_id", "amount"])
    ]
    whole = client.get("/workbench/tables/ORDERS/arrow", headers=AUTH)
    assert whole.status_code == 200 and ipc.open_stream(io.BytesIO(whole.content)).read_all().num_rows == 3
    plan = {"columns": ["amount"], "filters": [["amount", ">", 8]], "sort": [], "limit": None}
    read = client.post("/workbench/tables/adapter/read", json={"table": "orders", "plan": plan}, headers=AUTH)
    assert read.status_code == 200 and ipc.open_stream(io.BytesIO(read.content)).read_all().num_rows == 2
    again = next(
        i for i in ok(client.get("/environment", headers=AUTH))["items"] if i["id"] == "table:orders"
    )
    assert again["grids"] == []  # read by name: still no grid made for it
    missing = client.get("/workbench/tables/nothing_here/arrow", headers=AUTH)
    assert missing.status_code == 404 and "is in the Environment" in missing.text


def test_the_venv_carries_what_the_projects_type_needs() -> None:
    """Canvas previews, 2026-11-22: a Streamlit canvas's project whose requirements.txt leaves Streamlit out
    still gets it in its `.venv` (its contract's requirements); requirements.txt's own line wins."""
    assert rules.venv_packages("", ["streamlit>=1.43"]) == [
        "ipykernel",
        "openpyxl",
        "xlrd",
        "streamlit>=1.43",
    ]
    assert rules.venv_packages("streamlit==1.50.0\n", ["streamlit>=1.43"])[-1] == "streamlit==1.50.0"


def test_the_streamlit_canvas_asks_for_streamlit_in_every_project_that_offers_it() -> None:
    from swissarmybench import extensions

    assert "streamlit>=1.43" in extensions.requirements_of("streamlit")
    assert "streamlit>=1.43" in extensions.requirements_of("bi")  # its canvas is offered in a BI project
    assert extensions.requirements_of("no-such-type") == []
