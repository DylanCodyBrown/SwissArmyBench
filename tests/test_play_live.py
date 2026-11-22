"""Play follows live data (the owner, 2026-11-22: "yea live changes"; docs/ideas.md "Play follows live data,
2026-11-22"). A table a playing page reads (an open grid's table, a sandbox table, data.ipynb's data.py) is
written again into its run when it changes, only when its bytes changed, and the run's sab_live.py stamp
moves so Streamlit's own file watcher runs the open pages again; the runtime reads a table's Parquet again
only when its file changed. Here the Streamlit process is stood in for (FakeRunner: the files are real), and
the runtime's reader runs in this Python; tests/e2e/test_field_service_app.py sees a page follow in a
browser. Made-up data only."""

from __future__ import annotations

import ast
import io
import os
import time
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any

import pyarrow.parquet as pq
import pytest
from starlette.testclient import TestClient

from swissarmybench_streamlit.domain import canvas_build
from swissarmybench_streamlit.server.live_runs import LIVE_FILE, live_text
from swissarmybench_streamlit.services.live_tables import LiveTables
from tests.conftest import AUTH, make_client
from tests.streamlit_helpers import FakeRunner

SORTED = [{"kind": "sort", "params": {"keys": [["amount", "desc"]]}}]
ORDERS = "order_id,region,amount\n1,West,10.5\n2,East,7.25\n3,West,3.0\n4,North,12.0\n"


def ok(response: Any) -> Any:
    assert response.status_code == 200, response.text
    return response.json()


def until(check: Callable[[], Any], seconds: float = 10.0) -> Any:
    deadline = time.monotonic() + seconds
    while True:
        found = check()
        if found or time.monotonic() > deadline:
            return found
        time.sleep(0.05)


# ===== the rules =====


def test_a_notice_reads_again_only_what_it_names() -> None:
    live = LiveTables(None, None)  # type: ignore[arg-type]
    names = ["orders", "[Sandbox].orders", '[sandbox]."Stock"', "[Shop].segments"]
    assert [n for n in names if live.wanted(True, set())(n)] == ["orders"]
    assert [n for n in names if live.wanted(False, {"stock"})(n)] == ['[sandbox]."Stock"']
    assert [n for n in names if live.wanted(False, None)(n)] == ["[Sandbox].orders", '[sandbox]."Stock"']
    # Another connection's table is never read again by a notice: the session's read stands (its Refresh).
    assert not any(live.wanted(True, None)(n) for n in ["[Shop].segments"])


def test_the_runtime_reads_a_tables_parquet_again_only_when_its_file_changed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import pandas as pd

    tree = ast.parse(canvas_build.RUNTIME)
    source = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "_parquet")
    namespace: dict[str, Any] = {"_READ": {}}
    exec(  # noqa: S102 (our own runtime's one function)
        "from pathlib import Path\nfrom typing import Any\n" + ast.unparse(source), namespace
    )
    path = tmp_path / "orders.parquet"
    pd.DataFrame({"a": [1, 2]}).to_parquet(path)
    first = namespace["_parquet"](path)
    first["a"] = 0  # a widget changing its frame changes only its own copy
    assert namespace["_parquet"](path)["a"].tolist() == [1, 2]
    reads: list[Any] = []
    real = pd.read_parquet

    def counted(given: Any) -> Any:
        reads.append(given)
        return real(given)

    monkeypatch.setattr(pd, "read_parquet", counted)
    assert namespace["_parquet"](path)["a"].tolist() == [1, 2] and reads == []  # unchanged: not read
    pd.DataFrame({"a": [3]}).to_parquet(path)
    os.utime(path, ns=(time.time_ns(), time.time_ns() + 1_000_000))
    assert namespace["_parquet"](path)["a"].tolist() == [3] and len(reads) == 1
    assert namespace["_parquet"](tmp_path / "gone.parquet") is None


def test_the_stamp_holds_no_name_or_value() -> None:
    assert live_text(3) == (
        '"""Swiss Army Bench rewrites this stamp when a table this app reads changes: '
        'its pages run again."""\n'
        "VERSION = 3\n"
    )
    assert "import sab_live" in canvas_build.RUNTIME


# ===== a playing page =====


@pytest.fixture
def played(tmp_path: Path) -> Iterator[tuple[TestClient, Path, str, str]]:
    with make_client(tmp_path) as client:
        runner = FakeRunner()
        client.app.state.ctx.extension["streamlit"].live_runs._runner = runner  # type: ignore[attr-defined]
        project = tmp_path / "shop"
        ok(client.post("/project/new", json={"path": str(project)}, headers=AUTH))
        csv = tmp_path / "orders.csv"
        csv.write_text(ORDERS, encoding="utf-8")
        grid = str(ok(client.post("/datasets/orders/load", json={"path": str(csv)}, headers=AUTH))["grid"])
        ok(client.post("/sandbox/tables/variant", json={"table": "orders"}, headers=AUTH))
        made = ok(
            client.post("/streamlit/canvases", headers=AUTH, json={"name": "Live", "folder": str(project)})
        )
        canvas = made["canvas"]
        for table in ("orders", "[Sandbox].orders_sandbox"):
            body = {"kind": "insert_widget", "widget": "data_table", "values": {"table_name": table}}
            ok(client.post(f"/streamlit/canvases/{canvas}/command", headers=AUTH, json=body))
        ok(client.post(f"/streamlit/canvases/{canvas}/play", headers=AUTH, json={"python": "/p"}))
        folder = Path(runner.started[-1][1])
        yield client, folder, grid, canvas


def _amounts(folder: Path, name: str) -> list[Any]:
    path = folder / "data" / f"{canvas_build.table_stem(name)}.parquet"
    try:
        return list(pq.read_table(io.BytesIO(path.read_bytes())).column("amount").to_pylist())
    except OSError:
        return []


def _version(folder: Path) -> int:
    text = (folder / LIVE_FILE).read_text(encoding="utf-8")
    return int(text.rsplit("VERSION = ", 1)[1])


def test_a_sandbox_write_shows_in_the_playing_page_without_playing_again(
    played: tuple[TestClient, Path, str, str],
) -> None:
    client, folder, _grid, _canvas = played
    sandbox = "[Sandbox].orders_sandbox"
    assert _amounts(folder, sandbox) == [10.5, 7.25, 3.0, 12.0] and _version(folder) == 0
    stamp = (folder / "data" / f"{canvas_build.table_stem('orders')}.parquet").stat().st_mtime_ns
    ok(client.post("/sandbox/tables/open", json={"table": "orders_sandbox"}, headers=AUTH))
    edit = {"table": "orders_sandbox", "op": "update", "row": 0, "column": "amount", "value": "99.5"}
    ok(client.post("/sandbox/edit", json=edit, headers=AUTH))  # a sandbox grid's edit, as an API's write
    assert until(lambda: _amounts(folder, sandbox) == [99.5, 7.25, 3.0, 12.0]), _amounts(folder, sandbox)
    assert until(lambda: _version(folder) == 1)  # the stamp moved: Streamlit runs the open pages again
    ok(client.post("/sandbox/edit", json=edit | {"row": 1, "value": "50"}, headers=AUTH))  # and again
    assert until(lambda: _amounts(folder, sandbox) == [99.5, 50.0, 3.0, 12.0]), _amounts(folder, sandbox)
    assert until(lambda: _version(folder) == 2)
    # The open table the write did not touch was not written again.
    assert (folder / "data" / f"{canvas_build.table_stem('orders')}.parquet").stat().st_mtime_ns == stamp


def test_an_open_tables_steps_and_close_show_in_the_playing_page(
    played: tuple[TestClient, Path, str, str],
) -> None:
    client, folder, grid, _canvas = played
    assert _amounts(folder, "orders") == [10.5, 7.25, 3.0, 12.0]
    ok(client.post(f"/grids/{grid}/steps", json={"steps": SORTED}, headers=AUTH))
    assert until(lambda: _amounts(folder, "orders") == [12.0, 10.5, 7.25, 3.0]), _amounts(folder, "orders")
    assert until(lambda: _version(folder) == 1)
    # The same steps again write nothing: the page keeps what it read, the stamp stays.
    ok(client.post(f"/grids/{grid}/steps", json={"steps": SORTED}, headers=AUTH))
    time.sleep(0.6)
    assert _version(folder) == 1
    # Closed: no copy of it stays (the page says the table is not here).
    ok(client.delete("/datasets/orders", headers=AUTH))
    assert until(lambda: not (folder / "data" / "orders.parquet").is_file())
    assert until(lambda: _version(folder) == 2)


def test_a_stopped_run_follows_nothing(played: tuple[TestClient, Path, str, str]) -> None:
    client, folder, grid, canvas = played
    ok(client.post(f"/streamlit/canvases/{canvas}/stop", headers=AUTH, json={}))
    assert not folder.exists()  # its folder went with it
    ok(client.post(f"/grids/{grid}/steps", json={"steps": SORTED}, headers=AUTH))
    time.sleep(0.5)
    assert not folder.exists()


def test_data_pys_tables_follow_its_export(played: tuple[TestClient, Path, str, str]) -> None:
    """data.ipynb's tables are data.py's, beside the app: data.py written again (its export) is copied into
    the run, a module its pages import, so Streamlit runs them again by itself."""
    client, folder, _grid, _canvas = played
    ctx = client.app.state.ctx  # type: ignore[attr-defined]
    project = Path(ctx.sab_projects.state()["project"]["folder"])
    assert (folder / "data.py").read_bytes() == (project / "data.py").read_bytes()
    made = "import pandas as pd\n\nregions = pd.DataFrame({'r': ['West']})\n"
    (project / "data.py").write_text(made, encoding="utf-8")
    live = ctx.extension["streamlit"].live_tables
    live.heard({"type": "file_changed", "path": str(project / "data.py"), "by": "app"})
    assert len(client.portal.call(live.refresh)) == 1  # type: ignore[union-attr]
    assert (folder / "data.py").read_text(encoding="utf-8") == made and _version(folder) == 1
    live.heard({"type": "file_changed", "path": str(project / "other.py"), "by": "app"})
    assert client.portal.call(live.refresh) == []  # type: ignore[union-attr]
