"""A widget's I/O contract (the owner, 2026-11-21: "Make a way for input and out from widgets to be defined and
clear"): Ins, Outs and Events read from the code with ast (domain/widget_contract.py), the types and their
checks, the canvas's wiring (domain/canvas_wiring.py: sources, automatic wires, readers, a wire broken by a
delete, the run order), an older canvas's table value wired as it opens, Upgrade to In/Out
(domain/widget_upgrade.py); over HTTP the wire refused in place with the reason; with Streamlit, the built page
passing values between two widgets and an export running alone with AppTest. Made-up data only."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any

import pytest
from starlette.testclient import TestClient

from swissarmybench_streamlit.domain import canvas_build as build
from swissarmybench_streamlit.domain import canvas_layouts as layouts
from swissarmybench_streamlit.domain import canvas_model as engine
from swissarmybench_streamlit.domain import canvas_wiring as wiring
from swissarmybench_streamlit.domain import widget_contract as contract
from swissarmybench_streamlit.domain import widget_properties as props
from swissarmybench_streamlit.domain import widget_upgrade as upgrade
from swissarmybench_streamlit.domain.widget_contract import ContractError, Port
from swissarmybench_streamlit.server.live_runs import CHECK_RUNNER
from tests.conftest import AUTH
from tests.test_canvas_routes import command, ok, opened, served  # noqa: F401
from tests.test_widgets_apptest import PYTHON, needs_streamlit

CODE = """import streamlit as st
import sab_canvas
from sab_canvas import Event, In, Out, Table

# The orders to show
orders: In[Table] = None
region: In[str] = "All"
picked: Out[int] = None
filtered: Out[Table] = None
saved: Event[dict]
nested: sab_canvas.In["list[str]"] = None
quoted: "Out[bool]" = None
title = "Orders"
x = "month"  # column of orders
_private: In[str] = None
region: In[int] = 3
if True:
    inside: In[str] = None


def f():
    local: In[str] = None
"""


def test_the_contract_is_read_from_the_code_and_never_from_running_it() -> None:
    found = {p.name: p for p in contract.detect(CODE)}
    assert list(found) == ["orders", "region", "picked", "filtered", "saved", "nested", "quoted"]
    assert (found["orders"].direction, found["orders"].type, found["orders"].help) == (
        "in",
        "Table",
        "The orders to show",
    )
    assert (
        found["region"].default == "All" and found["region"].type == "str"
    )  # declared twice: the first counts
    assert (found["picked"].direction, found["picked"].type) == ("out", "int")
    assert (found["saved"].direction, found["saved"].type, found["saved"].problem) == ("event", "dict", None)
    assert found["nested"].type == "list[str]" and found["quoted"].type == "bool"
    assert all(p.problem is None for p in found.values())
    # The declarations are the contract, never properties; a column's table may be an In.
    properties = {p.name: p for p in props.detect(CODE)}
    assert list(properties) == ["title", "x"] and properties["x"].of == "orders"
    shown = contract.contract(CODE)
    assert [p["name"] for p in shown["ins"]] == ["orders", "region", "nested"]
    assert [p["words"] for p in shown["outs"]] == ["a whole number", "a table", "yes or no"]


def test_a_declaration_that_does_not_read_says_why_in_one_sentence() -> None:
    code = (
        "from sab_canvas import In, Out, Event\n"
        "a: In[Money] = None\n"
        "b: Out = None\n"
        "c: In[int] = 'three'\n"
        "d: In[list[list[int]]] = None\n"
        "e: Event[dict] = {'x': 1}\n"
        "f: Out[str] = make()\n"
    )
    found = {p.name: p.problem for p in contract.detect(code)}
    assert found["a"] is not None and found["a"].startswith("Money is not a type here")
    assert found["b"] == "b's Out needs a type: Out[str]."
    assert found["c"] == "c's starting value is not a whole number."
    assert found["d"] == "A list of lists is not a type here: list[str] is."
    assert found["e"] is not None and "is an Event: it has no value" in found["e"]
    assert found["f"] == "f's starting value is code: give a plain value or None."
    with pytest.raises(props.PropertyError):
        contract.detect("x: In[str] = (\n")
    # The declarations made `pass`, their lines kept (a traceback's line is the widget's own).
    stripped = contract.without_declarations(CODE, contract.detect(CODE))
    assert (
        stripped.count("\n") == CODE.count("\n")
        and "orders: In" not in stripped
        and 'title = "Orders"' in stripped
    )


def test_types_fit_and_a_typed_value_is_checked() -> None:
    assert contract.fits("int", "float") and not contract.fits("float", "int")
    assert contract.fits("list[dict]", "Table") and not contract.fits("Table", "dict")
    assert contract.fits("list[str]", "list") and contract.fits("list", "list[str]")
    assert contract.fits_value("date", "2026-02-28") and not contract.fits_value("date", "2026-02-30")
    assert contract.fits_value("list[int]", [1, 2]) and not contract.fits_value("list[int]", [1, "2"])
    assert contract.fits_value("Table", [{"a": 1}]) and not contract.fits_value("Table", {"a": [1]})
    assert (
        contract.words("list[str]") == "a list of text"
        and contract.words("list[Table]") == "a list of tables"
    )


def _ports(code: str) -> list[Port]:
    return contract.detect(code)


def test_a_wire_is_refused_in_place_with_the_reason() -> None:
    orders = Port("orders", "in", "Table")
    count = Port("count", "in", "int")
    context = wiring.Context({"w1.uploaded": "Table", "w2.n": "int"}, {"GET /orders"}, {"REGION"}, {"orders"})
    wiring.check_in(orders, {"out": "w1.uploaded"}, context)
    wiring.check_in(orders, {"table": "orders"}, context)
    wiring.check_in(orders, {"endpoint": "GET /orders"}, context)
    wiring.check_in(count, {"value": 3}, context)
    wiring.check_in(
        Port("many", "in", "list[Table]"), {"tables": [{"table": "orders"}, {"out": "w1.uploaded"}]}, context
    )
    for port, wire, said in [
        (count, {"out": "w1.uploaded"}, "count takes a whole number: w1.uploaded gives a table."),
        (orders, {"out": "w9.gone"}, "No widget on this page has an Out w9.gone."),
        (orders, {"table": "nope"}, "There is no table called nope here."),
        (count, {"endpoint": "GET /orders"}, "count takes a whole number: an endpoint answers JSON."),
        (orders, {"endpoint": "POST /orders"}, "orders reads a GET endpoint's answer, as GET /orders."),
        (count, {"value": "three"}, "count takes a whole number: that value is not."),
        (orders, {"variable": "MISSING"}, "MISSING is not set on this computer."),
        (orders, {"elsewhere": 1}, "orders's source is one of"),
    ]:
        with pytest.raises(ContractError) as error:
            wiring.check_in(port, wire, context)
        assert str(error.value).startswith(said), (wire, str(error.value))
    saved = Port("saved", "event", "dict")
    wiring.check_event(
        saved,
        {"actions": [{"do": "call", "endpoint": "POST /visits", "body": "values"}, {"do": "rerun"}]},
        {"POST /visits"},
    )
    for wire in (
        {"actions": [{"do": "explode"}]},
        {"actions": [{"do": "call", "endpoint": "POST /nope"}]},
        {"actions": [{"do": "set", "key": "has space"}]},
        {"actions": [{"do": "call", "endpoint": "POST /visits", "body": {"store": "values.store; drop"}}]},
    ):
        with pytest.raises(ContractError):
            wiring.check_event(saved, wire, {"POST /visits"})


WRITER = "from sab_canvas import Out, Table\nuploaded: Out[Table] = None\nlabel = 'x'\n"
READER = "from sab_canvas import In, Table\nuploaded: In[Table] = None\nother: In[str] = None\n"


def _canvas(nodes: list[dict[str, Any]]) -> dict[str, Any]:
    canvas = layouts.new_canvas("Wired")
    children = []
    for at, node in enumerate(nodes):
        place = {"x": 0.0, "y": node.get("y", at * 100), "w": 0.5, "h": 90}
        children.append(
            {"id": node["id"], "kind": "widget", "widget": node["widget"], "show": "both",
             "at": {"desktop": place, "phone": place}, "values": {}, **({"wires": node["wires"]} if "wires" in node else {})}
        )  # fmt: skip
    canvas["pages"][0]["children"] = children
    return canvas


def test_the_wiring_finds_sources_readers_automatic_wires_and_a_wire_broken_by_a_delete() -> None:
    contracts = {"writer": _ports(WRITER), "reader": _ports(READER)}
    canvas = _canvas(
        [
            {"id": "w1", "widget": "reader", "y": 0, "wires": {"other": {"value": "hi"}}},
            {"id": "w2", "widget": "writer", "y": 200},
            {"id": "w3", "widget": "reader", "y": 400, "wires": {"uploaded": {"out": "w2.uploaded"}}},
        ]
    )
    found = wiring.analyse(canvas, contracts)
    assert found["sources"]["w1"] == {
        "other": {"value": "hi"},
        "uploaded": {"out": "w2.uploaded"},
    }  # automatic
    assert found["readers"]["w2.uploaded"] == ["w1.uploaded", "w3.uploaded"]
    assert {(w["from"], w["to"], w["auto"]) for w in found["wires"]} == {
        ("w2.uploaded", "w1.uploaded", True),
        ("w2.uploaded", "w3.uploaded", False),
    }
    assert found["broken"] == []
    # The reader placed above runs after the writer (each placed by its CSS, so the order is free).
    order = wiring.order(canvas["pages"][0]["children"], wiring.needs(found["sources"]))
    assert [n["id"] for n in order] == ["w2", "w1", "w3"]
    # The writer deleted: its wire is broken, said on the reading end and listed; the automatic one is gone.
    after, _ = layouts.apply(canvas, "delete", {"id": "w2"}, {})
    gone = wiring.analyse(after, contracts)
    assert gone["broken"] == [
        {
            "instance": "w3",
            "port": "uploaded",
            "reason": "The widget w2 it read from was deleted.",
            "source": "w2.uploaded",
        }
    ]
    assert gone["sources"]["w3"]["uploaded"] == {"broken": "The widget w2 it read from was deleted."}
    assert "uploaded" not in gone["sources"]["w1"]
    # An Out whose type changed: broken too.
    contracts["writer"] = _ports("from sab_canvas import Out\nuploaded: Out[str] = None\n")
    changed = wiring.analyse(canvas, contracts)
    assert changed["broken"][0]["reason"] == "uploaded takes a table: w2.uploaded gives text."


def test_an_older_canvas_table_value_is_wired_as_it_opens() -> None:
    facts = {
        "reader": engine.WidgetFacts(
            (4, 2), (1, 1), frozenset({"label"}), frozenset({"orders"}), (("orders", "Table"),)
        )
    }
    node = {"id": "w1", "kind": "widget", "widget": "reader", "values": {"orders": "sales", "label": "Hi"}}
    assert engine.take_ins(node, facts["reader"]) == ["orders"]
    assert node == {
        "id": "w1",
        "kind": "widget",
        "widget": "reader",
        "values": {"label": "Hi"},
        "wires": {"orders": {"table": "sales"}},
    }
    assert wiring.tables(
        _canvas(
            [
                {
                    "id": "w1",
                    "widget": "reader",
                    "wires": {"orders": {"table": "sales"}, "x": {"tables": [{"table": "b"}]}},
                }
            ]
        )
    ) == {"sales", "b"}


def test_upgrade_to_in_out_rewrites_session_state_keys_as_declarations() -> None:
    code = (
        'import streamlit as st\nfrom sab_canvas import key\n\n# Where the rows come from\nin_key = "uploaded"\n'
        "label = \"Pick\"\n\nfound = st.session_state.get(in_key)\nchoice = st.selectbox(label, ['a'], key=key('p'))\n"
        'st.session_state["picked"] = choice\nif "picked" in st.session_state:\n    st.write(st.session_state.get("picked", "none"))\n'
        'def f():\n    st.session_state["later"] = 1\n'
    )
    found = upgrade.plan(code)
    assert [(c["port"], c["direction"], c["type"]) for c in found["changes"]] == [
        ("picked", "out", "str"),
        ("uploaded", "in", "Table"),
    ]
    assert found["kept"] == ["later: line 14: a write inside a block or a function"]
    after = found["code"]
    assert (
        "from sab_canvas import In, Out, Table, key" in after
        and "in_key" not in after
        and "Where the rows" not in after
    )
    assert "found = uploaded" in after and "picked = choice" in after and "if picked is not None:" in after
    assert [(p.name, p.direction) for p in contract.detect(after)] == [("picked", "out"), ("uploaded", "in")]
    assert found["diff"].startswith("--- before")
    assert upgrade.plan("import streamlit as st\nst.write(1)\n")["changes"] == []


def test_a_wire_over_http_is_refused_with_its_reason_and_a_delete_marks_it_broken(
    served: tuple[TestClient, Any, Path],  # noqa: F811
) -> None:
    client, _runner, project = served
    canvas = opened(client, project)["canvas"]
    ok(command(client, canvas, "add_container", x=0, y=0, w=1200, h=900))
    up = ok(command(client, canvas, "insert_widget", parent="c1", widget="excel_upload", x=0, y=0))["made"]
    shown = ok(command(client, canvas, "insert_widget", parent="c1", widget="data_table", x=0, y=500))["made"]
    number = ok(command(client, canvas, "insert_widget", parent="c1", widget="input_number", x=700, y=500))[
        "made"
    ]
    state = ok(command(client, canvas, "wire", id=shown, port="table_name", wire={"out": f"{up}.uploaded"}))
    assert state["wiring"]["readers"][f"{up}.uploaded"] == [f"{shown}.table_name"]
    assert state["wiring"]["ports"][up]["outs"][0]["name"] == "uploaded"
    refused = command(client, canvas, "wire", id=number, port="default_from", wire={"out": f"{up}.uploaded"})
    assert (
        refused.status_code == 400
        and f"default_from takes a number: {up}.uploaded gives a table." in refused.text
    )
    event = command(client, canvas, "wire", id=number, port="nothing", wire={"value": 1})
    assert event.status_code == 400
    on_disk = json.loads((project / "sales.canvas.json").read_text())
    assert engine.find(on_disk, shown)[2]["wires"] == {"table_name": {"out": f"{up}.uploaded"}}
    after = ok(command(client, canvas, "delete", id=up))
    assert after["wiring"]["broken"] == [
        {
            "instance": shown,
            "port": "table_name",
            "reason": f"The widget {up} it read from was deleted.",
            "source": f"{up}.uploaded",
        }
    ]
    undone = ok(client.post(f"/streamlit/canvases/{canvas}/undo", headers=AUTH))
    assert undone["wiring"]["broken"] == []


# ===== the built page, run =====


def _run(folder: Path, files: dict[str, str], pages: list[str]) -> list[dict[str, Any]]:
    for name, text in files.items():
        (folder / name).parent.mkdir(parents=True, exist_ok=True)
        (folder / name).write_text(text, encoding="utf-8")
    (folder / "check.json").write_text(json.dumps({"pages": pages}), encoding="utf-8")
    assert PYTHON is not None
    done = subprocess.run(
        [PYTHON, "-I", "-c", CHECK_RUNNER, str(folder)],
        capture_output=True,
        text=True,
        timeout=600,
        cwd=folder,
        check=False,
    )
    line = next((x for x in reversed(done.stdout.splitlines()) if x.startswith("SAB-CHECK ")), None)
    assert line, done.stdout[-2000:] + done.stderr[-2000:]
    found: list[dict[str, Any]] = json.loads(line[len("SAB-CHECK ") :])
    return found


PICKER = """import streamlit as st
from sab_canvas import Event, In, Out, Table, sample

rows: In[Table] = None
picked: Out[str] = None
told: Event[dict] = None

frame = rows if rows is not None else sample()
picked = str(frame["region"].iloc[1])
told({"region": picked})
"""
SHOWER = """import streamlit as st
from sab_canvas import In

picked: In[str] = "nothing"
st.metric("Picked", picked)
"""


@needs_streamlit
def test_the_built_page_passes_values_between_two_widgets_and_the_export_runs_alone(tmp_path: Path) -> None:
    """The reader is placed above the writer: the page still runs the writer first, so the value arrives on
    the first run. The export's files run with AppTest in a folder of their own, without the app."""
    built = {"picker": build.made(PICKER), "shower": build.made(SHOWER)}
    canvas = _canvas(
        [
            {"id": "w1", "widget": "shower", "y": 0},
            {
                "id": "w2",
                "widget": "picker",
                "y": 200,
                "wires": {"told": {"actions": [{"do": "set", "key": "last", "value": "region"}]}},
            },
        ]
    )
    files = build.build(canvas, built)
    assert not build.compiles(files)
    page = files["app_pages/page_1.py"]
    assert page.index("'picker'") < page.index("'shower'")
    assert "{'picked': {'out': 'w2.picked'}}" in page or '{"picked": {"out": "w2.picked"}}' in page
    export = tmp_path / "export"
    found = _run(export, files, ["app_pages/page_1.py"])[0]
    assert found["exceptions"] == [] and found["errors"] == [], found
    assert found["kinds"]["metric"] == 1
    # The metric shows the picker's value: read it back with AppTest directly.
    probe = (
        "import os, sys; sys.path.insert(0, os.getcwd())\n"
        "from streamlit.testing.v1 import AppTest\n"
        "at = AppTest.from_file('app_pages/page_1.py', default_timeout=60); at.run()\n"
        "print('SAB', at.metric[0].value, at.session_state['last'], at.session_state['sab:w2.told'])\n"
    )
    assert PYTHON is not None
    done = subprocess.run(
        [PYTHON, "-I", "-c", probe], capture_output=True, text=True, timeout=300, cwd=export, check=False
    )
    line = next(x for x in done.stdout.splitlines() if x.startswith("SAB "))
    assert line == "SAB South South {'region': 'South'}", done.stderr[-2000:]
