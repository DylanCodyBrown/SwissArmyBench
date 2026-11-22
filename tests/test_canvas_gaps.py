"""The canvas's gaps the owner approved (2026-11-21): a widget Hidden in the app, who is viewing (app.viewer),
the project's sandbox tables as a source, wires across pages, a wired table's columns, typed event payloads,
File Outs (input_file, input_camera, input_audio into excel_upload), the project's own widgets/ folder; and
three fixes: excel_map_columns guessing again for a real upload, a container's long title never over its
first widget, the api_* widgets on the runtime's one api_call. Rules, the HTTP door and the agent's commands.
Made-up data only."""

from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pyarrow as pa
import pyarrow.parquet as pq
import pytest
from starlette.testclient import TestClient

from swissarmybench.cli import commands as _registry  # noqa: F401 (the base's registry first)
from swissarmybench_streamlit import commands
from swissarmybench_streamlit.domain import canvas_build as build
from swissarmybench_streamlit.domain import canvas_layouts as model
from swissarmybench_streamlit.domain import canvas_wiring as wiring
from swissarmybench_streamlit.domain import widget_contract as contract
from swissarmybench_streamlit.domain import widget_properties as props
from swissarmybench_streamlit.domain.canvas_model import WidgetFacts
from tests.conftest import AUTH, make_client, push
from tests.streamlit_helpers import FakeRunner

PREBUILT = Path(__file__).resolve().parents[1] / "extensions/streamlit/src/swissarmybench_streamlit/widgets"
ORDERS = pa.table({"order_id": [1, 2, 3], "region": ["North", "South", "West"], "amount": [12.5, 8.0, 4.25]})

PRODUCER = """from typing import TypedDict

from sab_canvas import Event, Out, Table


class Row(TypedDict):
    order_id: int
    region: str


class Order(TypedDict):
    order_id: int
    amount: float


# The rows picked
picked: Out[Table[Row]] = None
# The region picked
region: Out[str] = None
saved: Event[Order] = None
"""

READER = """import streamlit as st
from sab_canvas import In, Table

region: In[str] = "All"
rows: In[Table] = None
viewer: In[str] = "nobody"
# The column to show
column = "region"  # column of rows
st.markdown(f"region={region} viewer={viewer}")
"""


def _facts(*names: str) -> dict[str, WidgetFacts]:
    return {n: WidgetFacts((4, 2), (1, 1)) for n in names}


def _canvas_two_pages() -> dict[str, Any]:
    canvas = model.new_canvas("Shop")
    canvas["pages"].append({"id": "p2", "name": "Reports", "children": []})
    facts = _facts("producer", "reader")
    canvas, _ = model.apply(
        canvas, "add_container", {"page": "p1", "x": 0, "y": 0, "w": 600, "h": 300}, facts
    )
    canvas, _ = model.apply(canvas, "insert_widget", {"parent": "c1", "widget": "producer"}, facts)
    canvas, _ = model.apply(
        canvas, "add_container", {"page": "p2", "x": 0, "y": 0, "w": 600, "h": 300}, facts
    )
    canvas, _ = model.apply(
        canvas, "insert_widget", {"page": "p2", "parent": "c2", "widget": "reader"}, facts
    )
    return canvas


def _built() -> dict[str, build.Built]:
    return {"producer": build.made(PRODUCER), "reader": build.made(READER)}


# ===== the contract: typed payloads, Table[Row], File =====


def test_a_typed_payload_and_a_table_of_rows_name_their_fields() -> None:
    ports = {p.name: p for p in contract.detect(PRODUCER)}
    assert (
        ports["saved"].type == "dict" and ports["saved"].schema == "Order" and ports["saved"].problem is None
    )
    assert ports["saved"].fields == (("order_id", "int"), ("amount", "float"))
    assert ports["picked"].type == "Table" and ports["picked"].fields == (
        ("order_id", "int"),
        ("region", "str"),
    )
    assert ports["saved"].to_json()["fields"] == [
        {"name": "order_id", "type": "int"},
        {"name": "amount", "type": "float"},
    ]
    dataclassed = (
        "from dataclasses import dataclass\nfrom sab_canvas import Event\n\n\n@dataclass\nclass Visit:\n"
        "    store: str\n    when: str\n\n\nvisited: Event[Visit] = None\n"
    )
    visited = contract.detect(dataclassed)[0]
    assert visited.schema == "Visit" and [n for n, _ in visited.fields] == ["store", "when"]
    # Event[dict] still works; a name that is no record of the widget's is said
    assert contract.detect("from sab_canvas import Event\nsaved: Event[dict] = None\n")[0].problem is None
    unknown = contract.detect("from sab_canvas import Event\nsaved: Event[Nope] = None\n")[0]
    assert unknown.problem and "Nope is not a type here" in unknown.problem


def test_a_file_is_a_contract_type() -> None:
    found = contract.detect("from sab_canvas import File, In, Out\nf: Out[File] = None\ng: In[File] = None\n")
    assert (found[0].type, found[0].problem) == ("File", None)
    assert contract.words("File") == "a file" and contract.words("list[File]") == "a list of files"
    assert contract.fits("File", "File") and not contract.fits("File", "str")
    assert contract.fits_value("File", None) and not contract.fits_value("File", "report.csv")
    for name in ("input_file", "input_camera", "input_audio"):
        code = (PREBUILT / f"{name}.widget.py").read_text(encoding="utf-8")
        outs = {p.name: p.type for p in contract.detect(code) if p.direction == "out"}
        assert outs.get("file") == "File", name
    upload = (PREBUILT / "excel_upload.widget.py").read_text(encoding="utf-8")
    assert {p.name: p.type for p in contract.detect(upload) if p.direction == "in"}["file"] == "File"


def test_an_input_files_file_wires_itself_into_excel_upload() -> None:
    def code(name: str) -> str:
        text = (PREBUILT / f"{name}.widget.py").read_text(encoding="utf-8")
        return text.split("\n# ///\n", 1)[1]

    built = {"input_file": build.made(code("input_file")), "excel_upload": build.made(code("excel_upload"))}
    facts = _facts(*built)
    canvas = model.new_canvas("Load")
    canvas, _ = model.apply(canvas, "add_container", {"x": 0, "y": 0, "w": 1200, "h": 600}, facts)
    canvas, _ = model.apply(canvas, "insert_widget", {"parent": "c1", "widget": "input_file"}, facts)
    canvas, _ = model.apply(canvas, "insert_widget", {"parent": "c1", "widget": "excel_upload"}, facts)
    found = wiring.analyse(canvas, build.contracts(built))
    assert found["sources"]["w2"]["file"] == {"out": "w1.file"}
    assert {"from": "w1.file", "to": "w2.file", "auto": True} in found["wires"]


def test_a_column_property_of_a_table_in_takes_its_row_type_too() -> None:
    code = "from sab_canvas import In, Table\nrows: In[Table[Row]] = None\nx = 'a'  # column\n"
    prop = next(p for p in props.detect(code) if p.name == "x")
    assert prop.type == "column" and prop.of == "rows"


# ===== wires across pages, the viewer, a wired table's columns =====


def test_an_in_reads_another_pages_out_and_a_broken_one_is_marked() -> None:
    canvas = _canvas_two_pages()
    built = _built()
    canvas = wiring.set_wire(canvas, {"id": "w2", "port": "region", "wire": {"out": "w1.region"}})
    found = wiring.analyse(canvas, build.contracts(built))
    assert found["sources"]["w2"]["region"] == {"out": "w1.region"} and not found["broken"]
    line = next(w for w in found["wires"] if w["to"] == "w2.region")
    assert line == {"from": "w1.region", "to": "w2.region", "auto": False, "cross": True, "page": "p1"}
    assert found["readers"]["w1.region"] == ["w2.region"]
    # never automatic across pages: a same-named Out on another page is not taken by itself
    assert "rows" not in found["sources"]["w2"]
    # the producer deleted: the wire is broken, said like any other
    gone, _ = model.apply(canvas, "delete", {"id": "w1"}, _facts("producer", "reader"))
    broken = wiring.analyse(gone, build.contracts(built))["broken"]
    assert broken == [
        {
            "instance": "w2",
            "port": "region",
            "reason": "The widget w1 it read from was deleted.",
            "source": "w1.region",
        }
    ]


def test_who_is_viewing_is_the_apps_own_out() -> None:
    canvas = _canvas_two_pages()
    found = wiring.analyse(canvas, build.contracts(_built()))
    assert found["sources"]["w2"]["viewer"] == {"out": wiring.VIEWER}  # an In[str] called viewer: by itself
    assert found["outs"][wiring.VIEWER]["type"] == "str"
    port = contract.Port("count", "in", "int")
    with pytest.raises(contract.ContractError, match="takes a whole number"):
        wiring.check_in(port, {"out": wiring.VIEWER}, wiring.Context({wiring.VIEWER: "str"}))
    wiring.check_in(
        contract.Port("who", "in", "str"), {"out": wiring.VIEWER}, wiring.Context({wiring.VIEWER: "str"})
    )


def test_a_wired_tables_columns_come_from_its_out() -> None:
    canvas = _canvas_two_pages()
    canvas = wiring.set_wire(canvas, {"id": "w2", "port": "rows", "wire": {"out": "w1.picked"}})
    found = wiring.analyse(canvas, build.contracts(_built()))
    assert found["columns"]["w1.picked"] == ["order_id", "region"]  # declared: Table[Row]
    plain = {
        "producer": build.made(PRODUCER.replace("Out[Table[Row]]", "Out[Table]")),
        "reader": _built()["reader"],
    }
    assert "w1.picked" not in wiring.analyse(canvas, build.contracts(plain))["columns"]  # not known yet
    seen = wiring.analyse(canvas, build.contracts(plain), seen={"w1.picked": ["sku", "qty"]})
    assert seen["columns"]["w1.picked"] == ["sku", "qty"]  # as Play last ran it


def test_the_built_page_reads_another_pages_out_from_the_apps_session() -> None:
    canvas = wiring.set_wire(
        _canvas_two_pages(), {"id": "w2", "port": "region", "wire": {"out": "w1.region"}}
    )
    files = build.build(canvas, _built())
    assert not build.compiles(files)
    reports = files["app_pages/reports.py"]
    assert '"region": {"out": "w1.region"}' in reports and '"viewer": {"out": "app.viewer"}' in reports


# ===== hidden in the app =====


def test_a_hidden_widget_runs_and_takes_no_space() -> None:
    facts = _facts("producer", "reader")
    canvas = _canvas_two_pages()
    canvas, _ = model.apply(
        canvas, "insert_widget", {"page": "p1", "widget": "producer", "x": 0, "y": 400}, facts
    )
    hidden, _ = model.apply(canvas, "hide", {"id": "w3", "hidden": True}, facts)
    assert model.find(hidden, "w3")[2]["hidden"] is True
    # A container, titled too (the owner approved, 2026-11-21): hidden as a whole; its widgets still run.
    boxed, _ = model.apply(hidden, "set_container", {"id": "c1", "props": {"title": "Loaders"}}, facts)
    boxed, _ = model.apply(boxed, "hide", {"id": "c1", "hidden": True}, facts)
    assert model.find(boxed, "c1")[2]["hidden"] is True
    assert model.read(model.write(boxed)).canvas == boxed
    boxed_page = build.page_code(boxed, "p1", _built())
    boxed_css = json.loads(boxed_page.split("sab.style(", 1)[1].split(")\n", 1)[0])
    assert "display: none" in boxed_css.split(".st-key-sab-c1 {", 1)[1].split("}", 1)[0]
    assert "sab.render('producer', {}, 'w1')" in boxed_page  # its widget runs, its Outs flow
    with pytest.raises(model.CanvasError, match="true or false"):
        model.apply(hidden, "hide", {"id": "w3", "hidden": "yes"}, facts)
    shown, _ = model.apply(hidden, "hide", {"id": "w3", "hidden": False}, facts)
    assert "hidden" not in model.find(shown, "w3")[2]
    # read back the same; a hidden that is not true is refused on read
    assert model.read(model.write(hidden)).canvas == hidden
    bad = json.loads(model.write(hidden))
    bad["pages"][0]["children"][0]["hidden"] = False
    with pytest.raises(model.CanvasError, match="hidden is true, or left out"):
        model.read(json.dumps(bad))
    page = build.page_code(hidden, "p1", _built())
    css = json.loads(page.split("sab.style(", 1)[1].split(")\n", 1)[0])
    assert (
        ".st-key-sab-w3 {" in css and "display: none" in css.split(".st-key-sab-w3 {", 1)[1].split("}", 1)[0]
    )
    # its container holds nothing else and has no title: it takes no space either
    assert "display: none" in css.split(".st-key-sab-c3 {", 1)[1].split("}", 1)[0]
    assert "display: none" not in css.split(".st-key-sab-c1 {", 1)[1].split("}", 1)[0]
    assert "sab.render('producer', {}, 'w3')" in page  # it still runs
    # the page's height ends at its last shown item, not at the hidden one
    assert ".st-key-sab-page { position: relative; width: 100%; height: 300px;" in css
    shown_page = json.loads(
        build.page_code(shown, "p1", _built()).split("sab.style(", 1)[1].split(")\n", 1)[0]
    )
    assert ".st-key-sab-page { position: relative; width: 100%; height: 544px;" in shown_page


# ===== a container's title =====


def test_a_containers_title_is_reserved_above_its_widgets() -> None:
    facts = _facts("reader")
    canvas = model.new_canvas("Titles")
    canvas, _ = model.apply(canvas, "add_container", {"x": 0, "y": 0, "w": 600, "h": 300}, facts)
    canvas, _ = model.apply(
        canvas, "insert_widget", {"parent": "c1", "widget": "reader", "x": 8, "y": 36}, facts
    )
    plain = build.page_code(canvas, "p1", {"reader": build.made(READER)})
    titled_canvas, _ = model.apply(
        canvas,
        "set_container",
        {"id": "c1", "props": {"title": "Reconciliation results for every month"}},
        facts,
    )
    titled = build.page_code(titled_canvas, "p1", {"reader": build.made(READER)})
    assert "sab-c1-body" not in plain
    assert "with st.container(key='sab-c1-body'):" in titled
    css = json.loads(titled.split("sab.style(", 1)[1].split(")\n", 1)[0])
    pad = model.find(titled_canvas, "c1")[2]["props"]["padding"]
    # the widget's top inside the body is its canvas top less the border, padding and the title's one line
    assert f"top: {max(0, 36 - build.BORDER - pad - build.TITLE_PX)}px" in css.split(".st-key-sab-w1 {", 1)[1]
    # one drawn in the title's line sits under it, never over it
    lower, _ = model.apply(titled_canvas, "move", {"id": "w1", "y": 80}, facts)
    lower_css = json.loads(
        build.page_code(lower, "p1", {"reader": build.made(READER)})
        .split("sab.style(", 1)[1]
        .split(")\n", 1)[0]
    )
    assert f"top: {80 - build.BORDER - pad - build.TITLE_PX}px" in lower_css.split(".st-key-sab-w1 {", 1)[1]
    assert (
        "top: 35px"
        in json.loads(plain.split("sab.style(", 1)[1].split(")\n", 1)[0]).split(".st-key-sab-w1 {")[1]
    )
    assert not build.compiles(build.build(titled_canvas, {"reader": build.made(READER)}))


# ===== the three fixes =====


def test_map_columns_keys_its_pickers_by_the_columns_it_maps() -> None:
    code = (PREBUILT / "excel_map_columns.widget.py").read_text(encoding="utf-8")
    assert 'key=key(f"f_{field}_{_of}")' in code and "hashlib.sha256" in code


def test_the_api_widgets_call_through_the_runtimes_one_action() -> None:
    """Every API widget's call is the runtime's action(): api_adapter's run, its one envelope. No widget has a
    request of its own, and the older api_call is the same call (kept for the widgets written on it)."""
    for name in ("api_table", "api_form", "api_button", "api_metric"):
        code = (PREBUILT / f"{name}.widget.py").read_text(encoding="utf-8")
        assert "def _call(" not in code and "urllib" not in code and "api_call(" not in code, name
        assert " action(endpoint" in code and "said(answer)" in code, name
        assert "action" in code.split("from sab_canvas import", 1)[1].split("\n", 1)[0], name
    assert "def action(" in build.RUNTIME and "import api_adapter as aa" in build.RUNTIME
    older = build.RUNTIME.split("def api_call(", 1)[1].split("\n\n\n", 1)[0]
    assert "action(" in older and "urllib" not in older


# ===== the HTTP door and the agent =====


@pytest.fixture
def served(tmp_path: Path) -> Iterator[tuple[TestClient, FakeRunner, Path]]:
    with make_client(tmp_path) as client:
        runner = FakeRunner()
        client.app.state.ctx.live_runs.use_runner(runner)  # type: ignore[attr-defined]
        assert push(client, "orders", ORDERS).status_code == 200
        project = tmp_path / "work" / "shop"
        ok(client.post("/project/new", json={"path": str(project)}, headers=AUTH))
        yield client, runner, project


def ok(response: Any) -> dict[str, Any]:
    assert response.status_code == 200, response.text
    return dict(response.json())


def as_agent(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    """The agent's commands sent through this client (the agent's own door)."""

    def call(method: str, path: str, body: Any = None) -> Any:
        answer = client.request(method, path, headers=AUTH, json=body)
        assert answer.status_code == 200, answer.text
        return answer.json()

    monkeypatch.setattr(commands.api, "call", call)  # type: ignore[attr-defined]


WIDGET = """# /// swissarmybench-widget
# format = 1
# name = "{name}"
# description = "{description}"
# framework = "streamlit"
# group = "Data"
# ///
import streamlit as st

st.write("{description}")
"""


def test_the_projects_widgets_are_listed_first_and_win_over_the_librarys(
    served: tuple[TestClient, FakeRunner, Path], monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    client, _, project = served
    as_agent(client, monkeypatch)
    made = commands.COMMANDS["widgets_new"].run({"name": "orders_strip", "description": "In the library"})
    assert made["where"] == "library"
    (project / "widgets").mkdir(exist_ok=True)
    (project / "widgets" / "orders_strip.widget.py").write_text(
        WIDGET.format(name="orders_strip", description="The project's own"), encoding="utf-8"
    )
    (project / "widgets" / "api_bridge.widget.py").write_text(
        WIDGET.format(name="api_bridge", description="A bridge"), encoding="utf-8"
    )
    listed = ok(client.get("/streamlit/widgets", headers=AUTH))["widgets"]
    assert [w["where"] for w in listed[:2]] == ["project", "project"]
    strip = next(w for w in listed if w["name"] == "orders_strip")
    assert (
        strip["where"] == "project"
        and strip["hides"] == ["library"]
        and strip["description"] == "The project's own"
    )
    assert sum(w["name"] == "orders_strip" for w in listed) == 1
    # saved where it lives (the project's file), never the library's
    commands.COMMANDS["widgets_save"].run(
        {"name": "orders_strip", "code": "import streamlit as st\nst.write(1)\n"}
    )
    assert "st.write(1)" in (project / "widgets" / "orders_strip.widget.py").read_text(encoding="utf-8")
    # Copy to library: the same name in the library
    copied = commands.COMMANDS["widgets_copy"].run({"name": "api_bridge", "to": "library"})
    assert copied["name"] == "api_bridge" and copied["to"] == "library"
    listed = ok(client.get("/streamlit/widgets", headers=AUTH))["widgets"]
    assert next(w for w in listed if w["name"] == "api_bridge")["hides"] == ["library"]
    # Copy to project of a library widget, and a new widget made in the project
    commands.COMMANDS["widgets_new"].run({"name": "kpi_line", "description": "x"})
    assert commands.COMMANDS["widgets_copy"].run({"name": "kpi_line", "to": "project"})["where"] == "project"
    assert (project / "widgets" / "kpi_line.widget.py").is_file()
    assert (
        commands.COMMANDS["widgets_new"].run({"name": "mine_here", "where": "project"})["where"] == "project"
    )
    # Export carries the project's own widgets the canvas uses, inlined in widgets.py (the fewest files)
    canvas = ok(
        client.post("/streamlit/canvases", headers=AUTH, json={"name": "Sales", "folder": str(project)})
    )
    cid = canvas["canvas"]
    ok(client.post(f"/streamlit/canvases/{cid}/command", headers=AUTH, json={"kind": "add_container"}))
    ok(
        client.post(
            f"/streamlit/canvases/{cid}/command",
            headers=AUTH,
            json={"kind": "insert_widget", "parent": "c1", "widget": "orders_strip"},
        )
    )
    out = tmp_path / "exported"
    done = ok(client.post(f"/streamlit/canvases/{cid}/export", headers=AUTH, json={"folder": str(out)}))
    inlined = (out / "widgets.py").read_text(encoding="utf-8")
    assert "CODE['orders_strip']" in inlined and "st.write(1)" in inlined
    assert "kpi_line" not in inlined  # not on the canvas
    assert not any(f.startswith("widgets/") for f in done["files"])
    assert done["variables"] == []  # it calls no API


def test_hidden_and_a_sandbox_table_through_the_agents_commands(
    served: tuple[TestClient, FakeRunner, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    client, runner, _project = served
    as_agent(client, monkeypatch)
    ok(client.post("/sandbox/tables", headers=AUTH, json={"from": "grid", "table": "orders"}))
    context = ok(client.get("/streamlit/widgets/context", headers=AUTH))
    assert "[Sandbox].orders" in context["connection_tables"]["Sandbox"]
    cid = commands.COMMANDS["canvas_open"].run({"name": "Sales"})["canvas"]
    commands.COMMANDS["canvas_add_container"].run({"canvas": cid, "x": 0, "y": 0, "w": 600, "h": 300})
    commands.COMMANDS["canvas_insert_widget"].run(
        {"canvas": cid, "parent": "c1", "widget": "input_data_editor"}
    )
    wired = commands.COMMANDS["canvas_wire"].run(
        {"canvas": cid, "id": "w1", "port": "table_name", "wire": {"table": "[Sandbox].orders"}}
    )
    assert wired["wiring"]["sources"]["w1"]["table_name"] == {"table": "[Sandbox].orders"}
    commands.COMMANDS["canvas_insert_widget"].run(
        {"canvas": cid, "parent": "c1", "widget": "metric", "y": 200}
    )
    hidden = commands.COMMANDS["canvas_move"].run({"canvas": cid, "id": "w2", "hidden": True})
    assert model.find(hidden["model"], "w2")[2]["hidden"] is True
    ok(client.post(f"/streamlit/canvases/{cid}/play", headers=AUTH, json={"python": "/p"}))
    folder = Path(runner.started[-1][1])
    stem = build.table_stem("[Sandbox].orders")
    table = pq.read_table(folder / "data" / f"{stem}.parquet")
    assert table.column("region").to_pylist() == ["North", "South", "West"]  # the sandbox's copy
    page = (folder / "app_pages" / "page_1.py").read_text(encoding="utf-8")
    assert "sab.render('metric'" in page and ".st-key-sab-w2 {" in page
    # a wire across pages through the agent; the state carries its stub's page
    commands.COMMANDS["canvas_page"].run({"canvas": cid, "name": "Reports"})
    state = commands.COMMANDS["canvas_state"].run({"canvas": cid})
    reports = state["model"]["pages"][1]["id"]
    commands.COMMANDS["canvas_add_container"].run({"canvas": cid, "page": reports})
    commands.COMMANDS["canvas_insert_widget"].run(
        {"canvas": cid, "page": reports, "parent": "c2", "widget": "data_table"}
    )
    across = commands.COMMANDS["canvas_wire"].run(
        {"canvas": cid, "id": "w3", "port": "table_name", "wire": {"out": "w1.value"}}
    )
    line = next(w for w in across["wiring"]["wires"] if w["to"] == "w3.table_name")
    assert line["cross"] is True and line["page"] == state["model"]["pages"][0]["id"]


def test_play_records_an_outs_columns_and_the_canvas_offers_them(
    served: tuple[TestClient, FakeRunner, Path],
) -> None:
    client, runner, project = served
    cid = ok(
        client.post("/streamlit/canvases", headers=AUTH, json={"name": "Sales", "folder": str(project)})
    )["canvas"]
    ok(client.post(f"/streamlit/canvases/{cid}/command", headers=AUTH, json={"kind": "add_container"}))
    ok(
        client.post(
            f"/streamlit/canvases/{cid}/command",
            headers=AUTH,
            json={"kind": "insert_widget", "parent": "c1", "widget": "input_data_editor"},
        )
    )
    ok(client.post(f"/streamlit/canvases/{cid}/play", headers=AUTH, json={"python": "/p"}))
    folder = Path(runner.started[-1][1])
    (folder / ".sab_columns.json").write_text(json.dumps({"w1.value": ["region", "amount"]}))
    state = ok(client.get(f"/streamlit/canvases/{cid}", headers=AUTH))
    assert state["wiring"]["columns"]["w1.value"] == ["region", "amount"]
    # Launch records them too (the owner approved, 2026-11-21): a launched run's names, never its rows.
    ok(client.post(f"/streamlit/canvases/{cid}/play", headers=AUTH, json={"stop": "play"}))
    ok(client.post(f"/streamlit/canvases/{cid}/launch", headers=AUTH, json={"python": "/p"}))
    launched = Path(runner.started[-1][1])
    assert launched != folder
    (launched / ".sab_columns.json").write_text(json.dumps({"w1.value": ["region", "amount", "store"]}))
    state = ok(client.get(f"/streamlit/canvases/{cid}", headers=AUTH))
    assert state["wiring"]["columns"]["w1.value"] == ["region", "amount", "store"]


def test_a_local_play_knows_this_computers_user_a_shared_one_does_not() -> None:
    import inspect

    from swissarmybench_streamlit.server import streamlit_apps

    text = inspect.getsource(streamlit_apps.start)
    assert 'environ.pop("SAB_LOCAL_VIEWER", None)' in text and "if not shared:" in text
    assert streamlit_apps.local_user() == __import__("getpass").getuser()
    # the runtime trusts App Service's sign-in headers only on App Service, else st.user, else this computer
    runtime = build.RUNTIME
    assert 'if os.environ.get("WEBSITE_SITE_NAME"):' in runtime and 'UNKNOWN = "unknown"' in runtime


# ===== the viewer's other claims (the owner approved, 2026-11-21) =====


def _runtime(monkeypatch: pytest.MonkeyPatch, headers: dict[str, str], user: Any = None) -> dict[str, Any]:
    """sab_canvas's own text run with stand-ins for Streamlit (its request's headers, st.user) and the
    widgets module: what viewer_info() reads."""
    import sys
    import types

    st = types.ModuleType("streamlit")
    st.context = types.SimpleNamespace(headers=headers)  # type: ignore[attr-defined]
    st.user = user or types.SimpleNamespace(is_logged_in=False)  # type: ignore[attr-defined]
    st.session_state = {}  # type: ignore[attr-defined]
    widgets = types.ModuleType("sab_widgets")
    monkeypatch.setitem(sys.modules, "streamlit", st)
    monkeypatch.setitem(sys.modules, "sab_widgets", widgets)
    namespace: dict[str, Any] = {"__name__": "sab_canvas_test", "__file__": "/nowhere/sab_canvas.py"}
    exec(compile(build.RUNTIME, "sab_canvas.py", "exec"), namespace)  # noqa: S102 (the app's own runtime)
    return namespace


def _principal(claims: list[tuple[str, str]], role_typ: str = "roles") -> str:
    import base64

    body = {
        "auth_typ": "aad",
        "name_typ": "name",
        "role_typ": role_typ,
        "claims": [{"typ": t, "val": v} for t, v in claims],
    }
    return base64.b64encode(json.dumps(body).encode()).decode().rstrip("=")


def test_the_viewers_email_id_and_roles_come_only_from_the_hosts_sign_in(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import types

    claims = [
        ("name", "Ada Ashdown"),
        ("preferred_username", "ada@larkfield.example"),
        ("http://schemas.microsoft.com/identity/claims/objectidentifier", "0000-made-up-oid"),
        ("roles", "Approver"),
        ("roles", "Clerk"),
    ]
    headers = {
        "X-MS-CLIENT-PRINCIPAL-NAME": "ada@larkfield.example",
        "X-MS-CLIENT-PRINCIPAL": _principal(claims),
    }
    monkeypatch.setenv("WEBSITE_SITE_NAME", "made-up-app")
    monkeypatch.delenv("SAB_LOCAL_VIEWER", raising=False)
    assert _runtime(monkeypatch, headers)["viewer"]() == {
        "name": "ada@larkfield.example",
        "email": "ada@larkfield.example",
        "id": "0000-made-up-oid",
        "roles": ["Approver", "Clerk"],
        "via": "app service",
    }
    # Off App Service the same headers are anyone's: not trusted; this computer gives a name only.
    monkeypatch.delenv("WEBSITE_SITE_NAME")
    monkeypatch.setenv("SAB_LOCAL_VIEWER", "ada.ashdown")
    local = _runtime(monkeypatch, headers)["viewer_info"]()
    assert local == {"name": "ada.ashdown", "email": "", "id": "", "roles": [], "via": "this computer"}

    class User(types.SimpleNamespace):
        def get(self, key: str) -> Any:
            return getattr(self, key, None)

    # Streamlit's own sign-in: its name and email, nothing invented.
    signed = _runtime(monkeypatch, {}, User(is_logged_in=True, email="bo@larkfield.example"))["viewer_info"]()
    assert signed == {
        "name": "bo@larkfield.example",
        "email": "bo@larkfield.example",
        "id": "",
        "roles": [],
        "via": "streamlit",
    }
    assert _runtime(monkeypatch, {})["principal_claims"]("not base64 !") == {}
    # The app's Outs: an In of the same name takes each by itself.
    assert {k: v["type"] for k, v in wiring.APP_OUTS.items()} == {
        "app.viewer": "str",
        "app.viewer_email": "str",
        "app.viewer_id": "str",
        "app.viewer_roles": "list[str]",
    }


def test_a_text_in_takes_a_number_a_page_value_holds_as_its_text(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test app two (2026-11-22): an Event set a page value from its payload's work_order_id (a number); an
    input_text's default_from (In[str]) wired to that page value handed st.text_input the number, which
    refused it ("bad argument type for built-in operation") and the widget failed in its place."""
    import datetime

    runtime = _runtime(monkeypatch, {})
    runtime["st"].session_state["last_visit"] = 1003
    assert runtime["_source"]({"page": "last_visit"}, "str", None, "default_from") == "1003"
    assert runtime["_coerce"](2.5, "str", "x") == "2.5"
    assert runtime["_coerce"](datetime.date(2026, 11, 2), "str", "x") == "2026-11-02"
    assert runtime["_coerce"]("text", "str", "x") == "text" and runtime["_coerce"](7, "int", "x") == 7
