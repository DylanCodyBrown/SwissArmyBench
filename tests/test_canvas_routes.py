"""The Canvas over HTTP (services/canvas.py): a canvas file opened and changed by rule-checked commands, every
change saved at once (atomically, only when its bytes change) and undoable; a command sent for an older
version refused with the canvas as it is now; a file changed on disk read again first; a broken file reported
with its line and a copy kept, never written over; a newer one read-only; an instance of a deleted widget kept
as a placeholder (Replace, Remove); a widget's rename followed by its instances; Play, Launch and Export from
the one builder; the agent's export on the user's Allow. Made-up data only."""

from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pyarrow as pa
import pytest
from starlette.testclient import TestClient

from swissarmybench_streamlit.domain import canvas_model as model
from tests.conftest import AGENT, AUTH, make_client, push
from tests.streamlit_helpers import FakeRunner, answering

ORDERS = pa.table({"month": ["2026-01", "2026-02"], "region": ["North", "South"], "revenue": [120.5, 98.0]})


@pytest.fixture
def served(tmp_path: Path) -> Iterator[tuple[TestClient, FakeRunner, Path]]:
    with make_client(tmp_path) as client:
        runner = FakeRunner()
        client.app.state.ctx.live_runs._runner = runner  # type: ignore[attr-defined]
        assert push(client, "orders", ORDERS).status_code == 200
        project = tmp_path / "shop"
        project.mkdir()
        yield client, runner, project


def ok(response: Any) -> dict[str, Any]:
    assert response.status_code == 200, response.text
    return dict(response.json())


def opened(client: TestClient, project: Path, name: str = "Sales") -> dict[str, Any]:
    return ok(client.post("/streamlit/canvases", headers=AUTH, json={"name": name, "folder": str(project)}))


def command(client: TestClient, canvas: str, kind: str, headers: dict[str, str] = AUTH, **body: Any) -> Any:
    return client.post(f"/streamlit/canvases/{canvas}/command", headers=headers, json={"kind": kind, **body})


def test_every_change_is_saved_at_once_and_undoable(served: tuple[TestClient, FakeRunner, Path]) -> None:
    client, _, project = served
    state = opened(client, project)
    path = project / "sales.canvas.json"
    assert path.is_file() and state["version"] == 1 and state["path"] == str(path)
    canvas = state["canvas"]
    made = ok(command(client, canvas, "add_container", x=10, y=20, w=400, h=200, version=1))
    assert made["made"] == "c1" and made["version"] == 2
    on_disk = json.loads(path.read_text())
    assert on_disk["pages"][0]["children"][0]["x"] == 10
    ok(command(client, canvas, "insert_widget", parent="c1", widget="metric", values={"label": "Orders"}))
    ok(command(client, canvas, "set_container", id="c1", props={"scrollable": True, "title": "KPIs"}))
    after = ok(client.post(f"/streamlit/canvases/{canvas}/undo", headers=AUTH))
    assert model.find(after["model"], "c1")[2]["props"]["scrollable"] is False
    assert json.loads(path.read_text())["pages"][0]["children"][0]["props"]["scrollable"] is False
    again = ok(client.post(f"/streamlit/canvases/{canvas}/redo", headers=AUTH))
    assert model.find(again["model"], "c1")[2]["props"]["title"] == "KPIs" and again["undo"] == 3
    stamp = path.stat().st_mtime_ns
    ok(command(client, canvas, "set_container", id="c1", props={"title": "KPIs"}))  # nothing changes
    assert path.stat().st_mtime_ns == stamp
    refused = command(client, canvas, "move", id="c1", x=5000)
    assert refused.status_code == 400 and "past the right of the page" in refused.text


def test_two_windows_never_write_over_each_other(served: tuple[TestClient, FakeRunner, Path]) -> None:
    client, _, project = served
    canvas = opened(client, project)["canvas"]
    ok(command(client, canvas, "add_container", version=1, window="a"))
    stale = command(client, canvas, "add_container", version=1, window="b")
    assert stale.status_code == 409 and "changed in another window" in stale.text
    # The file changed on disk (a pull): read again, the change refused, nothing written over it.
    path = project / "sales.canvas.json"
    edited = json.loads(path.read_text())
    edited["pages"][0]["name"] = "Changed elsewhere"
    path.write_text(json.dumps(edited))
    moved = command(client, canvas, "add_container")
    assert moved.status_code == 409 and "changed on disk" in moved.text
    state = ok(client.get(f"/streamlit/canvases/{canvas}", headers=AUTH))
    assert state["model"]["pages"][0]["name"] == "Changed elsewhere"
    ok(command(client, canvas, "add_container", version=state["version"]))


def test_a_broken_file_is_reported_with_its_line_and_never_written_over(
    served: tuple[TestClient, FakeRunner, Path],
) -> None:
    client, _, project = served
    path = project / "broken.canvas.json"
    text = '{\n  "format": 1,\n  "pages": [\n'
    path.write_text(text)
    state = ok(client.post("/streamlit/canvases", headers=AUTH, json={"path": str(path)}))
    assert state["broken"]["line"] == 4 and "does not read" in state["broken"]["error"]
    assert Path(state["broken"]["copy"]).read_text() == text
    refused = command(client, state["canvas"], "add_container")
    assert refused.status_code == 403 and path.read_text() == text
    newer = project / "newer.canvas.json"
    newer.write_text(json.dumps({"format": 7, "pages": []}))
    read_only = ok(client.post("/streamlit/canvases", headers=AUTH, json={"path": str(newer)}))
    assert "newer version" in read_only["read_only"]
    assert command(client, read_only["canvas"], "add_container").status_code == 403
    old = project / "sales.stapp.json"
    old.write_text("{}")
    gone = client.post("/streamlit/canvases", headers=AUTH, json={"path": str(old)})
    assert gone.status_code == 400 and "replaced by widgets" in gone.text
    assert (
        ok(client.get(f"/streamlit/canvases?folder={project}", headers=AUTH))["old"][0]["name"]
        == "sales.stapp.json"
    )


def test_a_deleted_widget_stays_as_a_placeholder_and_a_rename_follows_its_instances(
    served: tuple[TestClient, FakeRunner, Path],
) -> None:
    client, runner, project = served
    ok(
        client.post(
            "/streamlit/widgets",
            headers=AUTH,
            json={
                "name": "sales_kpi",
                "code": 'import streamlit as st\n\nlabel = "Sales"\ncolour = "#1f77b4"\n\n'
                "st.metric(label, 1)\n",
            },
        )
    )
    canvas = opened(client, project)["canvas"]
    ok(
        command(
            client,
            canvas,
            "insert_widget",
            widget="sales_kpi",
            values={"label": "Orders", "colour": "#000000"},
        )
    )
    renamed = ok(client.patch("/streamlit/widgets/sales_kpi", headers=AUTH, json={"name": "orders_kpi"}))
    assert renamed["instances_renamed"] == 1
    state = ok(client.get(f"/streamlit/canvases/{canvas}", headers=AUTH))
    assert model.find(state["model"], "w1")[2]["widget"] == "orders_kpi"
    # A bad value is marked with the fix; the widget's code that lost a property drops its override, once.
    ok(command(client, canvas, "set_values", id="w1", values={"colour": "red"}))
    state = ok(client.get(f"/streamlit/canvases/{canvas}", headers=AUTH))
    assert "not a colour" in state["marks"]["w1"]["colour"]
    ok(
        client.put(
            "/streamlit/widgets/orders_kpi",
            headers=AUTH,
            json={"code": 'import streamlit as st\n\nlabel = "Sales"\n\nst.metric(label, 1)\n'},
        )
    )
    again = ok(
        client.post("/streamlit/canvases", headers=AUTH, json={"path": str(project / "sales.canvas.json")})
    )
    assert again["notes"] == ["w1 (orders_kpi): colour went with the widget's code."]
    assert ok(client.get(f"/streamlit/canvases/{canvas}", headers=AUTH))["notes"] == []  # said once
    ok(client.delete("/streamlit/widgets/orders_kpi", headers=AUTH))
    state = ok(client.get(f"/streamlit/canvases/{canvas}", headers=AUTH))
    assert state["missing"] == ["w1"]
    played = ok(client.post(f"/streamlit/canvases/{canvas}/play", headers=AUTH, json={"python": "/p"}))
    page = (Path(runner.started[-1][1]) / "app_pages" / "page_1.py").read_text()
    assert played["ok"] and "sab.missing('orders_kpi', 'w1')" in page
    replaced = ok(command(client, canvas, "replace_widget", id="w1", widget="metric"))
    assert replaced["missing"] == [] and model.find(replaced["model"], "w1")[2]["widget"] == "metric"


def test_play_launch_and_export_are_one_builder(
    served: tuple[TestClient, FakeRunner, Path], tmp_path: Path
) -> None:
    client, runner, project = served
    canvas = opened(client, project)["canvas"]
    ok(command(client, canvas, "add_container", x=0, y=0, w=600, h=300))
    ok(
        command(
            client, canvas, "insert_widget", parent="c1", widget="data_table", values={"table_name": "orders"}
        )
    )
    played = ok(client.post(f"/streamlit/canvases/{canvas}/play", headers=AUTH, json={"python": "/p"}))
    folder = Path(runner.started[-1][1])
    assert played["url"].endswith("/page_1") and (folder / "data" / "orders.parquet").is_file()
    page = (folder / "app_pages" / "page_1.py").read_text()
    launched = ok(client.post(f"/streamlit/canvases/{canvas}/launch", headers=AUTH, json={"python": "/p"}))
    build = project / "builds" / "sales" / "1"
    assert launched["build"] == 1 and (build / "app_pages" / "page_1.py").read_text() == page
    assert json.loads((build / "build.json").read_text())["changed"] == ["The first build."]
    assert not (build / "data").exists()  # never rows in a build
    out = tmp_path / "out"
    exported = ok(
        client.post(f"/streamlit/canvases/{canvas}/export", headers=AUTH, json={"folder": str(out)})
    )
    assert (out / "app_pages" / "page_1.py").read_text() == page
    assert {"app.py", "sab_canvas.py", "sab_widgets.py", "requirements.txt", "data/orders.parquet"} <= set(
        exported["files"]
    )


def test_the_agents_export_waits_for_the_users_allow(
    served: tuple[TestClient, FakeRunner, Path], tmp_path: Path
) -> None:
    client, _, project = served
    canvas = opened(client, project)["canvas"]
    ok(command(client, canvas, "insert_widget", widget="data_table", values={"table_name": "orders"}))
    pending = lambda: client.get("/agent/approvals", headers=AUTH).json()["pending"]  # noqa: E731

    def answer(request: str, yes: bool) -> Any:
        return client.post(f"/agent/approvals/{request}", headers=AUTH, json={"approve": yes})

    out = tmp_path / "out"
    with answering(pending, answer, approve=False) as asked:
        declined = client.post(
            f"/streamlit/canvases/{canvas}/export", headers=AGENT, json={"folder": str(out)}
        )
    assert declined.status_code == 403 and not out.exists()
    assert "with the rows of orders" in asked[0]["detail"]
    with answering(pending, answer, approve=True):
        ok(client.post(f"/streamlit/canvases/{canvas}/export", headers=AGENT, json={"folder": str(out)}))
    assert (out / "app.py").is_file()
