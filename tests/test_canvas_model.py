"""The Canvas's file and rules (domain/canvas_model.py) and the page built from it (domain/canvas_build.py):
every place in pixels, nothing overlaps or leaves its box, a widget never smaller than its minimum, the
columns a guide that re-flows, a file that does not read reported with its line, a newer one read-only, and a
many-case run of random commands keeping every rule after each step with a page that compiles. Made-up data
only."""

from __future__ import annotations

import json
import random
from typing import Any

import pytest

from swissarmybench_streamlit.domain import canvas_build as build
from swissarmybench_streamlit.domain import canvas_model as model
from swissarmybench_streamlit.domain import widget_properties as props
from swissarmybench_streamlit.domain.canvas_model import CanvasError, WidgetFacts

FACTS = {
    "metric": WidgetFacts((3, 2), (2, 1), frozenset({"label", "value"})),
    "chart": WidgetFacts((6, 4), (3, 2), frozenset({"table_name", "colour"})),
}
BUILT = {
    "metric": build.Built(
        'import streamlit as st\n\nlabel = "Revenue"\nvalue = 42\n\nst.metric(label, value)\n',
        tuple(props.detect('label = "Revenue"\nvalue = 42\n')),
    ),
    "chart": build.Built(
        'import streamlit as st\n\ntable_name = ""  # table\ncolour = "#1f77b4"\n\n'
        "st.write(table_name, colour)\n",
        tuple(props.detect('table_name = ""  # table\ncolour = "#1f77b4"\n')),
    ),
}


def run(canvas: dict[str, Any], kind: str, **body: Any) -> tuple[dict[str, Any], str | None]:
    return model.apply(canvas, kind, body, FACTS)


def test_a_new_canvas_reads_back_byte_for_byte() -> None:
    canvas = model.new_canvas("Sales")
    text = model.write(canvas)
    assert model.read(text, FACTS).canvas == canvas
    assert model.write(model.read(text, FACTS).canvas) == text
    assert canvas["sizing"] == {
        "columns": 12,
        "row_height": 60,
        "gap": 8,
        "width": "wide",
        "snap": True,
        "step": 1,
    }


def test_containers_and_widgets_keep_their_exact_pixels() -> None:
    canvas, c1 = run(model.new_canvas("S"), "add_container", x=13, y=7, w=401, h=203)
    canvas, w1 = run(canvas, "insert_widget", parent=c1, widget="metric", x=5, y=3)
    _, _, node = model.find(canvas, str(w1))
    assert (node["x"], node["y"]) == (5, 3)
    canvas = run(canvas, "move", id=c1, x=14, y=9)[0]
    _, _, container = model.find(canvas, str(c1))
    assert (container["x"], container["y"], container["w"], container["h"]) == (14, 9, 401, 203)


def test_nothing_overlaps_or_leaves_its_box() -> None:
    canvas, c1 = run(model.new_canvas("S"), "add_container", x=0, y=0, w=400, h=200)
    canvas, c2 = run(canvas, "add_container", x=420, y=0, w=300, h=200)
    with pytest.raises(CanvasError, match="taken by c1"):
        run(canvas, "move", id=c2, x=399, y=0)
    with pytest.raises(CanvasError, match="past the right of the page"):
        run(canvas, "move", id=c2, x=1000, y=0)
    canvas, w1 = run(canvas, "insert_widget", parent=c1, widget="metric", x=0, y=0)
    with pytest.raises(CanvasError, match="out of its container at the bottom"):
        run(canvas, "move", id=w1, x=0, y=150)
    with pytest.raises(CanvasError, match="cannot be smaller than"):
        run(canvas, "move", id=w1, w=20)
    with pytest.raises(CanvasError, match="what it holds needs that"):
        run(canvas, "move", id=c1, h=50)
    with pytest.raises(CanvasError, match="A widget goes in a container"):
        run(canvas, "move", id=w1, parent="")
    with pytest.raises(CanvasError, match="cannot go inside itself"):
        canvas2, c3 = run(canvas, "add_container", parent=c1, x=300, y=0, w=50, h=40)
        run(canvas2, "move", id=c1, parent=c3)


def test_a_widget_dropped_into_a_full_container_grows_it() -> None:
    canvas, c1 = run(model.new_canvas("S"), "add_container", x=0, y=0, w=300, h=60)
    canvas, _ = run(canvas, "add_container", x=0, y=70, w=300, h=60)
    canvas, _ = run(canvas, "insert_widget", parent=c1, widget="chart")
    _, _, container = model.find(canvas, str(c1))
    assert container["h"] >= container["children"][0]["h"]
    assert not model.problems(canvas, FACTS)  # the container below moved down


def test_insert_with_no_container_makes_one_around_it() -> None:
    canvas, made = run(model.new_canvas("S"), "insert_widget", widget="metric", x=100, y=40)
    _, parent, node = model.find(canvas, str(made))
    assert parent is not None and parent["kind"] == "container" and (parent["x"], parent["y"]) == (100, 40)
    assert node["x"] == parent["props"]["padding"]


def test_scrollable_needs_a_fixed_height_and_is_set_with_it() -> None:
    canvas, c1 = run(model.new_canvas("S"), "add_container")
    canvas = run(canvas, "set_container", id=c1, props={"scrollable": True})[0]
    assert model.find(canvas, str(c1))[2]["props"]["height"] == "fixed"
    with pytest.raises(CanvasError, match="background is a colour"):
        run(canvas, "set_container", id=c1, props={"background": "blue"})


def test_columns_are_a_guide_that_reflows_and_width_scales() -> None:
    canvas = model.new_canvas("S")
    lines12 = model.lines(1200, 12, 8)
    left, right = round(lines12[2]), round(lines12[7])  # column 2's left edge to column 4's right edge
    canvas, c1 = run(canvas, "add_container", x=left, y=0, w=right - left, h=100)
    canvas, _ = run(canvas, "add_container", x=right + 3, y=0, w=200, h=100)  # off the lines: stays
    after = run(canvas, "sizing", columns=5)[0]
    lines5 = model.lines(1200, 5, 8)
    moved = model.find(after, str(c1))[2]
    assert any(abs(moved["x"] - line) <= 1 for line in lines5)
    assert not model.problems(after, FACTS)
    narrow = run(canvas, "sizing", width="centered")[0]
    assert all(n["x"] + n["w"] <= 704 for _, n in model.walk(narrow) if n["kind"] == "container")
    assert not model.problems(narrow, FACTS)
    with pytest.raises(CanvasError, match="snap step"):
        run(canvas, "sizing", step=3)
    assert run(canvas, "sizing", snap=False, step="grid")[0]["sizing"]["step"] == "grid"


def test_the_file_is_checked_on_read() -> None:
    with pytest.raises(CanvasError) as said:
        model.read('{"format": 1,\n "pages": [\n')
    assert said.value.line == 3
    newer = model.read(json.dumps({"format": 9, "pages": []}))
    assert newer.read_only and "newer version" in newer.read_only
    canvas, c1 = run(model.new_canvas("S"), "add_container", x=0, y=0, w=300, h=100)
    canvas, _ = run(canvas, "insert_widget", parent=c1, widget="metric")
    found = model.read(model.write(canvas), {"chart": FACTS["chart"]})
    assert found.missing == ["w1"]  # the widget is gone: a placeholder, never a crash
    overlapping = json.loads(model.write(canvas))
    overlapping["pages"][0]["children"].append(
        {**overlapping["pages"][0]["children"][0], "id": "c7", "children": []}
    )
    with pytest.raises(CanvasError, match="overlap") as broken:
        model.read(json.dumps(overlapping, indent=2))
    assert broken.value.line


def test_overrides_of_properties_that_went_are_pruned_and_said() -> None:
    canvas, made = run(model.new_canvas("S"), "insert_widget", widget="metric", values={"label": "Sales"})
    model.find(canvas, str(made))[2]["values"]["gone"] = 1
    pruned, said = model.prune(canvas, FACTS)
    assert model.find(pruned, str(made))[2]["values"] == {"label": "Sales"}
    assert said == ["w1 (metric): gone went with the widget's code."]


def test_the_page_reproduces_the_pixels_and_wraps_each_widget() -> None:
    canvas, c1 = run(
        model.new_canvas("Sales"), "add_container", x=13, y=7, w=401, h=203, props={"title": "KPIs"}
    )
    canvas, _ = run(
        canvas, "insert_widget", parent=c1, widget="metric", x=5, y=31, values={"label": "Orders"}
    )
    canvas = run(canvas, "set_container", id=c1, props={"scrollable": True, "resizable": True})[0]
    files = build.build(canvas, BUILT)
    assert not build.compiles(files)
    page = files["app_pages/page_1.py"]
    assert ".st-key-sab-page { position: relative; width: 1200px;" in page
    assert ".st-key-sab-c1 { position: absolute; left: 13px; top: 7px; width: 401px;" in page
    assert ".st-key-sab-w1 { position: absolute; left: 4px; top: 30px;" in page  # inside c1's 1 px border
    assert "resize: both" in page and "with st.container(border=True, height=203, key='sab-c1'):" in page
    assert 'sab.render(\'metric\', {"label": "Orders", "value": 42}, \'w1\')' in page
    assert 'sab.heading("KPIs")' in page
    assert "st.navigation(pages, position='hidden')" in files["app.py"]
    assert "CODE['metric']" in files["sab_widgets.py"] and "CODE['chart']" not in files["sab_widgets.py"]


@pytest.mark.parametrize("seed", range(40))
def test_random_commands_keep_every_rule_and_the_page_compiles(seed: int) -> None:
    """Random sequences of the commands (add, move, resize, nest, insert, delete, undo, redo, columns, width):
    after each step every rule holds and the built pages compile."""
    rng = random.Random(seed)  # noqa: S311 (made-up commands, not secrets)
    canvas = model.new_canvas("Fuzz")
    back: list[dict[str, Any]] = []
    forward: list[dict[str, Any]] = []
    for _step in range(60):
        nodes = [n for _, n in model.walk(canvas)]
        containers = [n["id"] for n in nodes if n["kind"] == "container"]
        ids = [n["id"] for n in nodes]
        choice = rng.choice(
            [
                "add",
                "add",
                "insert",
                "insert",
                "move",
                "resize",
                "nest",
                "delete",
                "undo",
                "redo",
                "columns",
                "width",
                "set",
                "page",
            ]
        )
        body: dict[str, Any] = {}
        kind = ""
        if choice == "undo" and back:
            forward.append(canvas)
            canvas = back.pop()
            continue
        if choice == "redo" and forward:
            back.append(canvas)
            canvas = forward.pop()
            continue
        if choice == "add":
            kind = "add_container"
            body = {
                "parent": rng.choice([None, *containers]),
                "x": rng.choice([None, rng.randint(0, 1100)]),
                "y": rng.randint(0, 600),
                "w": rng.randint(8, 500),
                "h": rng.randint(8, 300),
            }
        elif choice == "insert":
            kind, body = (
                "insert_widget",
                {"widget": rng.choice(list(FACTS)), "parent": rng.choice([None, *containers])},
            )
        elif choice == "move" and ids:
            kind, body = "move", {"id": rng.choice(ids), "x": rng.randint(0, 1200), "y": rng.randint(0, 900)}
        elif choice == "resize" and ids:
            kind, body = "move", {"id": rng.choice(ids), "w": rng.randint(1, 700), "h": rng.randint(1, 400)}
        elif choice == "nest" and ids:
            kind, body = "move", {"id": rng.choice(ids), "parent": rng.choice(["", *containers])}
        elif choice == "delete" and ids:
            kind, body = "delete", {"id": rng.choice(ids)}
        elif choice == "columns":
            kind, body = "sizing", {"columns": rng.randint(1, 24)}
        elif choice == "width":
            kind, body = "sizing", {"width": rng.choice(["wide", "centered"])}
        elif choice == "set" and containers:
            kind, body = (
                "set_container",
                {
                    "id": rng.choice(containers),
                    "props": {"columns": rng.randint(1, 12), "scrollable": rng.random() < 0.5},
                },
            )
        elif choice == "page":
            kind, body = "add_page", {}
        if not kind:
            continue
        try:
            after, _ = model.apply(canvas, kind, body, FACTS)
        except CanvasError:
            continue  # refused: the canvas stays as it was
        back.append(canvas)
        forward.clear()
        canvas = after
        assert model.problems(canvas, FACTS) == [], (seed, kind, body)
        assert model.read(model.write(canvas), FACTS).canvas == canvas
    files = build.build(canvas, BUILT)
    assert build.compiles(files) == []
