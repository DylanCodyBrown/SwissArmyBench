"""A cell's Streamlit code read and written back (the canvas's property pane, 2026-11-19): widgets, keys,
defaults, cache decorators and handlers read with Python's parser, and each change written into ONLY the
characters it names (tests/golden/canvas_code: before and after, comments and formatting kept). A value that
is code is refused. Made-up code only."""

from __future__ import annotations

import ast
import json
from pathlib import Path
from typing import Any

import pytest

from swissarmybench_streamlit.domain import toolbox
from swissarmybench_streamlit.domain import widget_code as wc
from swissarmybench_streamlit.domain.streamlit_cells import keyed

GOLDEN = Path(__file__).parent / "golden" / "canvas_code"
CASES: dict[str, dict[str, Any]] = json.loads((GOLDEN / "cases.json").read_text(encoding="utf-8"))

CELL = """# Region filter
import os
import streamlit as st

region = st.selectbox("Region", ["All", "North"], index=1, key="region_pick", on_change=picked)
least = st.slider("Least", 0, 500, value=default_least)
shown = st.checkbox("Show", value=st.session_state["show_all"])
top = st.number_input("Top", value=int(os.environ["TOP_N"]))
limit = st.number_input("Limit", value=os.environ.get("LIMIT_N"))
token = secret("WAREHOUSE_TOKEN")
st.caption("Reading ${REPORT_FOLDER}, not $${ESCAPED}")
st.sidebar.metric("Total", total())
pick = col.selectbox("Pick", ["a"])
plt.title("not Streamlit")


@st.cache_data(ttl=600, show_spinner="Loading", max_entries=ENTRIES)
def monthly(orders):
    return orders


def plain():
    return 1
"""


def _do(code: str, op: dict[str, Any]) -> wc.Change:
    if op["do"] == "set":
        return wc.set_argument(code, op["index"], op["name"], op["value"])
    if op["do"] == "reset":
        return wc.reset_argument(code, op["index"], op["name"])
    if op["do"] == "handler":
        return wc.add_handler(code, op["index"], op.get("event"))
    if op["do"] == "bind":
        return wc.bind(code, op["index"], op["name"], op["kind"], op["target"])
    return wc.set_cache(code, op["function"], op["kind"], op.get("settings"))


@pytest.mark.parametrize("name", sorted(CASES))
def test_a_change_writes_only_its_own_characters(name: str) -> None:
    before = (GOLDEN / f"{name}.before.txt").read_text(encoding="utf-8")
    after = (GOLDEN / f"{name}.after.txt").read_text(encoding="utf-8")
    change = _do(before, CASES[name])
    assert change.code == after
    # The edits are those characters against the text as it was, and nothing else moved.
    assert wc.apply(before, change.edits) == after
    assert change.edits
    touched = sum(e.end - e.start for e in change.edits) + sum(len(e.text) for e in change.edits)
    assert touched < len(before) / 2
    ast.parse(change.code)
    # Every comment of the cell is still there, unless the change took its own line away.
    kept = [line for line in before.split("\n") if "#" in line and line in after]
    assert len(kept) >= sum("#" in line for line in before.split("\n")) - 1
    # Made again, it changes nothing.
    assert _do(change.code, CASES[name]).edits == () or CASES[name]["do"] == "handler"


def test_a_handler_is_written_once_and_found_again() -> None:
    before = (GOLDEN / "handler.before.txt").read_text(encoding="utf-8")
    made = wc.add_handler(before, 0)
    assert made.handler == "on_region_pick_change" and made.line == 6
    assert made.code.split("\n")[made.line - 1] == "def on_region_pick_change():"
    again = wc.add_handler(made.code, 0)
    assert again.edits == () and again.handler == "on_region_pick_change" and again.line == 6
    # A name in use gets a number; a widget with no event says so.
    taken = wc.add_handler("on_go_click = 1\ngo = st.button('Go')", 0)
    assert taken.handler == "on_go_click_2"
    with pytest.raises(wc.CodeError, match="no event"):
        wc.add_handler('st.metric("Total", 1)', 0)


def test_a_cells_widgets_keys_defaults_and_bindings_are_read() -> None:
    read = wc.read(CELL)
    assert read.problem is None
    assert [w.call for w in read.widgets] == [
        "selectbox", "slider", "checkbox", "number_input", "number_input", "caption", "metric",
        "selectbox",
    ]  # fmt: skip
    region, least, shown, top, limit, _, metric, _ = read.widgets
    assert (region.target, region.key, region.default, region.event) == (
        "region",
        "region_pick",
        "index",
        "on_change",
    )
    assert region.arguments["index"].value == 1 and region.arguments["options"].value == ["All", "North"]
    assert region.arguments["label"].kind == "literal" and region.by_position == ("label", "options")
    assert (region.arguments["on_change"].kind, region.arguments["on_change"].target) == ("name", "picked")
    # A slider's positional arguments have their names; a name, a state key and a variable are bindings.
    assert least.arguments["min_value"].value == 0 and least.arguments["max_value"].value == 500
    assert (least.arguments["value"].kind, least.arguments["value"].target) == ("name", "default_least")
    assert (shown.arguments["value"].kind, shown.arguments["value"].target) == ("state", "show_all")
    assert top.arguments["value"].kind == "expression"  # int(...) is code
    assert (limit.arguments["value"].kind, limit.arguments["value"].target) == ("variable", "LIMIT_N")
    assert metric.arguments["value"].kind == "expression" and not metric.widget
    # The keys the page gives the widgets that have none, numbered as the page numbers them.
    assert [w.auto for w in read.widgets] == [None, 1, 2, 3, 4, None, None, 5]
    said = [w.to_json("b7")["state_key"] for w in read.widgets]
    assert said == ["region_pick", "b7_1", "b7_2", "b7_3", "b7_4", None, None, "b7_5"]
    paged = keyed(CELL, "b7")
    assert all(f'key="{key}"' in paged for key in said if key)
    assert read.variables == ("TOP_N", "LIMIT_N", "WAREHOUSE_TOKEN", "REPORT_FOLDER")
    assert "total" in read.calls and "secret" in read.calls


def test_a_cells_cache_decorators_are_read() -> None:
    monthly, plain = wc.read(CELL).functions
    assert (monthly.name, monthly.cache, monthly.line) == ("monthly", "data", 18)
    assert monthly.settings["ttl"].value == 600 and monthly.settings["show_spinner"].value == "Loading"
    assert monthly.settings["max_entries"].kind == "name"
    assert (plain.name, plain.cache, plain.settings) == ("plain", None, {})


def test_code_that_is_not_a_plain_value_is_refused_and_left_alone() -> None:
    with pytest.raises(wc.NotPlain, match=r"value=int\(os.environ\[\"TOP_N\"\]\) is code, not a plain value"):
        wc.set_argument(CELL, 3, "value", 5)
    with pytest.raises(wc.NotPlain, match="is bound to default_least: unbind it first"):
        wc.set_argument(CELL, 1, "value", 5)
    with pytest.raises(wc.NotPlain, match="max_entries=ENTRIES is code"):
        wc.set_cache(CELL, "monthly", "data", {"max_entries": 5})
    with pytest.raises(wc.NotPlain, match="given by its place"):
        wc.reset_argument(CELL, 0, "options")
    # A binding may be replaced by another, or by an expression; code only by an expression.
    assert 'value=st.session_state["least"])' in wc.bind(CELL, 1, "value", "state", "least").code
    assert "value=len(orders))" in wc.bind(CELL, 3, "value", "expression", "len(orders)").code
    with pytest.raises(wc.NotPlain):
        wc.bind(CELL, 3, "value", "name", "top_default")


@pytest.mark.parametrize(
    ("call", "message"),
    [
        (lambda: wc.set_argument(CELL, 99, "value", 1), "has no Streamlit element 99"),
        (lambda: wc.set_argument("x = 1", 0, "value", 1), "calls no Streamlit element"),
        (lambda: wc.set_argument("st.slider(", 0, "value", 1), "not whole Python yet"),
        (lambda: wc.set_argument(CELL, 0, "index", {"a": object()}), "plain value"),
        (lambda: wc.set_argument(CELL, 0, "in dex", 1), "named as Streamlit names it"),
        (lambda: wc.bind(CELL, 0, "index", "name", "not a name"), "one word"),
        (lambda: wc.bind(CELL, 0, "index", "expression", "x = 1"), "not one whole Python expression"),
        (lambda: wc.bind(CELL, 0, "index", "expression", "(y := 2)"), "does not assign"),
        (lambda: wc.bind(CELL, 0, "index", "file", "x"), "binds to one of"),
        (lambda: wc.set_cache(CELL, "nothing", "data"), "no function called nothing"),
        (lambda: wc.set_cache(CELL, "monthly", "disk"), 'A cache is "data"'),
        (lambda: wc.set_cache(CELL, "monthly", "data", {"ttl": -1}), "ttl is a number of seconds"),
        (lambda: wc.set_cache(CELL, "plain", "data", {"max_entries": 0}), "whole number from 1"),
        (lambda: wc.set_cache(CELL, "monthly", "data", {"speed": 1}), "no setting called 'speed'"),
        (lambda: wc.set_cache(CELL, "plain", "resource", {"persist": "disk"}), "Only st.cache_data"),
    ],
)
def test_a_change_that_cannot_be_made_says_why(call: Any, message: str) -> None:
    with pytest.raises(wc.CodeError, match=message):
        call()


def test_text_is_written_safely_whatever_it_holds() -> None:
    nasty = "He said \"no\"\\ and\n left\t\x07 ${X} 'q' é 日本"
    change = wc.set_argument('st.text_input("Name", value="x")', 0, "value", nasty)
    tree = ast.parse(change.code)
    assert tree.body[0].value.keywords[0].value.value == nasty  # type: ignore[attr-defined]
    # A place counted in UTF-8 bytes by the parser is still the right character.
    wide = 'a = st.text_input("Ñame 日本", value="é")  # ünï'
    assert wc.set_argument(wide, 0, "value", "ok").code == 'a = st.text_input("Ñame 日本", value="ok")  # ünï'
    assert wc.set_argument(wide, 0, "value", "é").edits == ()


def test_nothing_is_written_that_would_not_parse(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(wc, "literal", lambda *a, **k: "(")
    with pytest.raises(wc.CodeError, match="nothing was changed"):
        wc.set_argument('st.slider("A", 0, 9, 1)', 0, "value", 2)


def test_the_toolbox_lists_every_group_and_a_dropped_element_is_whole_python() -> None:
    listed = toolbox.catalog()
    assert listed["groups"] == ["Input", "Data", "Charts", "Text", "Media", "Layout", "Status"]
    ids = {item["id"] for item in listed["items"]}
    for wanted in (
        "text_input number_input slider selectbox multiselect date_input checkbox toggle radio file_uploader "
        "button form_submit_button dataframe data_editor metric table json line_chart bar_chart area_chart "
        "scatter_chart map plotly_chart altair_chart title header markdown caption code divider image "
        "columns tabs expander container form sidebar popover success info warning error spinner progress"
    ).split():
        assert wanted in ids, wanted
    assert all(item["words"] and item["label"] for item in listed["items"])
    assert all(p["words"] for item in listed["items"] for p in item["params"])
    taken: list[str] = []
    for element in toolbox.ELEMENTS.values():
        if not element.code:
            continue
        made = toolbox.cell_code(element.call, taken, ["orders"])
        ast.parse(made.code)
        assert made.code.startswith(f"# {made.name}\n")
        read = wc.read(made.code)
        assert any(w.call == element.call for w in read.widgets), element.call
        if made.variable:
            assert made.variable not in taken
            taken.append(made.variable)
    # A second one of a kind has its own name and key; with no table open a data element brings a sample.
    assert toolbox.cell_code("slider", ["slider_1"]).variable == "slider_2"
    assert 'key="slider_2"' in toolbox.cell_code("slider", ["slider_1"]).code
    assert "pd.DataFrame" in toolbox.cell_code("dataframe").code
    with pytest.raises(toolbox.ToolboxError, match="no element called 'carousel'"):
        toolbox.cell_code("carousel")
