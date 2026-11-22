"""Widgets (the owner, 2026-11-21): the widget file, its properties found with ast (types and masks), a value
written back into only its own characters, a value checked before it is kept, and the prebuilt widgets."""

from __future__ import annotations

from pathlib import Path

import pytest

from swissarmybench_streamlit.domain import widget_properties as props
from swissarmybench_streamlit.domain import widgets as rules
from swissarmybench_streamlit.domain.widgets import Widget, WidgetError

PREBUILT = Path(__file__).resolve().parents[1] / "extensions/streamlit/src/swissarmybench_streamlit/widgets"

CODE = """import os
from typing import Literal

import streamlit as st

from sab_canvas import table

# The heading over the chart
title = "Sales by month"
show = True
count = 5  # 1..20
ratio = 0.5  # 0..1 step 0.1
colour = "#1f77b4"
start = "2026-01-01"
at = "09:30"
when = "2026-01-01 09:30"
kind: Literal["line", "bar"] = "line"
level = "title"  # choices: title, header, subheader
orders = ""  # table
x = "month"  # column of orders
y_column = "revenue"
key = os.environ["ORDERS_KEY"]
token = "${API_TOKEN}"
folder = "./data/out.csv"
labels = ["a", "b"]
style = {"bold": True}
number: int = "5"
_hidden = 3
computed = len(labels)
total = 1 + 1

st.subheader(title)
"""


def by_name(code: str = CODE) -> dict[str, props.Property]:
    return {p.name: p for p in props.detect(code)}


# ===== the file =====


def test_a_widget_file_round_trips_byte_for_byte() -> None:
    widget = Widget(
        name="sales_chart",
        code=CODE,
        description="Sales, by month",
        group="Charts",
        tags=("kpi",),
        size=(6, 4),
        min_size=(3, 2),
    )
    text = rules.write_widget(widget)
    assert text.startswith("# /// swissarmybench-widget\n# format = 1\n")
    read = rules.read_widget(text)
    assert (read.name, read.code, read.size, read.min_size, read.group, read.tags) == (
        "sales_chart",
        CODE,
        (6, 4),
        (3, 2),
        "Charts",
        ("kpi",),
    )
    assert rules.write_widget(read) == text  # the same widget, the same bytes


def test_the_header_is_rewritten_and_the_code_is_the_same_bytes() -> None:
    text = rules.write_widget(Widget(name="a", code="x = 1  # odd   spacing\n\n\n"))
    after = rules.with_header(text, name="b", description="  A   new\nline ")
    assert after.endswith("\n# ///\nx = 1  # odd   spacing\n\n\n")
    read = rules.read_widget(after)
    assert (read.name, read.description) == ("b", "A new line")


def test_files_that_are_not_widgets_say_why_with_their_line() -> None:
    with pytest.raises(WidgetError, match="no swissarmybench-widget header"):
        rules.read_widget("x = 1\n")
    broken = "# /// swissarmybench-widget\n# name = 'a\n# ///\n"
    with pytest.raises(WidgetError) as said:
        rules.read_widget(broken)
    assert said.value.line == 2
    with pytest.raises(WidgetError, match="newer version"):
        rules.read_widget("# /// swissarmybench-widget\n# format = 9\n# name = 'a'\n# ///\n")
    with pytest.raises(WidgetError, match="size"):
        rules.read_widget("# /// swissarmybench-widget\n# name = 'a'\n# size = [0, 2]\n# ///\n")


def test_names_are_checked_live() -> None:
    taken = frozenset({"button", "my_chart"})
    assert rules.check_name("sales", taken)["state"] == "available"
    assert rules.check_name("button", taken)["state"] == "taken"
    assert rules.check_name("my_chart", taken, own="my_chart")["state"] == "available"
    for bad in ("", "Sales", "1a", "a-b", "a" * 65, None):
        assert rules.check_name(bad, taken)["state"] == "invalid"
    assert rules.free_name("my_button", frozenset({"my_button", "my_button_2"})) == "my_button_3"


# ===== properties =====


def test_properties_are_the_top_level_plain_values_with_their_types_and_masks() -> None:
    found = by_name()
    expected = {
        "title": ("str", "text"),
        "show": ("bool", "switch"),
        "count": ("int", "number"),
        "ratio": ("float", "number"),
        "colour": ("colour", "colour"),
        "start": ("date", "date"),
        "at": ("time", "time"),
        "when": ("datetime", "datetime"),
        "kind": ("choice", "dropdown"),
        "level": ("choice", "dropdown"),
        "orders": ("table", "table"),
        "x": ("column", "column"),
        "y_column": ("column", "column"),
        "key": ("variable", "variable"),
        "token": ("variable", "variable"),
        "folder": ("path", "path"),
        "labels": ("list", "json"),
        "style": ("dict", "json"),
        "number": ("int", "number"),
    }
    assert {n: (p.type, p.mask) for n, p in found.items()} == expected
    assert "_hidden" not in found and "computed" not in found and "total" not in found
    assert found["title"].help == "The heading over the chart"
    assert (found["count"].minimum, found["count"].maximum) == (1, 20)
    assert (found["ratio"].minimum, found["ratio"].maximum, found["ratio"].step) == (0, 1, 0.1)
    assert found["kind"].choices == ("line", "bar") and found["kind"].annotated
    assert found["level"].choices == ("title", "header", "subheader")
    assert found["x"].of == "orders" and found["y_column"].of == "orders"
    assert (found["key"].default, found["token"].default) == ("ORDERS_KEY", "API_TOKEN")
    # An annotation always wins over the guess, and says when the value disagrees.
    assert found["number"].problem and "int" in found["number"].problem


def test_a_table_is_known_by_an_open_tables_name() -> None:
    found = {p.name: p for p in props.detect('source = "orders"\n', frozenset({"orders"}))}
    assert found["source"].type == "table"


def test_code_that_does_not_parse_says_its_line() -> None:
    with pytest.raises(props.PropertyError) as said:
        props.detect("title = 'a'\nif True\n")
    assert said.value.line == 2


@pytest.mark.parametrize(
    ("name", "value", "written"),
    [
        ("title", "Revenue ✓", 'title = "Revenue ✓"'),
        ("show", False, "show = False"),
        ("count", 7, "count = 7  # 1..20"),
        ("ratio", 1, "ratio = 1.0  # 0..1 step 0.1"),
        ("colour", "#d62728", 'colour = "#d62728"'),
        ("kind", "bar", 'kind: Literal["line", "bar"] = "bar"'),
        ("x", "region", 'x = "region"  # column of orders'),
        ("key", "OTHER_KEY", 'key = os.environ["OTHER_KEY"]'),
        ("labels", ["c"], 'labels = ["c"]'),
    ],
)
def test_a_value_is_written_into_only_its_own_characters(name: str, value: object, written: str) -> None:
    after = props.set_default(CODE, name, value)
    before_lines, after_lines = CODE.split("\n"), after.split("\n")
    changed = [(b, a) for b, a in zip(before_lines, after_lines, strict=True) if b != a]
    assert len(changed) == 1 and changed[0][1] == written
    assert by_name(after)[name].default == value or name == "ratio"


def test_a_variable_reference_stays_a_reference() -> None:
    after = props.set_default(CODE, "token", "OTHER")
    assert 'token = "${OTHER}"' in after


@pytest.mark.parametrize(
    ("name", "value", "said"),
    [
        ("colour", "red", "not a colour"),
        ("count", 50, "20 at most"),
        ("count", "five", "a whole number"),
        ("start", "2026-02-30", "not a date"),
        ("kind", "pie", "one of line, bar"),
        ("show", "yes", "on or off"),
        ("key", "NOT SET", "not a variable's name"),
    ],
)
def test_bad_values_are_refused_with_the_fix(name: str, value: object, said: str) -> None:
    with pytest.raises(props.PropertyError, match=said) as error:
        props.set_default(CODE, name, value)
    assert error.value.fix


def test_tables_columns_and_variables_are_checked_against_what_is_here() -> None:
    found = by_name()
    context = props.Context(
        tables={"orders": ["month", "region"]}, variables={"ORDERS_KEY"}, values={"orders": "orders"}
    )
    props.check(found["orders"], "orders", context)
    props.check(found["x"], "region", context)
    with pytest.raises(props.PropertyError, match="no table called sales"):
        props.check(found["orders"], "sales", context)
    with pytest.raises(props.PropertyError, match="has no column units") as error:
        props.check(found["x"], "units", context)
    assert "month" in error.value.fix
    with pytest.raises(props.PropertyError, match="not set on this computer") as error:
        props.check(found["key"], "MISSING_KEY", context)
    assert "Settings and secrets tab" in error.value.fix


def test_an_instances_values_fall_back_to_the_default_when_they_no_longer_fit() -> None:
    found = list(props.detect(CODE))
    values = props.values(found, {"count": 99, "colour": "#000000", "gone": 1})
    assert values["count"] == 5 and values["colour"] == "#000000" and "gone" not in values


def test_the_page_gives_the_properties_and_line_numbers_stay() -> None:
    found = list(props.detect(CODE))
    made = props.without_properties(CODE, found)
    assert made.count("\n") == CODE.count("\n")
    assert 'title = "Sales by month"' not in made and "computed = len(labels)" in made
    compile(made, "w", "exec")


# ===== the prebuilt widgets =====


def test_there_are_at_least_forty_prebuilt_widgets_each_one_reads_and_has_properties() -> None:
    files = sorted(PREBUILT.glob("*.widget.py"))
    assert len(files) >= 40
    groups = set()
    for path in files:
        widget = rules.read_widget(path.read_text(encoding="utf-8"), prebuilt=True)
        assert path.name == rules.file_name(widget.name)
        assert widget.description and widget.framework == "streamlit"
        groups.add(widget.group)
        found = props.detect(widget.code)
        if widget.name != "divider":
            assert found, widget.name
        compile(widget.code, path.name, "exec")
    assert {"Buttons", "Inputs", "Data", "Charts", "Text", "Filters", "Forms"} <= groups
